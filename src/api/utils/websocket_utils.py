"""WebSocket utilities for connection management and message handling."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import WebSocket

from src.domain.chat_content import (
    AudioContent,
    ContentBlock,
    FileContent,
    ImageContent,
    TextContent,
)


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


def serialize_for_json(obj: Any) -> Any:
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
        return {k: serialize_for_json(v) for k, v in obj.__dict__.items()}
    elif isinstance(obj, dict):
        return {k: serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [serialize_for_json(item) for item in obj]
    else:
        return obj


async def send_websocket_event(
    websocket: WebSocket, event_type: str, data: dict
) -> None:
    """Send structured event to WebSocket client.

    Args:
        websocket: WebSocket connection
        event_type: Type of event
        data: Event data dictionary
    """
    try:
        event = {"event": event_type}
        event.update(data)
        serialized_event = serialize_for_json(event)
        await websocket.send_text(json.dumps(serialized_event))
    except Exception as e:
        print(f"Failed to send event {event_type}: {e}")


def generate_connection_id() -> str:
    """Generate a unique connection ID.

    Returns:
        Unique connection ID string
    """
    return str(uuid.uuid4())


def create_connection_data(websocket: WebSocket) -> Dict[str, Any]:
    """Create initial connection data structure.

    Args:
        websocket: WebSocket connection

    Returns:
        Dictionary containing connection data
    """
    return {
        "websocket": websocket,
        "thread_id": None,
        "pending_interrupts": {},
    }


def generate_thread_id() -> str:
    """Generate a unique thread ID.

    Returns:
        Unique thread ID string
    """
    return str(uuid.uuid4())
