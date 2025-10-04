"""Chat module."""

import json
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

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

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatSendRequest, app_request: Request):
    """Send a message and get the response."""
    try:
        chat_service = app_request.app.state.chat_service

        result = await chat_service.send_message(
            content=request.content,
            thread_id=request.thread_id,
            user_id="default"
        )

        last_message = result["last_message"]
        chat_message = convert_langchain_message_to_chat_message(last_message)

        return ChatResponse(
            thread_id=result["thread_id"],
            message=chat_message,
            created_at=datetime.now()
        )

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing chat request: {str(e)}") from e


@router.post("/stream")
async def stream_message(request: ChatStreamRequest, app_request: Request):
    """Stream message responses as they are generated."""
    async def event_generator() -> AsyncIterator[str]:
        """Event Generator.


            Returns:
                Description of return value.
            """

        try:
            chat_service = app_request.app.state.chat_service

            async for event in chat_service.stream_message(
                content=request.content,
                thread_id=request.thread_id,
                user_id="default"
            ):
                yield f"data: {json.dumps(event)}\n\n"

        except Exception as e:
            error_event = {"type": "error", "error": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/retry/{thread_id}", response_model=ChatResponse)
async def retry_message(
    thread_id: str,
    app_request: Request,
    request: RetryChatRequest
):
    """Retry/regenerate a message using message ID-based replacement."""
    try:
        chat_service = app_request.app.state.chat_service

        result = await chat_service.retry_message(
            thread_id=thread_id,
            message_id=request.message_id,
            modified_content=request.content
        )

        last_message = result["last_message"]
        chat_message = convert_langchain_message_to_chat_message(last_message)

        return ChatResponse(
            thread_id=result["thread_id"],
            message=chat_message,
            created_at=datetime.now()
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrying message: {str(e)}") from e


@router.get("/history/{thread_id}", response_model=ChatHistoryResponse)
async def get_history(thread_id: str, app_request: Request):
    """Get message history for a thread."""
    try:
        chat_service = app_request.app.state.chat_service

        result = await chat_service.get_history(thread_id=thread_id)

        messages = result["messages"]
        chat_messages = [convert_langchain_message_to_chat_message(msg) for msg in messages]

        return ChatHistoryResponse(
            thread_id=result["thread_id"],
            messages=chat_messages
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving history: {str(e)}") from e


@router.get("/threads", response_model=ThreadListResponse)
async def get_threads(
    app_request: Request,
    user_id: str = Query(default="default", description="User ID to filter threads")
):
    """Get list of threads for a user."""
    try:
        chat_service = app_request.app.state.chat_service

        threads = await chat_service.get_threads(user_id=user_id)

        thread_infos = [
            ThreadInfo(
                thread_id=thread["thread_id"],
                title=thread["title"],
                created_at=thread["created_at"],
                last_message_preview=thread["last_message"]
            )
            for thread in threads
        ]

        return ThreadListResponse(threads=thread_infos)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving threads: {str(e)}") from e


@router.get("/checkpoints/{thread_id}")
async def get_checkpoints(
    thread_id: str,
    app_request: Request,
    limit: int = Query(default=10, description="Maximum number of checkpoints to retrieve")
):
    """Get checkpoint history for debugging and time-travel."""
    try:
        chat_service = app_request.app.state.chat_service

        checkpoints = await chat_service.get_checkpoints(
            thread_id=thread_id,
            limit=limit
        )

        return {
            "thread_id": thread_id,
            "checkpoints": checkpoints
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving checkpoints: {str(e)}") from e


@router.post("/resume/{thread_id}")
async def resume_from_failure(thread_id: str, app_request: Request):
    """Resume execution from a failed state."""
    try:
        chat_service = app_request.app.state.chat_service

        result = await chat_service.resume_from_failure(thread_id=thread_id)

        last_message = result["last_message"]
        chat_message = convert_langchain_message_to_chat_message(last_message)

        return {
            "thread_id": result["thread_id"],
            "message": chat_message,
            "status": result["status"],
            "resumed_from_checkpoint": result["resumed_from_checkpoint"]
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resuming from failure: {str(e)}") from e
