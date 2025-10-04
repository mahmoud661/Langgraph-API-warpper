"""WebSocket message handlers for different actions."""

from typing import Any, Dict

from fastapi import WebSocket

from src.api.utils.websocket_utils import (
    generate_thread_id,
    parse_content_blocks,
    send_websocket_event,
)
from src.app.services.chat_service import ChatService


async def handle_send_message_action(
    websocket: WebSocket,
    request_data: Dict[str, Any],
    connection_id: str,
    active_connections: Dict[str, Dict],
    chat_service: ChatService,
) -> None:
    """Handle send_message WebSocket action.

    Args:
        websocket: WebSocket connection
        request_data: Client request data
        connection_id: Connection identifier
        active_connections: Dictionary of active connections
        chat_service: ChatService instance
    """
    try:
        content_data = request_data.get("content", [])
        thread_id = request_data.get("thread_id") or generate_thread_id()

        active_connections[connection_id]["thread_id"] = thread_id
        content_blocks = parse_content_blocks(content_data)

        await send_websocket_event(
            websocket,
            "message_started",
            {"thread_id": thread_id, "message": "Processing your message..."},
        )

        async for event in chat_service.stream_message(
            content=content_blocks, thread_id=thread_id
        ):
            await handle_streaming_event(
                websocket, event, connection_id, active_connections
            )

        if not active_connections[connection_id]["pending_interrupts"]:
            await send_websocket_event(
                websocket,
                "message_complete",
                {"thread_id": thread_id, "status": "completed"},
            )

    except Exception as e:
        await send_websocket_event(
            websocket,
            "error",
            {
                "message": f"Failed to process message: {str(e)}",
                "error_type": type(e).__name__,
            },
        )


async def handle_resume_interrupt_action(
    websocket: WebSocket,
    request_data: Dict[str, Any],
    connection_id: str,
    active_connections: Dict[str, Dict],
    chat_service: ChatService,
) -> None:
    """Handle resume_interrupt WebSocket action.

    Args:
        websocket: WebSocket connection
        request_data: Client request data
        connection_id: Connection identifier
        active_connections: Dictionary of active connections
        chat_service: ChatService instance
    """
    try:
        interrupt_id = request_data.get("interrupt_id")
        user_response = request_data.get("user_response")
        thread_id = active_connections[connection_id]["thread_id"]

        if not thread_id:
            await send_websocket_event(
                websocket,
                "error",
                {"message": "No active thread for this connection"},
            )
            return

        if interrupt_id in active_connections[connection_id]["pending_interrupts"]:
            del active_connections[connection_id]["pending_interrupts"][interrupt_id]

        await send_websocket_event(
            websocket,
            "interrupt_resumed",
            {
                "interrupt_id": interrupt_id,
                "thread_id": thread_id,
                "user_response": user_response,
            },
        )

        async for event in chat_service.resume_interrupt(
            thread_id=thread_id,
            interrupt_id=interrupt_id,
            user_response=user_response,
        ):
            await handle_streaming_event(
                websocket, event, connection_id, active_connections, resumed=True
            )

        if not active_connections[connection_id]["pending_interrupts"]:
            await send_websocket_event(
                websocket,
                "message_complete",
                {"thread_id": thread_id, "status": "completed"},
            )

    except Exception as e:
        await send_websocket_event(
            websocket,
            "error",
            {
                "message": f"Failed to resume interrupt: {str(e)}",
                "error_type": type(e).__name__,
            },
        )


