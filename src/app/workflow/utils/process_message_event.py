"""Utilities related to processing message stream events."""
from typing import Any


def process_message_event(chunk: Any, thread_id: str, resumed: bool = False) -> dict[str, Any] | None:
    """Process message event for AI token streaming.

    Args:
        chunk: The streamed chunk, expected as (token, metadata).
        thread_id: The conversation thread id.
        resumed: Whether this message is emitted after a resume action.

    Returns:
        A dict event or None if the chunk isn't a token content message.
    """
    if not isinstance(chunk, (list, tuple)) or len(chunk) < 2:
        return None

    token, metadata = chunk
    if not (hasattr(token, 'content') and getattr(token, 'content', None)):
        return None

    result = {
        "type": "ai_token",
        "content": str(token.content),
        "thread_id": thread_id,
        "metadata": {
            "node": metadata.get("langgraph_node") if hasattr(metadata, 'get') else None,
            "step": metadata.get("langgraph_step") if hasattr(metadata, 'get') else None,
            "tags": metadata.get("tags", []) if hasattr(metadata, 'get') else []
        }
    }

    if resumed:
        result["resumed"] = True

    return result
