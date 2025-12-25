"""Store backend for persistent file storage using LangGraph Store."""

import asyncio
import json
import re
from typing import Any

from langchain_core.stores import BaseStore
from wcmatch import glob as wcglob

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


class StoreBackend(BackendProtocol):
    """Backend that stores files persistently using LangGraph Store."""

    def __init__(self, store: BaseStore, namespace: tuple[str, ...] = ("files",)):
        """Initialize store backend.

        Args:
            store: LangGraph store instance for persistence
            namespace: Namespace tuple for organizing files in store
        """
        self.store = store
        self.namespace = namespace

    def _get_key(self, file_path: str) -> str:
        """Convert file path to store key."""
        return f"file:{file_path}"

    def _get_metadata_key(self, file_path: str) -> str:
        """Convert file path to metadata store key."""
        return f"meta:{file_path}"

    def _list_all_files(self) -> list[str]:
        """List all file paths in store."""
        try:
            # Get all keys with file: prefix
            all_items = self.store.mget(self.namespace, [])
            file_paths = []
            for key, _ in all_items:
                if key.startswith("file:"):
                    file_paths.append(key[5:])  # Remove "file:" prefix
            return sorted(file_paths)
        except Exception:
            return []

    def ls_info(self, directory: str = ".") -> list[FileInfo]:
        """List files in directory with metadata.

        Args:
            directory: Directory path

        Returns:
            List of FileInfo objects for each file/directory
        """
        all_files = self._list_all_files()

        # Normalize directory path
        if directory == ".":
            dir_prefix = ""
        else:
            dir_prefix = directory.rstrip("/") + "/"

        # Find immediate children
        children = set()
        for file_path in all_files:
            if not file_path.startswith(dir_prefix):
                continue

            relative = file_path[len(dir_prefix) :]
            if "/" in relative:
                # This is a subdirectory
                subdir = relative.split("/")[0]
                children.add((subdir, False))  # False = directory
            else:
                # This is a file
                children.add((relative, True))  # True = file

        results = []
        for name, is_file in sorted(children):
            full_path = f"{dir_prefix}{name}" if dir_prefix else name

            if is_file:
                # Get file size from metadata
                try:
                    meta_key = self._get_metadata_key(full_path)
                    metadata = self.store.mget([self.namespace], [meta_key])
                    size = metadata.get("size", 0) if metadata else 0
                except Exception:
                    size = 0

                results.append(
                    FileInfo(
                        path=full_path,
                        is_file=True,
                        size=size,
                    )
                )
            else:
                results.append(
                    FileInfo(
                        path=full_path,
                        is_file=False,
                        size=0,
                    )
                )

        return results

    def read(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        page_size: int | None = None,
        page: int | None = None,
    ) -> str:
        """Read file content with optional line range or pagination.

        Args:
            file_path: Path to file
            start_line: Starting line number (1-indexed, inclusive)
            end_line: Ending line number (1-indexed, inclusive)
            page_size: Number of lines per page
            page: Page number (1-indexed)

        Returns:
            File content as string, or error message
        """
        try:
            key = self._get_key(file_path)
            result = self.store.mget([self.namespace], [key])

            if not result or key not in result:
                return f"Error: File '{file_path}' not found"

            content = result[key]
            if not isinstance(content, str):
                return f"Error: Invalid file content for '{file_path}'"

            lines = content.splitlines(keepends=True)

            # Handle pagination
            if page_size is not None and page is not None:
                start_idx = (page - 1) * page_size
                end_idx = start_idx + page_size
                selected_lines = lines[start_idx:end_idx]
                return "".join(selected_lines)

            # Handle line range
            if start_line is not None or end_line is not None:
                start_idx = (start_line - 1) if start_line else 0
                end_idx = end_line if end_line else len(lines)
                selected_lines = lines[start_idx:end_idx]
                return "".join(selected_lines)

            return content
        except Exception as e:
            return f"Error: {str(e)}"

    def write(
        self,
        file_path: str,
        content: str,
        create_parents: bool = True,
    ) -> WriteResult:
        """Write content to file.

        Args:
            file_path: Path to file
            content: Content to write
            create_parents: Whether to create parent directories (ignored for store)

        Returns:
            WriteResult with success status and metadata
        """
        try:
            key = self._get_key(file_path)
            meta_key = self._get_metadata_key(file_path)

            # Store file content
            self.store.mset([(self.namespace, key, content)])

            # Store metadata
            lines_written = len(content.splitlines())
            metadata = {
                "size": len(content),
                "lines": lines_written,
            }
            self.store.mset([(self.namespace, meta_key, json.dumps(metadata))])

            return WriteResult(
                path=file_path,
                lines_written=lines_written,
                error=None,
            )
        except Exception:
            return WriteResult(
                path=file_path,
                lines_written=0,
                error="permission_denied",
            )

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Edit file by replacing old_string with new_string.

        Args:
            file_path: Path to file
            old_string: String to find and replace
            new_string: Replacement string
            replace_all: If True, replace all occurrences; if False, replace first only

        Returns:
            EditResult with number of replacements and status
        """
        try:
            # Read existing content
            content = self.read(file_path)
            if content.startswith("Error:"):
                return EditResult(
                    path=file_path,
                    replacements=0,
                    error="file_not_found",
                )

            if old_string not in content:
                return EditResult(
                    path=file_path,
                    replacements=0,
                    error="pattern_not_found",
                )

            if replace_all:
                new_content = content.replace(old_string, new_string)
                replacements = content.count(old_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
                replacements = 1

            # Write updated content
            result = self.write(file_path, new_content)
            if result.error:
                return EditResult(
                    path=file_path,
                    replacements=0,
                    error=result.error,
                )

            return EditResult(
                path=file_path,
                replacements=replacements,
                error=None,
            )
        except Exception:
            return EditResult(
                path=file_path,
                replacements=0,
                error="permission_denied",
            )

    def glob_info(self, pattern: str, case_sensitive: bool = True) -> list[FileInfo]:
        """Find files matching glob pattern.

        Args:
            pattern: Glob pattern (supports **, *, ?, [], {})
            case_sensitive: Whether pattern matching is case-sensitive

        Returns:
            List of FileInfo objects for matching files
        """
        try:
            all_files = self._list_all_files()

            flags = wcglob.GLOBSTAR | wcglob.BRACE
            if not case_sensitive:
                flags |= wcglob.IGNORECASE

            results = []
            for file_path in all_files:
                if wcglob.globmatch(file_path, pattern, flags=flags):
                    # Get file size from metadata
                    try:
                        meta_key = self._get_metadata_key(file_path)
                        metadata_json = self.store.mget([self.namespace], [meta_key])
                        if metadata_json and meta_key in metadata_json:
                            metadata = json.loads(metadata_json[meta_key])
                            size = metadata.get("size", 0)
                        else:
                            size = 0
                    except Exception:
                        size = 0

                    results.append(
                        FileInfo(
                            path=file_path,
                            is_file=True,
                            size=size,
                        )
                    )

            return results
        except Exception:
            return []

    def grep_raw(
        self,
        pattern: str,
        file_pattern: str = "**/*",
        is_regex: bool = False,
        case_sensitive: bool = True,
        max_results: int = 100,
    ) -> list[GrepMatch]:
        """Search for pattern in files.

        Args:
            pattern: Search pattern (literal string or regex)
            file_pattern: Glob pattern for files to search
            is_regex: Whether pattern is a regex
            case_sensitive: Whether search is case-sensitive
            max_results: Maximum number of matches to return

        Returns:
            List of GrepMatch objects with file paths and matching lines
        """
        try:
            # Get files matching the pattern
            files = self.glob_info(file_pattern, case_sensitive=True)

            # Compile search pattern
            if is_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                search_re = re.compile(pattern, flags)
            else:
                flags = 0 if case_sensitive else re.IGNORECASE
                escaped_pattern = re.escape(pattern)
                search_re = re.compile(escaped_pattern, flags)

            results = []
            for file_info in files:
                if len(results) >= max_results:
                    break

                try:
                    content = self.read(file_info.path)
                    if content.startswith("Error:"):
                        continue

                    lines = content.splitlines()
                    for line_num, line in enumerate(lines, start=1):
                        if len(results) >= max_results:
                            break

                        if search_re.search(line):
                            results.append(
                                GrepMatch(
                                    path=file_info.path,
                                    line_number=line_num,
                                    line_content=line,
                                )
                            )
                except Exception:
                    continue

            return results
        except Exception:
            return []

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files to store.

        Args:
            files: List of (path, content) tuples

        Returns:
            List of FileUploadResponse objects with status for each file
        """
        results = []
        for path, content in files:
            try:
                decoded = content.decode("utf-8")
                result = self.write(path, decoded)
                if result.error:
                    results.append(
                        FileUploadResponse(path=path, error="permission_denied")
                    )
                else:
                    results.append(FileUploadResponse(path=path, error=None))
            except Exception:
                results.append(FileUploadResponse(path=path, error="invalid_path"))
        return results

    async def aupload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        return await asyncio.to_thread(self.upload_files, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from store.

        Args:
            paths: List of file paths to download

        Returns:
            List of FileDownloadResponse objects with content for each file
        """
        results = []
        for path in paths:
            content_str = self.read(path)
            if content_str.startswith("Error"):
                results.append(
                    FileDownloadResponse(
                        path=path, content=None, error="file_not_found"
                    )
                )
            else:
                results.append(
                    FileDownloadResponse(
                        path=path, content=content_str.encode("utf-8"), error=None
                    )
                )
        return results

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_files, paths)
