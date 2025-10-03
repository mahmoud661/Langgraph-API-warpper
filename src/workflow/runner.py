"""Workflow runner module for executing LangGraph workflows with checkpointing."""

import os
import uuid
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any, cast

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command, StreamMode
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.workflow.graph import create_workflow

if TYPE_CHECKING:
    from src.workflow.graph import AgentState


class WorkflowRunner:
    """WorkflowRunner class."""

    def __init__(self, checkpointer: AsyncPostgresSaver):
        """Init  .

        Args:
            checkpointer: Description of checkpointer.
        """
        self.checkpointer = checkpointer

        workflow = create_workflow()
        self.graph = workflow.compile(checkpointer=checkpointer)

    async def run_workflow(self, input_data: dict[str, Any], thread_id: str | None = None) -> dict[str, Any]:
        """Run Workflow.

        Args:
            input_data: Description of input_data.
            thread_id: Description of thread_id.

        Returns:
            Description of return value.
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        messages = input_data.get("messages", [])
        if isinstance(messages, str):
            messages = [HumanMessage(content=messages)]
        elif isinstance(messages, list):
            messages = [HumanMessage(content=msg) if isinstance(msg, str) else msg for msg in messages]

        result = await self.graph.ainvoke(cast("AgentState", {"messages": messages}), config=config)

        return {"thread_id": thread_id, "result": result, "status": "interrupted" if "__interrupt__" in result else "completed"}

    async def resume_workflow(self, thread_id: str, resume_value: Any) -> dict[str, Any]:
        """Resume Workflow.

        Args:
            thread_id: Description of thread_id.
            resume_value: Description of resume_value.

        Returns:
            Description of return value.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        result = await self.graph.ainvoke(Command(resume=resume_value), config=config)

        return {"thread_id": thread_id, "result": result, "status": "interrupted" if "__interrupt__" in result else "completed"}

    async def stream_workflow(self, input_data: dict[str, Any], thread_id: str | None = None, stream_mode: StreamMode = "messages") -> AsyncIterator[dict[str, Any]]:
        """Stream Workflow.

        Args:
            input_data: Description of input_data.
            thread_id: Description of thread_id.
            stream_mode: Description of stream_mode.

        Returns:
            Description of return value.
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        messages = input_data.get("messages", [])
        if isinstance(messages, str):
            messages = [HumanMessage(content=messages)]

        async for chunk in self.graph.astream(cast("AgentState", {"messages": messages}), config=config, stream_mode=stream_mode):
            yield {"thread_id": thread_id, "chunk": chunk}

    async def get_state(self, thread_id: str) -> dict[str, Any]:
        """Get State.

        Args:
            thread_id: Description of thread_id.

        Returns:
            Description of return value.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        state = await self.graph.aget_state(config)

        return {"values": state.values, "next": state.next, "tasks": state.tasks, "interrupts": [{"id": i.id, "value": i.value} for i in (state.interrupts or [])]}

    async def get_state_history(self, thread_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get State History.

        Args:
            thread_id: Description of thread_id.
            limit: Description of limit.

        Returns:
            Description of return value.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        history = []

        count = 0
        async for checkpoint in self.graph.aget_state_history(config):
            if count >= limit:
                break

            history.append({"checkpoint_id": checkpoint.config.get("configurable", {}).get("checkpoint_id"), "values": checkpoint.values, "next": checkpoint.next, "metadata": checkpoint.metadata})
            count += 1

        return history

    async def update_state(self, thread_id: str, values: dict[str, Any], checkpoint_id: str | None = None) -> dict[str, Any]:
        """Update State.

        Args:
            thread_id: Description of thread_id.
            values: Description of values.
            checkpoint_id: Description of checkpoint_id.

        Returns:
            Description of return value.
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        if checkpoint_id:
            config["configurable"]["checkpoint_id"] = checkpoint_id

        await self.graph.aupdate_state(config, values)

        return {"status": "updated", "thread_id": thread_id}


async def create_workflow_runner() -> WorkflowRunner:
    """Create Workflow Runner.


    Returns:
        Description of return value.
    """
    db_url = os.getenv("DATABASE_URL", "")

    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }

    pool: AsyncConnectionPool[AsyncConnection[Any]] = AsyncConnectionPool(conninfo=db_url, kwargs=connection_kwargs, min_size=2, max_size=10, max_idle=300, timeout=30, open=False)

    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    return WorkflowRunner(checkpointer)
