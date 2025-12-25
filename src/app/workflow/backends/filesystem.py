"""Filesystem backend for disk-based file storage."""

import asyncio
import re
from pathlib import Path
from typing import Literal

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


class FilesystemBackend(BackendProtocol):
    """Backend that stores files on the local filesystem."""

    def __init__(self, root: str | Path):
        """Initialize filesystem backend.

        Args:
            root: Root directory for file storage
        """
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, file_path: str) -> Path:
        """Resolve file path relative to root and ensure it's within root."""
        try:
            full_path = (self.root / file_path).resolve()
            # Ensure the path is within root
            full_path.relative_to(self.root)
            return full_path
        except (ValueError, OSError):
            raise ValueError(f"Invalid path: {file_path}")

    def ls_info(self, directory: str = ".") -> list[FileInfo]:
        """List files in directory with metadata.

        Args:
            directory: Directory path relative to root

        Returns:
            List of FileInfo objects for each file/directory
        """
        try:
            dir_path = self._resolve_path(directory)
            if not dir_path.exists():
                return []
            if not dir_path.is_dir():
                return []

            results = []
            for item in sorted(dir_path.iterdir()):
                try:
                    rel_path = item.relative_to(self.root)
                    is_file = item.is_file()
                    size = item.stat().st_size if is_file else 0

                    results.append(
                        FileInfo(
                            path=str(rel_path),
                            is_file=is_file,
                            size=size,
                        )
                    )
                except (OSError, ValueError):
                    continue

            return results
        except Exception:
            return []

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
            file_path: Path to file relative to root
            start_line: Starting line number (1-indexed, inclusive)
            end_line: Ending line number (1-indexed, inclusive)
            page_size: Number of lines per page
            page: Page number (1-indexed)

        Returns:
            File content as string, or error message
        """
        try:
            full_path = self._resolve_path(file_path)
            if not full_path.exists():
                return f"Error: File '{file_path}' not found"
            if not full_path.is_file():
                return f"Error: '{file_path}' is not a file"

            content = full_path.read_text(encoding="utf-8")
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
        except UnicodeDecodeError:
            return f"Error: Cannot decode '{file_path}' as UTF-8"
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
            file_path: Path to file relative to root
            content: Content to write
            create_parents: Whether to create parent directories

        Returns:
            WriteResult with success status and metadata
        """
        try:
            full_path = self._resolve_path(file_path)

            # Create parent directories if requested
            if create_parents:
                full_path.parent.mkdir(parents=True, exist_ok=True)
            elif not full_path.parent.exists():
                return WriteResult(
                    path=file_path,
                    lines_written=0,
                    error="parent_not_found",
                )

            # Write content
            full_path.write_text(content, encoding="utf-8")
            lines_written = len(content.splitlines())

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
            file_path: Path to file relative to root
            old_string: String to find and replace
            new_string: Replacement string
            replace_all: If True, replace all occurrences; if False, replace first only

        Returns:
            EditResult with number of replacements and status
        """
        try:
            full_path = self._resolve_path(file_path)
            if not full_path.exists():
                return EditResult(
                    path=file_path,
                    replacements=0,
                    error="file_not_found",
                )
            if not full_path.is_file():
                return EditResult(
                    path=file_path,
                    replacements=0,
                    error="invalid_path",
                )

            content = full_path.read_text(encoding="utf-8")

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

            full_path.write_text(new_content, encoding="utf-8")

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
            flags = wcglob.GLOBSTAR | wcglob.BRACE
            if not case_sensitive:
                flags |= wcglob.IGNORECASE

            matches = wcglob.glob(
                pattern,
                root_dir=str(self.root),
                flags=flags,
            )

            results = []
            for match in matches:
                try:
                    full_path = self.root / match
                    if not full_path.exists():
                        continue

                    is_file = full_path.is_file()
                    size = full_path.stat().st_size if is_file else 0

                    results.append(
                        FileInfo(
                            path=match,
                            is_file=is_file,
                            size=size,
                        )
                    )
                except (OSError, ValueError):
                    continue

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
            files = [f for f in files if f.is_file]

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
                    full_path = self._resolve_path(file_info.path)
                    content = full_path.read_text(encoding="utf-8")
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
        """Upload files to filesystem.

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
        """Download files from filesystem.

        Args:
            paths: List of file paths to download

        Returns:
            List of FileDownloadResponse objects with content for each file
        """
        results = []
        for path in paths:
            try:
                full_path = self._resolve_path(path)
                if not full_path.exists() or not full_path.is_file():
                    results.append(
                        FileDownloadResponse(
                            path=path, content=None, error="file_not_found"
                        )
                    )
                else:
                    content = full_path.read_bytes()
                    results.append(
                        FileDownloadResponse(path=path, content=content, error=None)
                    )
            except Exception:
                results.append(
                    FileDownloadResponse(
                        path=path, content=None, error="permission_denied"
                    )
                )
        return results

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_files, paths)