async def handle_cancel_interrupt_action(
    websocket: WebSocket,
    request_data: Dict[str, Any],
    connection_id: str,
    active_connections: Dict[str, Dict],
    chat_service: ChatService,
) -> None:
    """Handle cancel_interrupt WebSocket action.

    Args:
        websocket: WebSocket connection
        request_data: Client request data
        connection_id: Connection identifier
        active_connections: Dictionary of active connections
        chat_service: ChatService instance
    """
    try:
        interrupt_id = request_data.get("interrupt_id")
        thread_id = request_data.get("thread_id")

        if not thread_id:
            await send_websocket_event(
                websocket,
                "error",
                {
                    "message": "thread_id is required for cancel_interrupt",
                    "error_type": "ValidationError",
                },
            )
            return

        result = await chat_service.cancel_interrupt(thread_id, interrupt_id)

        if (
            interrupt_id
            and interrupt_id in active_connections[connection_id]["pending_interrupts"]
        ):
            del active_connections[connection_id]["pending_interrupts"][interrupt_id]

        if result["status"] == "cancelled":
            await send_websocket_event(
                websocket,
                "interrupt_cancelled",
                {
                    "interrupt_id": interrupt_id,
                    "thread_id": thread_id,
                    "message": result["message"],
                },
            )
        else:
            await send_websocket_event(
                websocket,
                "error",
                {
                    "message": result.get(
                        "error", result.get("message", "Unknown error")
                    ),
                    "error_type": "CancellationError",
                },
            )

    except Exception as e:
        await send_websocket_event(
            websocket,
            "error",
            {
                "message": f"Failed to cancel interrupt: {str(e)}",
                "error_type": type(e).__name__,
            },
        )


async def handle_get_interrupts_action(
    websocket: WebSocket,
    request_data: Dict[str, Any],
    connection_id: str,
    active_connections: Dict[str, Dict],
    chat_service: ChatService,
) -> None:
    """Handle get_interrupts WebSocket action.

    Args:
        websocket: WebSocket connection
        request_data: Client request data
        connection_id: Connection identifier
        active_connections: Dictionary of active connections
        chat_service: ChatService instance
    """
    try:
        thread_id = active_connections[connection_id]["thread_id"]

        if not thread_id:
            await send_websocket_event(
                websocket,
                "interrupts_list",
                {"interrupts": [], "message": "No active thread"},
            )
            return

        service_interrupts = await chat_service.get_interrupts(thread_id)
        pending_interrupts = active_connections[connection_id]["pending_interrupts"]

        await send_websocket_event(
            websocket,
            "interrupts_list",
            {
                "thread_id": thread_id,
                "interrupts": service_interrupts,
                "pending_count": len(pending_interrupts),
                "pending_ids": list(pending_interrupts.keys()),
            },
        )

    except Exception as e:
        await send_websocket_event(
            websocket,
            "error",
            {
                "message": f"Failed to get interrupts: {str(e)}",
                "error_type": type(e).__name__,
            },
        )


async def handle_streaming_event(
    websocket: WebSocket,
    event: Dict[str, Any],
    connection_id: str,
    active_connections: Dict[str, Dict],
    resumed: bool = False,
) -> None:
    """Handle individual streaming events from chat service.

    Args:
        websocket: WebSocket connection
        event: Event data from chat service
        connection_id: Connection identifier
        active_connections: Dictionary of active connections
        resumed: Whether this is from a resumed interrupt
    """
    event_type = event.get("type")

    if event_type == "ai_token":
        await send_websocket_event(
            websocket,
            "ai_token",
            {
                "content": event["content"],
                "thread_id": event["thread_id"],
                "metadata": event.get("metadata", {}),
                "resumed": resumed,
            },
        )
    elif event_type == "interrupt_detected":
        interrupt_id = event["interrupt_id"]
        question_data = event["question_data"]
        active_connections[connection_id]["pending_interrupts"][interrupt_id] = {
            "question_data": question_data,
        }
        await send_websocket_event(
            websocket,
            "interrupt_detected",
            {
                "interrupt_id": interrupt_id,
                "thread_id": event["thread_id"],
                "question_data": question_data,
                "resumable": event.get("resumable", True),
            },
        )
    elif event_type == "question_token":
        await send_websocket_event(
            websocket,
            "question_token",
            {"content": event["content"], "thread_id": event["thread_id"]},
        )
    elif event_type == "state_update":
        await send_websocket_event(
            websocket,
            "state_update",
            {
                "thread_id": event["thread_id"],
                "state_keys": event["state_keys"],
                "has_interrupt": event["has_interrupt"],
            },
        )
    elif event_type == "error":
        await send_websocket_event(
            websocket,
            "error",
            {
                "message": event["error"],
                "thread_id": event["thread_id"],
                "error_type": event.get("error_type", "UnknownError"),
            },
        )
