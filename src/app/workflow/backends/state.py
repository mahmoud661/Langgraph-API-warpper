import fnmatch
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain.tools import ToolRuntime
from wcmatch import glob as wcglob

from src.app.workflow.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileInfo,
    GrepMatch,
    WriteResult,
)


class StateBackend(BackendProtocol):
    def __init__(self, runtime: ToolRuntime):
        self.runtime = runtime

    def _get_files(self) -> dict[str, Any]:
        return self.runtime.state.get("files", {})

    def _validate_path(self, path: str) -> str:
        if not path.startswith("/"):
            return f"Error: Path must be absolute (start with /), got: {path}"
        return path

    def ls_info(self, path: str) -> list[FileInfo]:
        validated = self._validate_path(path)
        if isinstance(validated, str) and validated.startswith("Error"):
            return []

        files = self._get_files()
        path_normalized = path.rstrip("/")

        results: list[FileInfo] = []
        seen_dirs = set()

        for file_path in files.keys():
            if not file_path.startswith(path_normalized + "/"):
                continue

            relative = file_path[len(path_normalized) + 1 :]
            if "/" in relative:
                dir_name = relative.split("/")[0]
                if dir_name not in seen_dirs:
                    seen_dirs.add(dir_name)
                    results.append(
                        FileInfo(
                            path=f"{path_normalized}/{dir_name}",
                            is_dir=True,
                        )
                    )
            else:
                file_data = files[file_path]
                results.append(
                    FileInfo(
                        path=file_path,
                        is_dir=False,
                        size=len("\n".join(file_data.get("content", []))),
                        modified_at=file_data.get("modified_at", ""),
                    )
                )

        return sorted(results, key=lambda x: x["path"])

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        validated = self._validate_path(file_path)
        if isinstance(validated, str) and validated.startswith("Error"):
            return validated

        files = self._get_files()
        if file_path not in files:
            return f"Error: File not found: {file_path}"

        file_data = files[file_path]
        content_lines = file_data.get("content", [])

        selected_lines = content_lines[offset : offset + limit]
        if not selected_lines:
            return f"File {file_path} is empty or offset is beyond file length"

        numbered_lines = [
            f"{i + offset + 1}\t{line[:2000]}" for i, line in enumerate(selected_lines)
        ]
        return "\n".join(numbered_lines)

    def write(self, file_path: str, content: str) -> WriteResult:
        validated = self._validate_path(file_path)
        if isinstance(validated, str) and validated.startswith("Error"):
            return WriteResult(error=validated)

        files = self._get_files()
        if file_path in files:
            return WriteResult(error=f"Error: File already exists: {file_path}")

        now = datetime.utcnow().isoformat()
        file_data = {
            "content": content.splitlines(),
            "created_at": now,
            "modified_at": now,
        }

        files_update = {file_path: file_data}
        return WriteResult(path=file_path, files_update=files_update)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        validated = self._validate_path(file_path)
        if isinstance(validated, str) and validated.startswith("Error"):
            return EditResult(error=validated)

        files = self._get_files()
        if file_path not in files:
            return EditResult(error=f"Error: File not found: {file_path}")

        file_data = files[file_path].copy()
        content = "\n".join(file_data.get("content", []))

        if old_string == new_string:
            return EditResult(error="Error: old_string and new_string are identical")

        if replace_all:
            occurrences = content.count(old_string)
            if occurrences == 0:
                return EditResult(error=f"Error: String not found in file: {file_path}")
            new_content = content.replace(old_string, new_string)
        else:
            occurrences = content.count(old_string)
            if occurrences == 0:
                return EditResult(error=f"Error: String not found in file: {file_path}")
            if occurrences > 1:
                return EditResult(
                    error=f"Error: String appears {occurrences} times. Use replace_all=True or provide more context"
                )
            new_content = content.replace(old_string, new_string, 1)

        file_data["content"] = new_content.splitlines()
        file_data["modified_at"] = datetime.utcnow().isoformat()

        files_update = {file_path: file_data}
        return EditResult(
            path=file_path, files_update=files_update, occurrences=occurrences
        )

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        files = self._get_files()
        results: list[FileInfo] = []

        for file_path in files.keys():
            if wcglob.globmatch(file_path, pattern, flags=wcglob.GLOBSTAR):
                file_data = files[file_path]
                results.append(
                    FileInfo(
                        path=file_path,
                        is_dir=False,
                        size=len("\n".join(file_data.get("content", []))),
                        modified_at=file_data.get("modified_at", ""),
                    )
                )

        return sorted(results, key=lambda x: x["path"])

    def grep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str:
        files = self._get_files()
        matches: list[GrepMatch] = []

        for file_path, file_data in files.items():
            if path and not file_path.startswith(path):
                continue

            if glob and not fnmatch.fnmatch(file_path, glob):
                continue

            content_lines = file_data.get("content", [])
            for line_num, line in enumerate(content_lines, 1):
                if pattern in line:
                    matches.append(GrepMatch(path=file_path, line=line_num, text=line))

        return matches
