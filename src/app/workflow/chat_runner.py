"""Chat Runner module."""

import os
import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command, StreamMode
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from src.workflow.graph import AgentState, create_workflow
from src.workflow.utils.create_config import create_config
from src.workflow.utils.create_error_event import create_error_event
from src.workflow.utils.process_message_event import process_message_event
from src.workflow.utils.process_values_event import process_values_event


class ChatRunner:
    """ChatRunner class for managing conversational AI workflows with interrupts."""

    def __init__(self, checkpointer: AsyncPostgresSaver):
        """Initialize ChatRunner with checkpointer."""
        self.checkpointer = checkpointer
        workflow = create_workflow()
        self.graph = workflow.compile(checkpointer=checkpointer)

    async def run(
        self, messages: list[BaseMessage], thread_id: str | None = None
    ) -> dict[str, Any]:
        """Run workflow to completion without streaming."""
        thread_id = thread_id or str(uuid.uuid4())
        config = create_config(thread_id)

        result = await self.graph.ainvoke(
            cast(AgentState, {"messages": messages}), config=config
        )

        return {
            "thread_id": thread_id,
            "messages": result.get("messages", []),
            "status": "completed",
        }

    async def stream(
        self,
        messages: list[BaseMessage],
        thread_id: str | None = None,
        stream_mode: StreamMode | Sequence[StreamMode] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Unified multi-mode streaming for AI tokens, interrupts, and questions."""
        thread_id = thread_id or str(uuid.uuid4())
        config = create_config(thread_id)
        if stream_mode is None:
            stream_mode = ["messages", "values", "custom"]

        try:
            async for event_type, chunk in self.graph.astream(
                cast(AgentState, {"messages": messages}),
                config=config,
                stream_mode=stream_mode,
            ):
                # Process message events (AI tokens)
                if event_type == "messages":
                    event = process_message_event(chunk, thread_id)
                    if event:
                        yield event

                # Process values events (interrupts and state)
                elif event_type == "values":
                    for event in process_values_event(chunk, thread_id):
                        yield event

                # Process custom events (questions)
                elif event_type == "custom":
                    yield {
                        "type": "question_token",
                        "content": chunk,
                        "thread_id": thread_id,
                    }

        except Exception as e:
            yield create_error_event(thread_id, e)

    async def resume_interrupt(
        self, thread_id: str, interrupt_id: str | None = None, user_response: Any = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume execution after interrupt with user response."""
        config = create_config(thread_id)

        # Prepare resume command
        command = (
            Command(resume={interrupt_id: user_response})
            if interrupt_id and isinstance(user_response, dict)
            else Command(resume=user_response)
        )

        try:
            async for event_type, chunk in self.graph.astream(
                command, config=config, stream_mode=["messages", "values", "custom"]
            ):
                if event_type == "messages":
                    event = process_message_event(chunk, thread_id, resumed=True)
                    if event:
                        yield event

                elif event_type == "values":
                    for event in process_values_event(chunk, thread_id):
                        yield event

                elif event_type == "custom":
                    yield {
                        "type": "question_token",
                        "content": chunk,
                        "thread_id": thread_id,
                    }

        except Exception as e:
            yield create_error_event(thread_id, e, "Resume failed")

    async def get_interrupts(self, thread_id: str) -> list[dict[str, Any]]:
        """Get current interrupts for a thread."""
        config = create_config(thread_id)

        try:
            state = await self.graph.aget_state(config)
            return [
                {
                    "interrupt_id": interrupt.id,
                    "question_data": interrupt.value,
                    "resumable": getattr(interrupt, "resumable", True),
                    "namespace": getattr(interrupt, "ns", []),
                    "created_at": "now",
                }
                for interrupt in state.interrupts
            ]
        except Exception as e:
            return [{"error": f"Failed to get interrupts: {str(e)}"}]

    async def get_history(
        self, thread_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get conversation history with checkpoints."""
        config = create_config(thread_id)
        history = []

        count = 0
        async for checkpoint in self.graph.aget_state_history(config):
            if count >= limit:
                break

            history.append(
                {
                    "checkpoint_id": checkpoint.config.get("configurable", {}).get(
                        "checkpoint_id"
                    ),
                    "messages": checkpoint.values.get("messages", []),
                    "metadata": checkpoint.metadata,
                }
            )
            count += 1

        return history

    async def retry_message(
        self, thread_id: str, checkpoint_id: str | None = None
    ) -> dict[str, Any]:
        """Retry last AI message from checkpoint."""

        config = create_config(thread_id, checkpoint_id)
        state = await self.graph.aget_state(config)

        messages = state.values.get("messages", [])
        if not messages:
            return {
                "thread_id": thread_id,
                "status": "error",
                "error": "No messages in history to retry",
            }

        # Remove last AI message if present
        if isinstance(messages[-1], AIMessage):
            messages = messages[:-1]

        result = await self.graph.ainvoke(
            cast(AgentState, {"messages": messages}), config=config
        )

        return {
            "thread_id": thread_id,
            "messages": result.get("messages", []),
            "status": "completed",
        }

    async def has_pending_interrupts(self, thread_id: str) -> bool:
        """Check if thread has pending interrupts."""
        interrupts = await self.get_interrupts(thread_id)
        return len(interrupts) > 0 and not any("error" in i for i in interrupts)

    async def cancel_interrupt(
        self, thread_id: str, interrupt_id: str | None = None
    ) -> dict[str, Any]:
        """Cancel a pending interrupt and clean up thread state."""
        try:
            config = create_config(thread_id)
            state = await self.graph.aget_state(config)

            if not state.next:
                return {
                    "thread_id": thread_id,
                    "status": "no_interrupts",
                    "message": "No pending interrupts to cancel",
                }

            # Add cancellation message and update state
            current_messages = state.values.get("messages", [])
            cancellation_msg = SystemMessage(
                content="The previous operation was cancelled by the user."
            )

            await self.graph.aupdate_state(
                config, {"messages": current_messages + [cancellation_msg]}
            )

            return {
                "thread_id": thread_id,
                "interrupt_id": interrupt_id,
                "status": "cancelled",
                "message": "Interrupt cancelled successfully",
            }

        except Exception as e:
            return {
                "thread_id": thread_id,
                "interrupt_id": interrupt_id,
                "status": "error",
                "error": f"Failed to cancel interrupt: {str(e)}",
            }


# ============================================================================
# Factory Function
# ============================================================================


async def create_chat_runner() -> ChatRunner:
    """Create and initialize ChatRunner with database connection."""
    db_url = os.getenv("DATABASE_URL", "")

    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }

    pool: AsyncConnectionPool[AsyncConnection[Any]] = AsyncConnectionPool(
        conninfo=db_url,
        kwargs=connection_kwargs,
        min_size=2,
        max_size=10,
        max_idle=300,
        timeout=30,
        open=False,
    )

    await pool.open()

    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()

    return ChatRunner(checkpointer)
