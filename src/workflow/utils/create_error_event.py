"""Utility to build standardized error events for streaming."""
from typing import Any


def create_error_event(thread_id: str, error: Exception, context: str = "") -> dict[str, Any]:
    """Create standardized error event.

    Args:
        thread_id: The conversation thread id.
        error: The exception encountered.
        context: Optional context string to prefix the error message.

    Returns:
        A dict describing the error in a consistent, serializable format.
    """
    error_msg = f"{context}: {str(error)}" if context else str(error)
    return {
        "type": "error",
        "thread_id": thread_id,
        "error": error_msg,
        "error_type": type(error).__name__
    }
