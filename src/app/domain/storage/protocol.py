"""Storage backend protocol (domain interface)."""

import abc
import asyncio
from collections.abc import Callable
from typing import TypeAlias

from .types import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)


class BackendProtocol(abc.ABC):
    """Protocol for pluggable memory backends (single, unified).

    Backends can store files in different locations (state, filesystem, database, etc.)
    and provide a uniform interface for file operations.

    All file data is represented as dicts with the following structure:
    {
        "content": list[str], # Lines of text content
        "created_at": str, # ISO format timestamp
        "modified_at": str, # ISO format timestamp
    }
    """

    def ls_info(self, path: str) -> list[FileInfo]:
        """List all files in a directory with metadata.

        Args:
            path: Absolute path to the directory to list. Must start with '/'.

        Returns:
            List of FileInfo dicts containing file metadata:

            - `path` (required): Absolute file path
            - `is_dir` (optional): True if directory
            - `size` (optional): File size in bytes
            - `modified_at` (optional): ISO 8601 timestamp
        """

    async def als_info(self, path: str) -> list[FileInfo]:
        """Async version of ls_info."""
        return await asyncio.to_thread(self.ls_info, path)

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read file content with line numbers.

        Args:
            file_path: Absolute path to the file to read. Must start with '/'.
            offset: Line number to start reading from (0-indexed). Default: 0.
            limit: Maximum number of lines to read. Default: 2000.

        Returns:
            String containing file content formatted with line numbers (cat -n format),
            starting at line 1. Lines longer than 2000 characters are truncated.

            Returns an error string if the file doesn't exist or can't be read.

        !!! note
            - Use pagination (offset/limit) for large files to avoid context overflow
            - First scan: `read(path, limit=100)` to see file structure
            - Read more: `read(path, offset=100, limit=200)` for next section
            - ALWAYS read a file before editing it
            - If file exists but is empty, you'll receive a system reminder warning
        """

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Async version of read."""
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Search for a literal text pattern in files.

        Args:
            pattern: Literal string to search for (NOT regex).
                     Performs exact substring matching within file content.
                     Example: "TODO" matches any line containing "TODO"

            path: Optional directory path to search in.
                  If None, searches in current working directory.
                  Example: "/workspace/src"

            glob: Optional glob pattern to filter which FILES to search.
                  Filters by filename/path, not content.
                  Supports standard glob wildcards:
                  - `*` matches any characters in filename
                  - `**` matches any directories recursively
                  - `?` matches single character
                  - `[abc]` matches one character from set

        Examples:
                  - "*.py" - only search Python files
                  - "**/*.txt" - search all .txt files recursively
                  - "src/**/*.js" - search JS files under src/
                  - "test[0-9].txt" - search test0.txt, test1.txt, etc.

        Returns:
            On success: list[GrepMatch] with structured results containing:
                - path: Absolute file path
                - line: Line number (1-indexed)
                - text: Full line content containing the match

            On error: str with error message (e.g., invalid path, permission denied)
        """

    async def agrep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Async version of grep_raw."""
        return await asyncio.to_thread(self.grep_raw, pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern with wildcards to match file paths.
                     Supports standard glob syntax:
                     - `*` matches any characters within a filename/directory
                     - `**` matches any directories recursively
                     - `?` matches a single character
                     - `[abc]` matches one character from set

            path: Base directory to search from. Default: "/" (root).
                  The pattern is applied relative to this path.

        Returns:
            list of FileInfo
        """

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Async version of glob_info."""
        return await asyncio.to_thread(self.glob_info, pattern, path)

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """Write content to a new file in the filesystem, error if file exists.

        Args:
            file_path: Absolute path where the file should be created.
                       Must start with '/'.
            content: String content to write to the file.

        Returns:
            WriteResult
        """

    async def awrite(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:
        """Async version of write."""
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Perform exact string replacements in an existing file.

        Args:
            file_path: Absolute path to the file to edit. Must start with '/'.
            old_string: Exact string to search for and replace.
                       Must match exactly including whitespace and indentation.
            new_string: String to replace old_string with.
                       Must be different from old_string.
            replace_all: If True, replace all occurrences. If False (default),
                        old_string must be unique in the file or the edit fails.

        Returns:
            EditResult
        """

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Async version of edit."""
        return await asyncio.to_thread(
            self.edit, file_path, old_string, new_string, replace_all
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload multiple files to the sandbox.

        This API is designed to allow developers to use it either directly or
        by exposing it to LLMs via custom tools.

        Args:
            files: List of (path, content) tuples to upload.

        Returns:
            List of FileUploadResponse objects, one per input file.
            Response order matches input order (response[i] for files[i]).
            Check the error field to determine success/failure per file.

        Examples:
            ```python
            responses = sandbox.upload_files(
                [
                    ("/app/config.json", b"{...}"),
                    ("/app/data.txt", b"content"),
                ]
            )
            ```
        """

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        """Async version of upload_files."""
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download multiple files from the sandbox.

        This API is designed to allow developers to use it either directly or
        by exposing it to LLMs via custom tools.

        Args:
            paths: List of file paths to download.

        Returns:
            List of FileDownloadResponse objects, one per input path.
            Response order matches input order (response[i] for paths[i]).
            Check the error field to determine success/failure per file.
        """

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Async version of download_files."""
        return await asyncio.to_thread(self.download_files, paths)


class SandboxBackendProtocol(BackendProtocol):
    """Protocol for sandboxed backends with isolated runtime.

    Sandboxed backends run in isolated environments (e.g., separate processes,
    containers) and communicate via defined interfaces.
    """

    def execute(
        self,
        command: str,
    ) -> ExecuteResponse:
        """Execute a command in the process.

        Simplified interface optimized for LLM consumption.

        Args:
            command: Full shell command string to execute.

        Returns:
            ExecuteResponse with combined output, exit code, optional signal, and truncation flag.
        """

    async def aexecute(
        self,
        command: str,
    ) -> ExecuteResponse:
        """Async version of execute."""
        return await asyncio.to_thread(self.execute, command)

    @property
    def id(self) -> str:
        """Unique identifier for the sandbox backend instance."""


# Note: BackendFactory moved to infrastructure layer to avoid ToolRuntime dependency in domain
BackendFactory: TypeAlias = Callable[[object], BackendProtocol]
BACKEND_TYPES = BackendProtocol | BackendFactory
