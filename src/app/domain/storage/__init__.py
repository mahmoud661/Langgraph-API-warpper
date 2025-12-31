"""Storage domain types and protocols."""

from .protocol import (
    BackendFactory,
    BackendProtocol,
    SandboxBackendProtocol,
    BACKEND_TYPES,
)
from .types import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileOperationError,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)

__all__ = [
    "BackendFactory",
    "BackendProtocol",
    "SandboxBackendProtocol",
    "BACKEND_TYPES",
    "EditResult",
    "ExecuteResponse",
    "FileDownloadResponse",
    "FileInfo",
    "FileOperationError",
    "FileUploadResponse",
    "GrepMatch",
    "WriteResult",
]
