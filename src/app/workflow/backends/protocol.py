import abc
import asyncio
from dataclasses import dataclass
from typing import Any, Literal, NotRequired
from typing_extensions import TypedDict


FileOperationError = Literal[
    "file_not_found",
    "permission_denied",
    "is_directory",
    "invalid_path",
]


class FileInfo(TypedDict):
    path: str
    is_dir: NotRequired[bool]
    size: NotRequired[int]
    modified_at: NotRequired[str]


class GrepMatch(TypedDict):
    path: str
    line: int
    text: str


@dataclass
class WriteResult:
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None


@dataclass
class EditResult:
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None
    occurrences: int | None = None


@dataclass
class ExecuteResponse:
    output: str
    exit_code: int | None = None
    truncated: bool = False


@dataclass
class FileUploadResponse:
    path: str
    error: FileOperationError | None = None


@dataclass
class FileDownloadResponse:
    path: str
    content: bytes | None = None
    error: FileOperationError | None = None


class BackendProtocol(abc.ABC):
    @abc.abstractmethod
    def ls_info(self, path: str) -> list[FileInfo]:
        raise NotImplementedError

    async def als_info(self, path: str) -> list[FileInfo]:
        return await asyncio.to_thread(self.ls_info, path)

    @abc.abstractmethod
    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        raise NotImplementedError

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    @abc.abstractmethod
    def grep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str:
        raise NotImplementedError

    async def agrep_raw(
        self, pattern: str, path: str | None = None, glob: str | None = None
    ) -> list[GrepMatch] | str:
        return await asyncio.to_thread(self.grep_raw, pattern, path, glob)

    @abc.abstractmethod
    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        raise NotImplementedError

    async def aglob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        return await asyncio.to_thread(self.glob_info, pattern, path)

    @abc.abstractmethod
    def write(self, file_path: str, content: str) -> WriteResult:
        raise NotImplementedError

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await asyncio.to_thread(self.write, file_path, content)

    @abc.abstractmethod
    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        raise NotImplementedError

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return await asyncio.to_thread(
            self.edit, file_path, old_string, new_string, replace_all
        )

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
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


class SandboxBackendProtocol(BackendProtocol):
    @abc.abstractmethod
    def execute(self, command: str) -> ExecuteResponse:
        raise NotImplementedError

    async def aexecute(self, command: str) -> ExecuteResponse:
        return await asyncio.to_thread(self.execute, command)

    @property
    @abc.abstractmethod
    def id(self) -> str:
        raise NotImplementedError
