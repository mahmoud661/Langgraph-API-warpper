"""Filesystem state types (domain layer)."""

from typing import Annotated, NotRequired
from typing_extensions import TypedDict

from src.app.domain.workflow.state import AgentState


class FileData(TypedDict):
    """Data structure for storing file contents with metadata."""

    content: list[str]
    """Lines of the file."""

    created_at: str
    """ISO 8601 timestamp of file creation."""

    modified_at: str
    """ISO 8601 timestamp of last modification."""


def file_data_reducer(
    left: dict[str, FileData] | None, right: dict[str, FileData | None]
) -> dict[str, FileData]:
    """Reducer for merging file data state updates.

    Args:
        left: Current file data state (or None).
        right: New file data updates (value of None means delete).

    Returns:
        Merged file data dictionary.
    """
    if left is None:
        return {k: v for k, v in right.items() if v is not None}

    result = {**left}
    for key, value in right.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


class FilesystemState(AgentState):
    """State for the filesystem middleware."""

    files: Annotated[NotRequired[dict[str, FileData]], file_data_reducer]
    """Files in the filesystem."""
