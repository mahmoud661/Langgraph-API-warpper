"""Unified WebSocket Chat - Handles both AI responses and interactive questions."""

from fastapi import APIRouter, WebSocket

from src.api.controllers.websocket_chat_controller import WebSocketChatController

router = APIRouter(prefix="/ws", tags=["websocket-chat"])


@router.websocket("/chat-stream")
async def unified_websocket_chat(websocket: WebSocket):
    """Unified WebSocket Chat Endpoint.

    Handles both AI streaming responses and interactive human-in-the-loop workflows
    in a single endpoint using multi-mode LangGraph streaming.

    Supported Actions:
    - send_message: Send new message and start streaming
    - resume_interrupt: Resume from interrupt with user response
    - cancel_interrupt: Cancel pending interrupt
    - get_interrupts: Get current pending interrupts
    """
    chat_service = websocket.app.state.chat_service
    controller = WebSocketChatController(chat_service)
    await controller.handle_unified_chat(websocket)


@router.websocket("/connection-stats")
async def connection_stats_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time connection statistics.

    Sends connection stats every 5 seconds including:
    - Number of active connections
    - Connection details (IDs, thread IDs, pending interrupts)
    """
    chat_service = websocket.app.state.chat_service
    controller = WebSocketChatController(chat_service)
    await controller.handle_connection_stats(websocket)
