"""Chat Runner module."""

import os
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
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
        # Compile with checkpointer - interrupts will happen inside tools via interrupt() calls
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

    async def stream(self, messages: list[BaseMessage], thread_id: str | None = None, stream_mode: str = "messages") -> AsyncIterator[dict[str, Any]]:
        """Stream - Legacy single mode streaming.

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

        async for chunk in self.graph.astream(cast(AgentState, {"messages": messages}), config=config, stream_mode="messages"):
            yield {"thread_id": thread_id, "chunk": chunk}

    async def unified_stream(self, messages: list[BaseMessage], thread_id: str | None = None) -> AsyncIterator[dict[str, Any]]:
        """Unified Stream - Multi-mode streaming for AI tokens + interrupts.
        
        This method implements the unified streaming approach from our research:
        - Uses multi-mode streaming ["messages", "values", "custom"] 
        - Captures AI tokens via "messages" mode
        - Detects interrupts via "values" mode (__interrupt__ key)
        - Streams questions via "custom" mode (StreamWriter)
        
        Args:
            messages: Conversation messages
            thread_id: Thread identifier for conversation persistence
            
        Yields:
            Unified event dictionaries with type-specific data
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        try:

            async for event_type, chunk in self.graph.astream(
                cast(AgentState, {"messages": messages}),
                config=config,
                stream_mode=["messages", "values", "custom"]
            ):

                # Process different event types
                if event_type == "messages":
                    # AI token streaming
                    if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
                        token, metadata = chunk
                        if hasattr(token, 'content') and getattr(token, 'content', None):
                            yield {
                                "type": "ai_token",
                                "content": str(token.content),
                                "thread_id": thread_id,
                                "metadata": {
                                    "node": metadata.get("langgraph_node") if hasattr(metadata, 'get') else None,
                                    "step": metadata.get("langgraph_step") if hasattr(metadata, 'get') else None,
                                    "tags": metadata.get("tags", []) if hasattr(metadata, 'get') else []
                                }
                            }

                elif event_type == "values":
                    # State updates including interrupt detection
                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        interrupts = chunk["__interrupt__"]
                        if isinstance(interrupts, (list, tuple)):
                            for interrupt in interrupts:

                                interrupt_data = {
                                    "type": "interrupt_detected",
                                    "interrupt_id": getattr(interrupt, 'id', str(interrupt)),
                                    "thread_id": thread_id,
                                    "question_data": getattr(interrupt, 'value', interrupt),
                                    "resumable": getattr(interrupt, 'resumable', True),
                                    "namespace": getattr(interrupt, 'ns', [])
                                }
                                yield interrupt_data

                    # Also yield regular state updates for debugging
                    if isinstance(chunk, dict):
                        yield {
                            "type": "state_update",
                            "thread_id": thread_id,
                            "state_keys": list(chunk.keys()),
                            "has_interrupt": "__interrupt__" in chunk
                        }

                elif event_type == "custom":
                    # Interactive questions streamed via StreamWriter
                    yield {
                        "type": "question_token",
                        "content": chunk,
                        "thread_id": thread_id
                    }

        except Exception as e:
            # Error handling for streaming
            yield {
                "type": "error",
                "thread_id": thread_id,
                "error": str(e),
                "error_type": type(e).__name__
            }

    async def resume_interrupt(self, thread_id: str, interrupt_id: str | None = None, user_response: Any = None) -> AsyncIterator[dict[str, Any]]:
        """Resume execution after interrupt with user response.
        
        Args:
            thread_id: Thread identifier
            interrupt_id: Specific interrupt to resume (optional)
            user_response: User's response to the interrupt
            
        Yields:
            Continuation of unified streaming events
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        # Prepare resume command
        if interrupt_id and isinstance(user_response, dict):
            # Resume specific interrupt with complex response
            command = Command(resume={interrupt_id: user_response})
        else:
            # Resume with simple response (most common case)
            command = Command(resume=user_response)

        try:
            # Resume streaming with multi-mode
            async for event_type, chunk in self.graph.astream(
                command,
                config=config,
                stream_mode=["messages", "values", "custom"]
            ):
                # Same processing as unified_stream
                if event_type == "messages":
                    if isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
                        token, metadata = chunk
                        if hasattr(token, 'content') and getattr(token, 'content', None):
                            yield {
                                "type": "ai_token",
                                "content": str(token.content),
                                "thread_id": thread_id,
                                "metadata": {
                                    "node": metadata.get("langgraph_node") if hasattr(metadata, 'get') else None,
                                    "step": metadata.get("langgraph_step") if hasattr(metadata, 'get') else None
                                },
                                "resumed": True
                            }

                elif event_type == "values":
                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        interrupts = chunk["__interrupt__"]
                        if isinstance(interrupts, (list, tuple)):
                            for interrupt in interrupts:
                                yield {
                                    "type": "interrupt_detected",
                                    "interrupt_id": getattr(interrupt, 'id', str(interrupt)),
                                    "thread_id": thread_id,
                                    "question_data": getattr(interrupt, 'value', interrupt),
                                    "resumable": getattr(interrupt, 'resumable', True)
                                }

                elif event_type == "custom":
                    yield {
                        "type": "question_token",
                        "content": chunk,
                        "thread_id": thread_id
                    }

        except Exception as e:
            yield {
                "type": "error",
                "thread_id": thread_id,
                "error": f"Resume failed: {str(e)}",
                "error_type": type(e).__name__
            }

    async def get_interrupts(self, thread_id: str) -> list[dict[str, Any]]:
        """Get current interrupts for a thread.
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            List of interrupt information dictionaries
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

        try:
            state = await self.graph.aget_state(config)

            interrupts = []
            for interrupt in state.interrupts:
                interrupts.append({
                    "interrupt_id": interrupt.id,
                    "question_data": interrupt.value,
                    "resumable": getattr(interrupt, 'resumable', True),
                    "namespace": getattr(interrupt, 'ns', []),
                    "created_at": "now"  # You might want to add timestamp tracking
                })

            return interrupts

        except Exception as e:
            return [{"error": f"Failed to get interrupts: {str(e)}"}]

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

    async def has_pending_interrupts(self, thread_id: str) -> bool:
        """Check if thread has pending interrupts.
        
        Args:
            thread_id: Thread identifier
            
        Returns:
            True if there are pending interrupts, False otherwise
        """
        interrupts = await self.get_interrupts(thread_id)
        return len(interrupts) > 0 and not any("error" in interrupt for interrupt in interrupts)

    async def cancel_interrupt(self, thread_id: str, interrupt_id: str | None = None) -> dict[str, Any]:
        """Cancel a pending interrupt and clean up the thread state.
        
        Args:
            thread_id: Thread identifier
            interrupt_id: Specific interrupt to cancel (optional)
            
        Returns:
            Status of cancellation operation
        """
        try:
            config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

            # Get current state to check for interrupts
            state = await self.graph.aget_state(config)

            if not state.next:
                return {
                    "thread_id": thread_id,
                    "status": "no_interrupts",
                    "message": "No pending interrupts to cancel"
                }

            # Update the state to remove the interrupt and continue with a cancellation message
            # We'll add a system message indicating the operation was cancelled
            current_messages = state.values.get("messages", [])

            # Add a cancellation message to the conversation
            from langchain_core.messages import SystemMessage
            cancellation_msg = SystemMessage(
                content="The previous operation was cancelled by the user."
            )

            # Update state by adding the cancellation message and clearing interrupts
            new_state = {
                "messages": current_messages + [cancellation_msg]
            }

            # Update the graph state - this should clear any pending interrupts
            await self.graph.aupdate_state(config, new_state)

            return {
                "thread_id": thread_id,
                "interrupt_id": interrupt_id,
                "status": "cancelled",
                "message": "Interrupt cancelled successfully"
            }

        except Exception as e:
            return {
                "thread_id": thread_id,
                "interrupt_id": interrupt_id,
                "status": "error",
                "error": f"Failed to cancel interrupt: {str(e)}"
            }


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
