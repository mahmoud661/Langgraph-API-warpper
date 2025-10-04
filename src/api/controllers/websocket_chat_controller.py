"""WebSocket Chat Controller module."""

import json
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect

from src.api.utils.websocket_handlers import (
    handle_cancel_interrupt_action,
    handle_get_interrupts_action,
    handle_resume_interrupt_action,
    handle_send_message_action,
)
from src.api.utils.websocket_stats import handle_connection_stats
from src.api.utils.websocket_utils import (
    create_connection_data,
    generate_connection_id,
    send_websocket_event,
)
from src.app.services.chat_service import ChatService


class WebSocketChatController:
    """Controller for handling WebSocket chat operations."""

    def __init__(self, chat_service: ChatService):
        """Initialize the WebSocket chat controller.

        Args:
            chat_service: ChatService instance
        """
        self.chat_service = chat_service
        self.active_connections: Dict[str, Dict] = {}

    async def handle_unified_chat(self, websocket: WebSocket):
        """Handle unified WebSocket chat connection.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()

        connection_id = generate_connection_id()
        self.active_connections[connection_id] = create_connection_data(websocket)

        try:
            await send_websocket_event(
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
                    await handle_send_message_action(
                        websocket,
                        request_data,
                        connection_id,
                        self.active_connections,
                        self.chat_service,
                    )
                elif action == "resume_interrupt":
                    await handle_resume_interrupt_action(
                        websocket,
                        request_data,
                        connection_id,
                        self.active_connections,
                        self.chat_service,
                    )
                elif action == "cancel_interrupt":
                    await handle_cancel_interrupt_action(
                        websocket,
                        request_data,
                        connection_id,
                        self.active_connections,
                        self.chat_service,
                    )
                elif action == "get_interrupts":
                    await handle_get_interrupts_action(
                        websocket,
                        request_data,
                        connection_id,
                        self.active_connections,
                        self.chat_service,
                    )
                else:
                    await send_websocket_event(
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
            await send_websocket_event(
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

    async def handle_connection_stats(self, websocket: WebSocket):
        """Handle connection statistics WebSocket.

        Args:
            websocket: WebSocket connection
        """
        await handle_connection_stats(websocket, self.active_connections)
