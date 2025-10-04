"""Unified WebSocket Chat - Handles both AI responses and interactive questions."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.domain.chat_content import (
    AudioContent,
    ContentBlock,
    FileContent,
    ImageContent,
    TextContent,
)

router = APIRouter(prefix="/ws", tags=["websocket-chat"])

# Track active connections and their states
active_connections: Dict[str, Dict] = {}


def parse_content_blocks(content_data: list) -> List[ContentBlock]:
    """Parse Content Blocks into structured format.

    Args:
        content_data: Raw content data from client

    Returns:
        List of ContentBlock objects
    """
    content_blocks: List[ContentBlock] = []
    for item in content_data:
        if isinstance(item, dict):
            content_type = item.get("type")
            if content_type == "text":
                content_blocks.append(TextContent(**item))
            elif content_type == "image":
                content_blocks.append(ImageContent(**item))
            elif content_type == "file":
                content_blocks.append(FileContent(**item))
            elif content_type == "audio":
                content_blocks.append(AudioContent(**item))
            else:
                content_blocks.append(TextContent(data=str(item)))
        else:
            content_blocks.append(TextContent(data=str(item)))
    return content_blocks


def serialize_for_json(obj):
    """Convert objects to JSON-serializable format."""
    if obj is None:
        return None
    elif isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, "__dict__"):
        # Convert objects with attributes to dict
        return {k: serialize_for_json(v) for k, v in obj.__dict__.items()}
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    else:
        return obj


async def send_event(websocket: WebSocket, event_type: str, data: dict):
    """Send structured event to client.

    Args:
        websocket: WebSocket connection
        event_type: Type of event (ai_token, interrupt_detected, etc.)
        data: Event data dictionary
    """
    try:
        # Create the complete event object
        event = {
            "event": event_type,
        }
        # Merge data into event
        event.update(data)

        # Serialize the entire event object to handle any nested datetime objects
        serialized_event = serialize_for_json(event)

        await websocket.send_text(json.dumps(serialized_event))
    except Exception as e:
        print(f"Failed to send event {event_type}: {e}")


@router.websocket("/unified-chat")
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
    await websocket.accept()

    # Generate connection ID and initialize state
    connection_id = str(uuid.uuid4())
    active_connections[connection_id] = {
        "websocket": websocket,
        "thread_id": None,
        "pending_interrupts": {},
    }

    try:
        # Send connection established event
        await send_event(
            websocket,
            "connection_established",
            {
                "connection_id": connection_id,
                "message": "Connected to unified chat system",
            },
        )

        while True:
            # Receive message from client
            data = await websocket.receive_text()
            request_data = json.loads(data)

            action = request_data.get("action")
            chat_service = websocket.app.state.chat_service

            if action == "send_message":
                await handle_send_message(
                    websocket, request_data, chat_service, connection_id
                )

            elif action == "resume_interrupt":
                await handle_resume_interrupt(
                    websocket, request_data, chat_service, connection_id
                )

            elif action == "cancel_interrupt":
                await handle_cancel_interrupt(
                    websocket, request_data, chat_service, connection_id
                )

            elif action == "get_interrupts":
                await handle_get_interrupts(
                    websocket, request_data, chat_service, connection_id
                )

            else:
                await send_event(
                    websocket,
                    "error",
                    {
                        "message": f"Unknown action: {action}",
                        "supported_actions": [
                            "send_message",
                            "resume_interrupt",
                            "cancel_interrupt",
                            "get_interrupts",
                        ],
                    },
                )

    except WebSocketDisconnect:
        print(f"WebSocket connection {connection_id} disconnected")
    except Exception as e:
        await send_event(
            websocket,
            "error",
            {"message": f"Unexpected error: {str(e)}", "error_type": type(e).__name__},
        )
    finally:
        # Clean up connection
        if connection_id in active_connections:
            del active_connections[connection_id]


async def handle_send_message(
    websocket: WebSocket, request_data: dict, chat_service, connection_id: str
):
    """Handle send_message action with unified streaming.

    Args:
        websocket: WebSocket connection
        request_data: Client request data
        chat_service: ChatService instance
        connection_id: Connection identifier
    """
    try:
        # Extract message data
        content_data = request_data.get("content", [])
        thread_id = request_data.get("thread_id") or str(uuid.uuid4())

        # Update connection state
        active_connections[connection_id]["thread_id"] = thread_id

        # Parse content blocks
        content_blocks = parse_content_blocks(content_data)

        # Send message started event
        await send_event(
            websocket,
            "message_started",
            {"thread_id": thread_id, "message": "Processing your message..."},
        )

        # Start unified streaming using ChatService
        async for event in chat_service.stream_message(
            content=content_blocks, thread_id=thread_id
        ):
            event_type = event.get("type")

            if event_type == "ai_token":
                # Stream AI response tokens
                await send_event(
                    websocket,
                    "ai_token",
                    {
                        "content": event["content"],
                        "thread_id": event["thread_id"],
                        "metadata": event.get("metadata", {}),
                    },
                )

            elif event_type == "interrupt_detected":
                # Handle interrupt detection
                interrupt_id = event["interrupt_id"]
                question_data = event["question_data"]

                # Store interrupt in connection state
                active_connections[connection_id]["pending_interrupts"][
                    interrupt_id
                ] = {
                    "question_data": question_data,
                }

                await send_event(
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
                # Stream question tokens (from StreamWriter)
                await send_event(
                    websocket,
                    "question_token",
                    {"content": event["content"], "thread_id": event["thread_id"]},
                )

            elif event_type == "state_update":
                # Optional: Send state updates for debugging
                await send_event(
                    websocket,
                    "state_update",
                    {
                        "thread_id": event["thread_id"],
                        "state_keys": event["state_keys"],
                        "has_interrupt": event["has_interrupt"],
                    },
                )

            elif event_type == "error":
                # Handle streaming errors
                await send_event(
                    websocket,
                    "error",
                    {
                        "message": event["error"],
                        "thread_id": event["thread_id"],
                        "error_type": event.get("error_type", "UnknownError"),
                    },
                )

        # Send completion event if no interrupts pending
        if not active_connections[connection_id]["pending_interrupts"]:
            await send_event(
                websocket,
                "message_complete",
                {"thread_id": thread_id, "status": "completed"},
            )

    except Exception as e:
        await send_event(
            websocket,
            "error",
            {
                "message": f"Failed to process message: {str(e)}",
                "error_type": type(e).__name__,
            },
        )


async def handle_resume_interrupt(
    websocket: WebSocket, request_data: dict, chat_service, connection_id: str
):
    """Handle resume_interrupt action.

    Args:
        websocket: WebSocket connection
        request_data: Client request data
        chat_service: ChatService instance
        connection_id: Connection identifier
    """
    try:
        interrupt_id = request_data.get("interrupt_id")
        user_response = request_data.get("user_response")
        thread_id = active_connections[connection_id]["thread_id"]

        if not thread_id:
            await send_event(
                websocket, "error", {"message": "No active thread for this connection"}
            )
            return

        # Remove interrupt from pending list
        if interrupt_id in active_connections[connection_id]["pending_interrupts"]:
            del active_connections[connection_id]["pending_interrupts"][interrupt_id]

        await send_event(
            websocket,
            "interrupt_resumed",
            {
                "interrupt_id": interrupt_id,
                "thread_id": thread_id,
                "user_response": user_response,
            },
        )

        # Resume streaming using ChatService
        async for event in chat_service.resume_interrupt(
            thread_id=thread_id, interrupt_id=interrupt_id, user_response=user_response
        ):
            event_type = event.get("type")

            if event_type == "ai_token":
                await send_event(
                    websocket,
                    "ai_token",
                    {
                        "content": event["content"],
                        "thread_id": event["thread_id"],
                        "metadata": event.get("metadata", {}),
                        "resumed": True,
                    },
                )

            elif event_type == "interrupt_detected":
                # New interrupt after resume
                new_interrupt_id = event["interrupt_id"]
                question_data = event["question_data"]

                active_connections[connection_id]["pending_interrupts"][
                    new_interrupt_id
                ] = {
                    "question_data": question_data,
                }

                await send_event(
                    websocket,
                    "interrupt_detected",
                    {
                        "interrupt_id": new_interrupt_id,
                        "thread_id": event["thread_id"],
                        "question_data": question_data,
                    },
                )

            elif event_type == "question_token":
                await send_event(
                    websocket,
                    "question_token",
                    {"content": event["content"], "thread_id": event["thread_id"]},
                )

            elif event_type == "error":
                await send_event(
                    websocket,
                    "error",
                    {"message": event["error"], "thread_id": event["thread_id"]},
                )

        # Send completion if no more interrupts
        if not active_connections[connection_id]["pending_interrupts"]:
            await send_event(
                websocket,
                "message_complete",
                {"thread_id": thread_id, "status": "completed"},
            )

    except Exception as e:
        await send_event(
            websocket,
            "error",
            {
                "message": f"Failed to resume interrupt: {str(e)}",
                "error_type": type(e).__name__,
            },
        )


async def handle_cancel_interrupt(
    websocket: WebSocket, request_data: dict, chat_service, connection_id: str
):
    """Handle cancel_interrupt action.

    Args:
        websocket: WebSocket connection
        request_data: Client request data
        chat_service: ChatService instance
        connection_id: Connection identifier
    """
    try:
        interrupt_id = request_data.get("interrupt_id")
        thread_id = request_data.get("thread_id")

        if not thread_id:
            await send_event(
                websocket,
                "error",
                {
                    "message": "thread_id is required for cancel_interrupt",
                    "error_type": "ValidationError",
                },
            )
            return

        # Cancel the interrupt using ChatService
        result = await chat_service.cancel_interrupt(thread_id, interrupt_id)

        # Remove from local pending interrupts
        if (
            interrupt_id
            and interrupt_id in active_connections[connection_id]["pending_interrupts"]
        ):
            del active_connections[connection_id]["pending_interrupts"][interrupt_id]

        if result["status"] == "cancelled":
            await send_event(
                websocket,
                "interrupt_cancelled",
                {
                    "interrupt_id": interrupt_id,
                    "thread_id": thread_id,
                    "message": result["message"],
                },
            )
        else:
            await send_event(
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
        await send_event(
            websocket,
            "error",
            {
                "message": f"Failed to cancel interrupt: {str(e)}",
                "error_type": type(e).__name__,
            },
        )


async def handle_get_interrupts(
    websocket: WebSocket, request_data: dict, chat_service, connection_id: str
):
    """Handle get_interrupts action.

    Args:
        websocket: WebSocket connection
        request_data: Client request data
        chat_service: ChatService instance
        connection_id: Connection identifier
    """
    try:
        thread_id = active_connections[connection_id]["thread_id"]

        if not thread_id:
            await send_event(
                websocket,
                "interrupts_list",
                {"interrupts": [], "message": "No active thread"},
            )
            return

        # Get interrupts from ChatService and connection state
        service_interrupts = await chat_service.get_interrupts(thread_id)
        pending_interrupts = active_connections[connection_id]["pending_interrupts"]

        await send_event(
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
        await send_event(
            websocket,
            "error",
            {
                "message": f"Failed to get interrupts: {str(e)}",
                "error_type": type(e).__name__,
            },
        )


# Utility endpoint to get connection stats
@router.websocket("/stats")
async def connection_stats(websocket: WebSocket):
    """WebSocket endpoint for connection statistics."""
    await websocket.accept()

    try:
        while True:
            stats = {
                "active_connections": len(active_connections),
                "connections": [
                    {
                        "connection_id": conn_id,
                        "thread_id": conn_data.get("thread_id"),
                        "pending_interrupts": len(
                            conn_data.get("pending_interrupts", {})
                        ),
                    }
                    for conn_id, conn_data in active_connections.items()
                ],
            }

            await websocket.send_text(json.dumps(stats))
            await asyncio.sleep(5)  # Update every 5 seconds

    except WebSocketDisconnect:
        pass
