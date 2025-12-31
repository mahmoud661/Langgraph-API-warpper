"""Path validation logic (domain layer)."""

import os
import re
from collections.abc import Sequence


def validate_path(path: str, *, allowed_prefixes: Sequence[str] | None = None) -> str:
    """Validate and normalize a virtual filesystem path.

    Args:
        path: The path to validate.
        allowed_prefixes: Optional list of allowed path prefixes.

    Returns:
        Normalized path starting with '/'.

    Raises:
        ValueError: If path contains traversal, Windows absolute paths, or invalid prefixes.
    """
    if ".." in path or path.startswith("~"):
        msg = f"Path traversal not allowed: {path}"
        raise ValueError(msg)

    # Reject Windows absolute paths (e.g., C:\..., D:/...)
    # This maintains consistency in virtual filesystem paths
    if re.match(r"^[a-zA-Z]:", path):
        msg = f"Windows absolute paths are not supported: {path}. Please use virtual paths starting with / (e.g., /workspace/file.txt)"
        raise ValueError(msg)

    normalized = os.path.normpath(path)
    normalized = normalized.replace("\\", "/")

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    if allowed_prefixes is not None and not any(
        normalized.startswith(prefix) for prefix in allowed_prefixes
    ):
        msg = f"Path must start with one of {allowed_prefixes}: {path}"
        raise ValueError(msg)

    return normalized
