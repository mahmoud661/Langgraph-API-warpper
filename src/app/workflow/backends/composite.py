"""Composite backend for routing files to different backends based on path patterns."""

import asyncio
from typing import Literal

from .protocol import (
    BackendProtocol,
    EditResult,
    FileInfo,
    FileOperationError,
    GrepMatch,
    WriteResult,
    FileUploadResponse,
    FileDownloadResponse,
)


class CompositeBackend(BackendProtocol):
    """Backend that routes file operations to different backends based on path patterns."""

    def __init__(
        self,
        default: BackendProtocol,
        routes: dict[str, BackendProtocol] | None = None,
    ):
        """Initialize composite backend.

        Args:
            default: Default backend for files not matching any route
            routes: Dictionary mapping path prefixes to backends.
                    For example: {"temp/": temp_backend, "cache/": cache_backend}
        """
        self.default = default
        self.routes = routes or {}

    def _get_backend(self, file_path: str) -> BackendProtocol:
        """Get the appropriate backend for a file path."""
        for prefix, backend in self.routes.items():
            if file_path.startswith(prefix):
                return backend
        return self.default

    def ls_info(self, directory: str = ".") -> list[FileInfo]:
        """List files in directory with metadata.

        For composite backend, this queries all backends and merges results.

        Args:
            directory: Directory path

        Returns:
            List of FileInfo objects from all backends
        """
        # Check if directory matches a specific route
        backend = self._get_backend(directory)
        if backend != self.default:
            return backend.ls_info(directory)

        # Query all backends and merge results
        all_results = []

        # Get from default backend
        all_results.extend(self.default.ls_info(directory))

        # Get from routed backends
        for prefix, backend in self.routes.items():
            if directory == "." or prefix.startswith(directory):
                results = backend.ls_info(directory)
                # Filter to only include files under this prefix
                for item in results:
                    if item.path.startswith(prefix):
                        all_results.append(item)

        # Deduplicate by path
        seen = set()
        unique_results = []
        for item in all_results:
            if item.path not in seen:
                seen.add(item.path)
                unique_results.append(item)

        return sorted(unique_results, key=lambda x: x.path)

    def read(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        page_size: int | None = None,
        page: int | None = None,
    ) -> str:
        """Read file content with optional line range or pagination."""
        backend = self._get_backend(file_path)
        return backend.read(file_path, start_line, end_line, page_size, page)

    def write(
        self,
        file_path: str,
        content: str,
        create_parents: bool = True,
    ) -> WriteResult:
        """Write content to file."""
        backend = self._get_backend(file_path)
        return backend.write(file_path, content, create_parents)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit file by replacing old_string with new_string."""
        backend = self._get_backend(file_path)
        return backend.edit(file_path, old_string, new_string, replace_all)

    def glob_info(self, pattern: str, case_sensitive: bool = True) -> list[FileInfo]:
        """Find files matching glob pattern.

        For composite backend, this queries all backends and merges results.

        Args:
            pattern: Glob pattern (supports **, *, ?, [], {})
            case_sensitive: Whether pattern matching is case-sensitive

        Returns:
            List of FileInfo objects from all backends
        """
        all_results = []

        # Query default backend
        all_results.extend(self.default.glob_info(pattern, case_sensitive))

        # Query routed backends
        for prefix, backend in self.routes.items():
            results = backend.glob_info(pattern, case_sensitive)
            all_results.extend(results)

        # Deduplicate by path
        seen = set()
        unique_results = []
        for item in all_results:
            if item.path not in seen:
                seen.add(item.path)
                unique_results.append(item)

        return sorted(unique_results, key=lambda x: x.path)

    def grep_raw(
        self,
        pattern: str,
        file_pattern: str = "**/*",
        is_regex: bool = False,
        case_sensitive: bool = True,
        max_results: int = 100,
    ) -> list[GrepMatch]:
        """Search for pattern in files.

        For composite backend, this queries all backends and merges results.

        Args:
            pattern: Search pattern (literal string or regex)
            file_pattern: Glob pattern for files to search
            is_regex: Whether pattern is a regex
            case_sensitive: Whether search is case-sensitive
            max_results: Maximum number of matches to return

        Returns:
            List of GrepMatch objects from all backends
        """
        all_results = []

        # Query default backend
        results = self.default.grep_raw(
            pattern, file_pattern, is_regex, case_sensitive, max_results
        )
        all_results.extend(results)

        if len(all_results) >= max_results:
            return all_results[:max_results]

        # Query routed backends
        for prefix, backend in self.routes.items():
            remaining = max_results - len(all_results)
            if remaining <= 0:
                break

            results = backend.grep_raw(
                pattern, file_pattern, is_regex, case_sensitive, remaining
            )
            all_results.extend(results)

        return all_results[:max_results]

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files to appropriate backends based on paths.

        Args:
            files: List of (path, content) tuples

        Returns:
            List of FileUploadResponse objects with status for each file
        """
        # Group files by backend
        backend_files: dict[BackendProtocol, list[tuple[str, bytes]]] = {}
        for path, content in files:
            backend = self._get_backend(path)
            if backend not in backend_files:
                backend_files[backend] = []
            backend_files[backend].append((path, content))

        # Upload to each backend
        all_results = []
        for backend, backend_file_list in backend_files.items():
            results = backend.upload_files(backend_file_list)
            all_results.extend(results)

        return all_results

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from appropriate backends based on paths.

        Args:
            paths: List of file paths to download

        Returns:
            List of FileDownloadResponse objects with content for each file
        """
        # Group paths by backend
        backend_paths: dict[BackendProtocol, list[str]] = {}
        for path in paths:
            backend = self._get_backend(path)
            if backend not in backend_paths:
                backend_paths[backend] = []
            backend_paths[backend].append(path)

        # Download from each backend
        all_results = []
        for backend, backend_path_list in backend_paths.items():
            results = backend.download_files(backend_path_list)
            all_results.extend(results)

        return all_results

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_files, paths)
