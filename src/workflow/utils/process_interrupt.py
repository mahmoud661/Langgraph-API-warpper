"""Utility to normalize interrupt objects into serializable events."""
from typing import Any


def process_interrupt(interrupt: Any, thread_id: str) -> dict[str, Any]:
    """Process single interrupt object into event dictionary.

    Args:
        interrupt: The interrupt object emitted by LangGraph.
        thread_id: The conversation thread id.

    Returns:
        A standardized interrupt event dictionary.
    """
    return {
        "type": "interrupt_detected",
        "interrupt_id": getattr(interrupt, 'id', str(interrupt)),
        "thread_id": thread_id,
        "question_data": getattr(interrupt, 'value', interrupt),
        "resumable": getattr(interrupt, 'resumable', True),
        "namespace": getattr(interrupt, 'ns', [])
    }
