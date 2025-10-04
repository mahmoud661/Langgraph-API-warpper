"""WebSocket Chat Controller module."""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, List

from fastapi import WebSocket, WebSocketDisconnect

from src.app.services.chat_service import ChatService
from src.domain.chat_content import (
    AudioContent,
    ContentBlock,
    FileContent,
    ImageContent,
    TextContent,
)


class WebSocketChatController:
    """Controller for handling WebSocket chat operations."""

    def __init__(self, chat_service: ChatService):
        """Initialize the WebSocket chat controller.

        Args:
            chat_service: ChatService instance
        """
        self.chat_service = chat_service
        self.active_connections: Dict[str, Dict] = {}

    def parse_content_blocks(self, content_data: list) -> List[ContentBlock]:
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

    def serialize_for_json(self, obj):
        """Convert objects to JSON-serializable format.

        Args:
            obj: Object to serialize

        Returns:
            JSON-serializable object
        """
        if obj is None:
            return None
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, "__dict__"):
            return {k: self.serialize_for_json(v) for k, v in obj.__dict__.items()}
        elif isinstance(obj, dict):
            return {k: self.serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self.serialize_for_json(item) for item in obj]
        else:
            return obj

    async def send_event(self, websocket: WebSocket, event_type: str, data: dict):
        """Send structured event to client.

        Args:
            websocket: WebSocket connection
            event_type: Type of event
            data: Event data dictionary
        """
        try:
            event = {"event": event_type}
            event.update(data)
            serialized_event = self.serialize_for_json(event)
            await websocket.send_text(json.dumps(serialized_event))
        except Exception as e:
            print(f"Failed to send event {event_type}: {e}")

    async def handle_unified_chat(self, websocket: WebSocket):
        """Handle unified WebSocket chat connection.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()

        connection_id = str(uuid.uuid4())
        self.active_connections[connection_id] = {
            "websocket": websocket,
            "thread_id": None,
            "pending_interrupts": {},
        }

        try:
            await self.send_event(
                websocket,
                "connection_established",
                {
                    "connection_id": connection_id,
                    "message": "Connected to unified chat system",
                },
            )

            while True:
                data = await websocket.receive_text()
                request_data = json.loads(data)
                action = request_data.get("action")

                if action == "send_message":
                    await self.handle_send_message(
                        websocket, request_data, connection_id
                    )
                elif action == "resume_interrupt":
                    await self.handle_resume_interrupt(
                        websocket, request_data, connection_id
                    )
                elif action == "cancel_interrupt":
                    await self.handle_cancel_interrupt(
                        websocket, request_data, connection_id
                    )
                elif action == "get_interrupts":
                    await self.handle_get_interrupts(
                        websocket, request_data, connection_id
                    )
                else:
                    await self.send_event(
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
            await self.send_event(
                websocket,
                "error",
                {
                    "message": f"Unexpected error: {str(e)}",
                    "error_type": type(e).__name__,
                },
            )
        finally:
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]

    async def handle_send_message(
        self, websocket: WebSocket, request_data: dict, connection_id: str
    ):
        """Handle send_message WebSocket action.

        Args:
            websocket: WebSocket connection
            request_data: Client request data
            connection_id: Connection identifier
        """
        try:
            content_data = request_data.get("content", [])
            thread_id = request_data.get("thread_id") or str(uuid.uuid4())

            self.active_connections[connection_id]["thread_id"] = thread_id
            content_blocks = self.parse_content_blocks(content_data)

            await self.send_event(
                websocket,
                "message_started",
                {"thread_id": thread_id, "message": "Processing your message..."},
            )

            async for event in self.chat_service.stream_message(
                content=content_blocks, thread_id=thread_id
            ):
                event_type = event.get("type")

                if event_type == "ai_token":
                    await self.send_event(
                        websocket,
                        "ai_token",
                        {
                            "content": event["content"],
                            "thread_id": event["thread_id"],
                            "metadata": event.get("metadata", {}),
                        },
                    )
                elif event_type == "interrupt_detected":
                    interrupt_id = event["interrupt_id"]
                    question_data = event["question_data"]
                    self.active_connections[connection_id]["pending_interrupts"][
                        interrupt_id
                    ] = {
                        "question_data": question_data,
                    }
                    await self.send_event(
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
                    await self.send_event(
                        websocket,
                        "question_token",
                        {"content": event["content"], "thread_id": event["thread_id"]},
                    )
                elif event_type == "state_update":
                    await self.send_event(
                        websocket,
                        "state_update",
                        {
                            "thread_id": event["thread_id"],
                            "state_keys": event["state_keys"],
                            "has_interrupt": event["has_interrupt"],
                        },
                    )
                elif event_type == "error":
                    await self.send_event(
                        websocket,
                        "error",
                        {
                            "message": event["error"],
                            "thread_id": event["thread_id"],
                            "error_type": event.get("error_type", "UnknownError"),
                        },
                    )

            if not self.active_connections[connection_id]["pending_interrupts"]:
                await self.send_event(
                    websocket,
                    "message_complete",
                    {"thread_id": thread_id, "status": "completed"},
                )

        except Exception as e:
            await self.send_event(
                websocket,
                "error",
                {
                    "message": f"Failed to process message: {str(e)}",
                    "error_type": type(e).__name__,
                },
            )

    async def handle_resume_interrupt(
        self, websocket: WebSocket, request_data: dict, connection_id: str
    ):
        """Handle resume_interrupt WebSocket action.

        Args:
            websocket: WebSocket connection
            request_data: Client request data
            connection_id: Connection identifier
        """
        try:
            interrupt_id = request_data.get("interrupt_id")
            user_response = request_data.get("user_response")
            thread_id = self.active_connections[connection_id]["thread_id"]

            if not thread_id:
                await self.send_event(
                    websocket,
                    "error",
                    {"message": "No active thread for this connection"},
                )
                return

            if (
                interrupt_id
                in self.active_connections[connection_id]["pending_interrupts"]
            ):
                del self.active_connections[connection_id]["pending_interrupts"][
                    interrupt_id
                ]

            await self.send_event(
                websocket,
                "interrupt_resumed",
                {
                    "interrupt_id": interrupt_id,
                    "thread_id": thread_id,
                    "user_response": user_response,
                },
            )

            async for event in self.chat_service.resume_interrupt(
                thread_id=thread_id,
                interrupt_id=interrupt_id,
                user_response=user_response,
            ):
                event_type = event.get("type")

                if event_type == "ai_token":
                    await self.send_event(
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
                    new_interrupt_id = event["interrupt_id"]
                    question_data = event["question_data"]
                    self.active_connections[connection_id]["pending_interrupts"][
                        new_interrupt_id
                    ] = {
                        "question_data": question_data,
                    }
                    await self.send_event(
                        websocket,
                        "interrupt_detected",
                        {
                            "interrupt_id": new_interrupt_id,
                            "thread_id": event["thread_id"],
                            "question_data": question_data,
                        },
                    )
                elif event_type == "question_token":
                    await self.send_event(
                        websocket,
                        "question_token",
                        {"content": event["content"], "thread_id": event["thread_id"]},
                    )
                elif event_type == "error":
                    await self.send_event(
                        websocket,
                        "error",
                        {"message": event["error"], "thread_id": event["thread_id"]},
                    )

            if not self.active_connections[connection_id]["pending_interrupts"]:
                await self.send_event(
                    websocket,
                    "message_complete",
                    {"thread_id": thread_id, "status": "completed"},
                )

        except Exception as e:
            await self.send_event(
                websocket,
                "error",
                {
                    "message": f"Failed to resume interrupt: {str(e)}",
                    "error_type": type(e).__name__,
                },
            )

    async def handle_cancel_interrupt(
        self, websocket: WebSocket, request_data: dict, connection_id: str
    ):
        """Handle cancel_interrupt WebSocket action.

        Args:
            websocket: WebSocket connection
            request_data: Client request data
            connection_id: Connection identifier
        """
        try:
            interrupt_id = request_data.get("interrupt_id")
            thread_id = request_data.get("thread_id")

            if not thread_id:
                await self.send_event(
                    websocket,
                    "error",
                    {
                        "message": "thread_id is required for cancel_interrupt",
                        "error_type": "ValidationError",
                    },
                )
                return

            result = await self.chat_service.cancel_interrupt(thread_id, interrupt_id)

            if (
                interrupt_id
                and interrupt_id
                in self.active_connections[connection_id]["pending_interrupts"]
            ):
                del self.active_connections[connection_id]["pending_interrupts"][
                    interrupt_id
                ]

            if result["status"] == "cancelled":
                await self.send_event(
                    websocket,
                    "interrupt_cancelled",
                    {
                        "interrupt_id": interrupt_id,
                        "thread_id": thread_id,
                        "message": result["message"],
                    },
                )
            else:
                await self.send_event(
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
            await self.send_event(
                websocket,
                "error",
                {
                    "message": f"Failed to cancel interrupt: {str(e)}",
                    "error_type": type(e).__name__,
                },
            )

    async def handle_get_interrupts(
        self, websocket: WebSocket, request_data: dict, connection_id: str
    ):
        """Handle get_interrupts WebSocket action.

        Args:
            websocket: WebSocket connection
            request_data: Client request data
            connection_id: Connection identifier
        """
        try:
            thread_id = self.active_connections[connection_id]["thread_id"]

            if not thread_id:
                await self.send_event(
                    websocket,
                    "interrupts_list",
                    {"interrupts": [], "message": "No active thread"},
                )
                return

            service_interrupts = await self.chat_service.get_interrupts(thread_id)
            pending_interrupts = self.active_connections[connection_id][
                "pending_interrupts"
            ]

            await self.send_event(
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
            await self.send_event(
                websocket,
                "error",
                {
                    "message": f"Failed to get interrupts: {str(e)}",
                    "error_type": type(e).__name__,
                },
            )

    async def handle_connection_stats(self, websocket: WebSocket):
        """Handle connection statistics WebSocket.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()

        try:
            while True:
                stats = {
                    "active_connections": len(self.active_connections),
                    "connections": [
                        {
                            "connection_id": conn_id,
                            "thread_id": conn_data.get("thread_id"),
                            "pending_interrupts": len(
                                conn_data.get("pending_interrupts", {})
                            ),
                        }
                        for conn_id, conn_data in self.active_connections.items()
                    ],
                }

                await websocket.send_text(json.dumps(stats))
                await asyncio.sleep(5)

        except WebSocketDisconnect:
            pass
