"""Chat Runner module."""

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import StreamMode
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.workflow.graph import AgentState, create_workflow


class ChatRunner:
    """ChatRunner class."""

    def __init__(self, checkpointer: AsyncPostgresSaver):
        """Init  .

        Args:
            checkpointer: Description of checkpointer.
        """

        self.checkpointer = checkpointer

        workflow = create_workflow()
        self.graph = workflow.compile(checkpointer=checkpointer)

    async def run(self, messages: list[BaseMessage], thread_id: str | None = None) -> dict[str, Any]:
        """Run.

        Args:
            messages: Description of messages.
            thread_id: Description of thread_id.

        Returns:
            Description of return value.
        """

        if thread_id is None:
            thread_id = str(uuid.uuid4())

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        result = await self.graph.ainvoke(cast(AgentState, {"messages": messages}), config=config)

        return {"thread_id": thread_id, "messages": result.get("messages", []), "status": "completed"}

    async def stream(self, messages: list[BaseMessage], thread_id: str | None = None, stream_mode: StreamMode = "messages") -> AsyncIterator[dict[str, Any]]:
        """Stream.

        Args:
            messages: Description of messages.
            thread_id: Description of thread_id.
            stream_mode: Description of stream_mode.

        Returns:
            Description of return value.
        """

        if thread_id is None:
            thread_id = str(uuid.uuid4())

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        async for chunk in self.graph.astream(cast(AgentState, {"messages": messages}), config=config, stream_mode=stream_mode):
            yield {"thread_id": thread_id, "chunk": chunk}

    async def get_history(self, thread_id: str, limit: int = 10) -> list[dict[str, Any]]:
        """Get History.

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

            history.append({"checkpoint_id": checkpoint.config.get("configurable", {}).get("checkpoint_id"), "messages": checkpoint.values.get("messages", []), "metadata": checkpoint.metadata})
            count += 1

        return history

    async def retry_message(self, thread_id: str, checkpoint_id: str | None = None) -> dict[str, Any]:
        """Retry Message.

        Args:
            thread_id: Description of thread_id.
            checkpoint_id: Description of checkpoint_id.

        Returns:
            Description of return value.
        """

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        if checkpoint_id:
            config["configurable"]["checkpoint_id"] = checkpoint_id

        state = await self.graph.aget_state(config)

        messages = state.values.get("messages", [])
        if not messages:
            return {"thread_id": thread_id, "status": "error", "error": "No messages in history to retry"}

        last_message = messages[-1]
        if isinstance(last_message, AIMessage):
            messages = messages[:-1]

        result = await self.graph.ainvoke(cast(AgentState, {"messages": messages}), config=config)

        return {"thread_id": thread_id, "messages": result.get("messages", []), "status": "completed"}


async def create_chat_runner() -> ChatRunner:
    """Create Chat Runner.


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

    return ChatRunner(checkpointer)
