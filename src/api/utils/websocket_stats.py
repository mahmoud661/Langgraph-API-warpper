"""WebSocket connection statistics utilities."""

import asyncio
import json
from typing import Dict

from fastapi import WebSocket, WebSocketDisconnect


async def handle_connection_stats(
    websocket: WebSocket, active_connections: Dict[str, Dict]
) -> None:
    """Handle connection statistics WebSocket.

    Args:
        websocket: WebSocket connection
        active_connections: Dictionary of active connections
    """
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
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        pass
