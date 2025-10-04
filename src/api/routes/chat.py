"""Chat routes module."""

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from src.api.controllers.chat_controller import ChatController
from src.api.dtos.chat import (
    ChatHistoryResponse,
    ChatResponse,
    ChatSendRequest,
    ChatStreamRequest,
    RetryChatRequest,
    ThreadListResponse,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatSendRequest, app_request: Request):
    """Send a message and get the response."""
    chat_service = app_request.app.state.chat_service
    controller = ChatController(chat_service)
    return await controller.send_message(request)


@router.post("/stream")
async def stream_message(request: ChatStreamRequest, app_request: Request):
    """Stream message responses as they are generated."""
    chat_service = app_request.app.state.chat_service
    controller = ChatController(chat_service)

    return StreamingResponse(
        controller.stream_message(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/retry/{thread_id}", response_model=ChatResponse)
async def retry_message(
    thread_id: str, request: RetryChatRequest, app_request: Request
):
    """Retry/regenerate a message using message ID-based replacement."""
    chat_service = app_request.app.state.chat_service
    controller = ChatController(chat_service)
    return await controller.retry_message(thread_id, request)


@router.get("/history/{thread_id}", response_model=ChatHistoryResponse)
async def get_history(thread_id: str, app_request: Request):
    """Get message history for a thread."""
    chat_service = app_request.app.state.chat_service
    controller = ChatController(chat_service)
    return await controller.get_history(thread_id)


@router.get("/threads", response_model=ThreadListResponse)
async def get_threads(
    app_request: Request,
    user_id: str = Query(default="default", description="User ID to filter threads"),
):
    """Get list of threads for a user."""
    chat_service = app_request.app.state.chat_service
    controller = ChatController(chat_service)
    return await controller.get_threads(user_id)


@router.get("/checkpoints/{thread_id}")
async def get_checkpoints(
    thread_id: str,
    app_request: Request,
    limit: int = Query(
        default=10, description="Maximum number of checkpoints to retrieve"
    ),
):
    """Get checkpoint history for debugging and time-travel."""
    chat_service = app_request.app.state.chat_service
    controller = ChatController(chat_service)
    return await controller.get_checkpoints(thread_id, limit)


@router.post("/resume/{thread_id}")
async def resume_from_failure(thread_id: str, app_request: Request):
    """Resume execution from a failed state."""
    chat_service = app_request.app.state.chat_service
    controller = ChatController(chat_service)
    return await controller.resume_from_failure(thread_id)
