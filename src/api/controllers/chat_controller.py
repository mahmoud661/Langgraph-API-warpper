import json
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import HTTPException

from src.api.dtos.chat import (
    ChatHistoryResponse,
    ChatResponse,
    ChatSendRequest,
    ChatStreamRequest,
    RetryChatRequest,
    ThreadInfo,
    ThreadListResponse,
)
from src.api.utils.convert_message import convert_langchain_message_to_chat_message
from src.app.services.chat_service import ChatService


class ChatController:
    """Controller for handling chat-related HTTP and WebSocket operations."""

    def __init__(self, chat_service: ChatService):
        """Initialize the chat controller.

        Args:
            chat_service: ChatService instance
        """
        self.chat_service = chat_service

    async def send_message(self, request: ChatSendRequest) -> ChatResponse:
        """Handle sending a message via REST API.

        Args:
            request: Chat send request

        Returns:
            ChatResponse with the assistant's response

        Raises:
            HTTPException: If there's an error processing the request
        """
        try:
            result = await self.chat_service.send_message(
                content=request.content, thread_id=request.thread_id, user_id="default"
            )

            last_message = result["last_message"]
            chat_message = convert_langchain_message_to_chat_message(last_message)

            return ChatResponse(
                thread_id=result["thread_id"],
                message=chat_message,
                created_at=datetime.now(),
            )

        except ValueError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error processing chat request: {str(e)}"
            ) from e

    async def stream_message(self, request: ChatStreamRequest) -> AsyncIterator[str]:
        """Handle streaming message via SSE.

        Args:
            request: Chat stream request

        Yields:
            SSE formatted event strings
        """
        try:
            async for event in self.chat_service.stream_message(
                content=request.content, thread_id=request.thread_id, user_id="default"
            ):
                yield f"data: {json.dumps(event)}\\n\\n"

        except Exception as e:
            error_event = {"type": "error", "error": str(e)}
            yield f"data: {json.dumps(error_event)}\\n\\n"

    async def retry_message(
        self, thread_id: str, request: RetryChatRequest
    ) -> ChatResponse:
        """Handle message retry via REST API.

        Args:
            thread_id: Thread ID
            request: Retry request with message ID and optional content

        Returns:
            ChatResponse with the regenerated response

        Raises:
            HTTPException: If there's an error processing the request
        """
        try:
            # Note: ChatService doesn't have retry_message method yet
            # This would need to be implemented or use ChatRunner directly
            raise NotImplementedError(
                "Retry message functionality needs to be implemented in ChatService"
            )

        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error retrying message: {str(e)}"
            ) from e

    async def get_history(self, thread_id: str) -> ChatHistoryResponse:
        """Handle getting chat history via REST API.

        Args:
            thread_id: Thread ID to get history for

        Returns:
            ChatHistoryResponse with message history

        Raises:
            HTTPException: If there's an error retrieving history
        """
        try:
            result = await self.chat_service.get_history(thread_id=thread_id)

            messages = result["messages"]
            chat_messages = [
                convert_langchain_message_to_chat_message(msg) for msg in messages
            ]

            return ChatHistoryResponse(
                thread_id=result["thread_id"], messages=chat_messages
            )

        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error retrieving history: {str(e)}"
            ) from e

    async def get_threads(self, user_id: str = "default") -> ThreadListResponse:
        """Handle getting thread list via REST API.

        Args:
            user_id: User ID to filter threads

        Returns:
            ThreadListResponse with list of threads

        Raises:
            HTTPException: If there's an error retrieving threads
        """
        try:
            threads = await self.chat_service.get_threads(user_id=user_id)

            thread_infos = [
                ThreadInfo(
                    thread_id=thread["thread_id"],
                    title=thread["title"],
                    created_at=thread["created_at"],
                    last_message_preview=thread["last_message"],
                )
                for thread in threads
            ]

            return ThreadListResponse(threads=thread_infos)

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error retrieving threads: {str(e)}"
            ) from e

    async def get_checkpoints(self, thread_id: str, limit: int = 10) -> dict:
        """Handle getting checkpoints via REST API.

        Args:
            thread_id: Thread ID to get checkpoints for
            limit: Maximum number of checkpoints to retrieve

        Returns:
            Dict containing thread_id and checkpoints

        Raises:
            HTTPException: If there's an error retrieving checkpoints
        """
        try:
            checkpoints = await self.chat_service.get_checkpoints(
                thread_id=thread_id, limit=limit
            )

            return {"thread_id": thread_id, "checkpoints": checkpoints}

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error retrieving checkpoints: {str(e)}"
            ) from e

    async def resume_from_failure(self, thread_id: str) -> dict:
        """Handle resuming from failure via REST API.

        Args:
            thread_id: Thread ID to resume

        Returns:
            Dict containing resume result

        Raises:
            HTTPException: If there's an error resuming
        """
        try:
            # Note: ChatService doesn't have resume_from_failure method yet
            # This would need to be implemented or use ChatRunner directly
            raise NotImplementedError(
                "Resume from failure functionality needs to be implemented in ChatService"
            )

        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error resuming from failure: {str(e)}"
            ) from e
