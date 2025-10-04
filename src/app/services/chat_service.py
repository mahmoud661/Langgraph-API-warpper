"""Chat Service module."""

import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from src.domain.chat_content import ContentBlock
from src.workflow.chat_runner import ChatRunner


class ChatService:
    """
    Simplified service layer for chat operations that delegates to ChatRunner.

    This service provides a clean interface for chat operations while delegating
    all LangGraph interactions to the ChatRunner.
    """

    def __init__(self, chat_runner: ChatRunner):
        """Initialize the chat service with ChatRunner dependency.

        Args:
            chat_runner: ChatRunner instance for LangGraph operations
        """
        self.chat_runner = chat_runner

    async def send_message(
        self,
        content: list[ContentBlock],
        thread_id: str | None = None,
        user_id: str = "default",
    ) -> dict[str, Any]:
        """Send a message and get the response.

        Args:
            content: List of ContentBlock objects representing the message
            thread_id: Optional thread ID to continue a conversation
            user_id: User ID for thread management

        Returns:
            Dict containing thread_id, messages, last_message, status
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        human_message = HumanMessage(
            content=[block.to_langchain_format() for block in content]
        )

        result = await self.chat_runner.run(
            messages=[human_message], thread_id=thread_id
        )

        messages = result.get("messages", [])
        if not messages:
            raise ValueError("No response generated from the assistant")

        last_message = messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError("Expected AI response but got different message type")

        return {
            "thread_id": thread_id,
            "messages": messages,
            "last_message": last_message,
            "status": "completed",
        }

    async def stream_message(
        self,
        content: list[ContentBlock],
        thread_id: str | None = None,
        user_id: str = "default",
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream message responses using ChatRunner's unified streaming.

        Args:
            content: List of ContentBlock objects representing the message
            thread_id: Optional thread ID to continue a conversation
            user_id: User ID for thread management

        Yields:
            Dict containing streaming events from ChatRunner
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        yield {"type": "metadata", "thread_id": thread_id}

        try:
            human_message = HumanMessage(
                content=[block.to_langchain_format() for block in content]
            )

            # Use ChatRunner's unified streaming
            async for event in self.chat_runner.stream(
                messages=[human_message], thread_id=thread_id
            ):
                yield event

        except Exception as e:
            yield {"type": "error", "error": str(e)}

    async def get_history(self, thread_id: str) -> dict[str, Any]:
        """Get message history for a thread.

        Args:
            thread_id: Thread ID to get history for

        Returns:
            Dict containing thread_id, messages, and history
        """
        history = await self.chat_runner.get_history(thread_id)

        if not history:
            raise ValueError(f"No history found for thread: {thread_id}")

        # Extract messages from the first checkpoint (most recent)
        messages = history[0].get("messages", []) if history else []

        if not messages:
            raise ValueError(f"No history found for thread: {thread_id}")

        return {"thread_id": thread_id, "messages": messages, "history": history}

    async def get_threads(self, user_id: str = "default") -> list[dict[str, Any]]:
        """Get list of threads for a user.

        Args:
            user_id: User ID to filter threads

        Returns:
            List of thread information (empty for now)
        """
        # TODO: implement thread persistence
        return []

    async def get_checkpoints(
        self, thread_id: str, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get checkpoint history for debugging and time-travel.

        Args:
            thread_id: Thread ID to get checkpoints for
            limit: Maximum number of checkpoints to retrieve

        Returns:
            List of checkpoint dictionaries
        """
        return await self.chat_runner.get_history(thread_id, limit)

    async def resume_interrupt(
        self, thread_id: str, interrupt_id: str | None = None, user_response: Any = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Resume execution after interrupt with user response.

        Args:
            thread_id: Thread ID
            interrupt_id: ID of interrupt to resume
            user_response: User's response to the interrupt

        Yields:
            Dict containing streaming events from resumed execution
        """
        async for event in self.chat_runner.resume_interrupt(
            thread_id=thread_id, interrupt_id=interrupt_id, user_response=user_response
        ):
            yield event

    async def cancel_interrupt(
        self, thread_id: str, interrupt_id: str | None = None
    ) -> dict[str, Any]:
        """Cancel a pending interrupt.

        Args:
            thread_id: Thread ID
            interrupt_id: ID of interrupt to cancel

        Returns:
            Dict containing cancellation result
        """
        return await self.chat_runner.cancel_interrupt(thread_id, interrupt_id)

    async def get_interrupts(self, thread_id: str) -> list[dict[str, Any]]:
        """Get current interrupts for a thread.

        Args:
            thread_id: Thread ID

        Returns:
            List of current interrupts
        """
        return await self.chat_runner.get_interrupts(thread_id)
