from collections.abc import Callable
from typing import TypeAlias

from langchain.tools import ToolRuntime

# Re-export from domain layer
from src.app.domain.storage import (
    BackendProtocol,
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileOperationError,
    FileUploadResponse,
    GrepMatch,
    SandboxBackendProtocol,
    WriteResult,
)

__all__ = [
    "BackendProtocol",
    "SandboxBackendProtocol",
    "EditResult",
    "ExecuteResponse",
    "FileDownloadResponse",
    "FileInfo",
    "FileOperationError",
    "FileUploadResponse",
    "GrepMatch",
    "WriteResult",
    "BackendFactory",
    "BACKEND_TYPES",
]

# Keep BackendFactory with ToolRuntime for backward compatibility
BackendFactory: TypeAlias = Callable[[ToolRuntime], BackendProtocol]
BACKEND_TYPES = BackendProtocol | BackendFactory
# Keep BackendFactory with ToolRuntime for backward compatibility
BackendFactory: TypeAlias = Callable[[ToolRuntime], BackendProtocol]
BACKEND_TYPES = BackendProtocol | BackendFactory
