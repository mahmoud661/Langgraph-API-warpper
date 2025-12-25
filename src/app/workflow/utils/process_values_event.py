"""Utilities for processing 'values' stream events like interrupts and state updates."""
from typing import Any

from .process_interrupt import process_interrupt


def process_values_event(chunk: Any, thread_id: str) -> list[dict[str, Any]]:
    """Process values event for interrupts and state updates.

    Args:
        chunk: The streamed values dict from LangGraph.
        thread_id: The conversation thread id.

    Returns:
        A list of event dictionaries derived from the values update.
    """
    events: list[dict[str, Any]] = []

    if not isinstance(chunk, dict):
        return events

    # Handle interrupts
    if "__interrupt__" in chunk:
        interrupts = chunk["__interrupt__"]
        if isinstance(interrupts, (list, tuple)):
            for interrupt in interrupts:
                events.append(process_interrupt(interrupt, thread_id))

    # Add state update event
    events.append({
        "type": "state_update",
        "thread_id": thread_id,
        "state_keys": list(chunk.keys()),
        "has_interrupt": "__interrupt__" in chunk
    })

    return events
