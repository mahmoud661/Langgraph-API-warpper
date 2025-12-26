from typing import TYPE_CHECKING

from .protocol import BackendProtocol, EditResult, FileInfo, GrepMatch, WriteResult
from .utils import (
    _glob_search_files,
    create_file_data,
    file_data_to_string,
    format_read_response,
    grep_matches_from_files,
    perform_string_replacement,
    update_file_data,
)

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime


class StateBackend(BackendProtocol):

    def __init__(self, runtime: "ToolRuntime"):
        self.runtime = runtime

    def ls_info(self, path: str) -> list[FileInfo]:

        files = self.runtime.state.get("files", {})
        infos: list[FileInfo] = []
        subdirs: set[str] = set()

        # Normalize path to have trailing slash for proper prefix matching
        normalized_path = path if path.endswith("/") else path + "/"

        for k, fd in files.items():
            # Check if file is in the specified directory or a subdirectory
            if not k.startswith(normalized_path):
                continue

            # Get the relative path after the directory
            relative = k[len(normalized_path) :]

            # If relative path contains '/', it's in a subdirectory
            if "/" in relative:
                # Extract the immediate subdirectory name
                subdir_name = relative.split("/")[0]
                subdirs.add(normalized_path + subdir_name + "/")
                continue

            # This is a file directly in the current directory
            size = len("\n".join(fd.get("content", [])))
            infos.append(
                {
                    "path": k,
                    "is_dir": False,
                    "size": int(size),
                    "modified_at": fd.get("modified_at", ""),
                }
            )

        # Add directories to the results
        for subdir in sorted(subdirs):
            infos.append(
                {
                    "path": subdir,
                    "is_dir": True,
                    "size": 0,
                    "modified_at": "",
                }
            )

        infos.sort(key=lambda x: x.get("path", ""))
        return infos

    def read(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:

        files = self.runtime.state.get("files", {})
        file_data = files.get(file_path)

        if file_data is None:
            return f"Error: File '{file_path}' not found"

        return format_read_response(file_data, offset, limit)

    def write(
        self,
        file_path: str,
        content: str,
    ) -> WriteResult:

        files = self.runtime.state.get("files", {})

        if file_path in files:
            return WriteResult(
                error=f"Cannot write to {file_path} because it already exists. Read and then make an edit, or write to a new path."
            )

        new_file_data = create_file_data(content)
        return WriteResult(path=file_path, files_update={file_path: new_file_data})

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
  
        files = self.runtime.state.get("files", {})
        file_data = files.get(file_path)

        if file_data is None:
            return EditResult(error=f"Error: File '{file_path}' not found")

        content = file_data_to_string(file_data)
        result = perform_string_replacement(
            content, old_string, new_string, replace_all
        )

        if isinstance(result, str):
            return EditResult(error=result)

        new_content, occurrences = result
        new_file_data = update_file_data(file_data, new_content)
        return EditResult(
            path=file_path,
            files_update={file_path: new_file_data},
            occurrences=int(occurrences),
        )

    def grep_raw(
        self,
        pattern: str,
        path: str = "/",
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        files = self.runtime.state.get("files", {})
        return grep_matches_from_files(files, pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Get FileInfo for files matching glob pattern."""
        files = self.runtime.state.get("files", {})
        result = _glob_search_files(files, pattern, path)
        if result == "No files found":
            return []
        paths = result.split("\n")
        infos: list[FileInfo] = []
        for p in paths:
            fd = files.get(p)
            size = len("\n".join(fd.get("content", []))) if fd else 0
            infos.append(
                {
                    "path": p,
                    "is_dir": False,
                    "size": int(size),
                    "modified_at": fd.get("modified_at", "") if fd else "",
                }
            )
        return infos
