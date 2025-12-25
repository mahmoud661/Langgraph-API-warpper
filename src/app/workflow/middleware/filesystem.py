from collections.abc import Callable, Awaitable
from typing import Any, NotRequired
from typing_extensions import TypedDict

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)
from langchain.tools import BaseTool, ToolRuntime
from langchain_core.tools import StructuredTool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from src.app.workflow.backends.protocol import BackendProtocol, SandboxBackendProtocol
from src.app.workflow.backends.state import StateBackend


class FilesystemState(TypedDict):
    files: NotRequired[dict[str, Any]]


LIST_FILES_TOOL_DESCRIPTION = """List files in a directory.

Usage:
- The path parameter must be an absolute path starting with /
- Returns a list of files and directories in the specified path
- Directories are marked with is_dir: true"""

READ_FILE_TOOL_DESCRIPTION = """Read file content with line numbers.

Usage:
- The file_path parameter must be an absolute path starting with /
- offset: Line number to start reading from (0-indexed, default: 0)
- limit: Maximum number of lines to read (default: 2000)
- Returns file content with line numbers
- ALWAYS read a file before editing it"""

WRITE_FILE_TOOL_DESCRIPTION = """Writes to a new file in the filesystem.

Usage:
- The file_path parameter must be an absolute path
- The content parameter must be a string
- Creates a new file (fails if file already exists)
- Prefer to edit existing files over creating new ones"""

EDIT_FILE_TOOL_DESCRIPTION = """Perform exact string replacements in an existing file.

Usage:
- file_path: Absolute path to the file to edit
- old_string: Exact string to replace (must match exactly including whitespace)
- new_string: String to replace old_string with
- replace_all: If True, replace all occurrences. If False, old_string must be unique
- ALWAYS use read_file tool before editing
- Include sufficient context in old_string to make it unique"""

GLOB_TOOL_DESCRIPTION = """Find files matching a glob pattern.

Usage:
- Supports standard glob patterns: * (any characters), ** (any directories), ? (single character)
- Examples: **/*.py, *.txt, /subdir/**/*.md"""

GREP_TOOL_DESCRIPTION = """Search for a pattern in files.

Usage:
- pattern: Text to search for (literal string)
- path: Optional directory to search in
- glob: Optional glob pattern to filter files (e.g., *.py)
- output_mode: files_with_matches, content, or count"""

EXECUTE_TOOL_DESCRIPTION = """Executes a command in the sandbox environment.

Usage:
- command: Shell command to execute
- Returns combined stdout/stderr with exit code
- Only available if backend supports execution"""

FILESYSTEM_SYSTEM_PROMPT = """## Filesystem Tools

You have access to filesystem tools: ls, read_file, write_file, edit_file, glob, grep
All file paths must start with /"""

EXECUTION_SYSTEM_PROMPT = """## Execute Tool

You have access to an execute tool for running shell commands in a sandboxed environment."""

TOO_LARGE_TOOL_MSG = """Tool result too large, the result of this tool call {tool_call_id} was saved in the filesystem at this path: {file_path}
You can read the result from the filesystem by using the read_file tool, but make sure to only read part of the result at a time.
You can do this by specifying an offset and limit in the read_file tool call.
For example, to read the first 100 lines, you can use the read_file tool with offset=0 and limit=100.

Here are the first 10 lines of the result:
{content_sample}
"""

TOOL_GENERATORS = {
    "ls",
    "read_file",
    "write_file",
    "edit_file",
    "glob",
    "grep",
    "execute",
}


def _validate_path(path: str) -> str:
    if not path.startswith("/"):
        return f"Error: Path must be absolute (start with /), got: {path}"
    return path


def _get_backend(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
    runtime: ToolRuntime,
) -> BackendProtocol:
    if callable(backend):
        return backend(runtime)
    return backend


def _ls_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> BaseTool:
    def sync_ls(runtime: ToolRuntime[None, FilesystemState], path: str) -> str:
        resolved_backend = _get_backend(backend, runtime)
        validated_path = _validate_path(path)
        if validated_path.startswith("Error"):
            return validated_path
        infos = resolved_backend.ls_info(validated_path)
        paths = [fi.get("path", "") for fi in infos]
        return str(paths)

    async def async_ls(runtime: ToolRuntime[None, FilesystemState], path: str) -> str:
        resolved_backend = _get_backend(backend, runtime)
        validated_path = _validate_path(path)
        if validated_path.startswith("Error"):
            return validated_path
        infos = await resolved_backend.als_info(validated_path)
        paths = [fi.get("path", "") for fi in infos]
        return str(paths)

    return StructuredTool.from_function(
        name="ls",
        description=LIST_FILES_TOOL_DESCRIPTION,
        func=sync_ls,
        coroutine=async_ls,
    )


def _read_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> BaseTool:
    def sync_read_file(
        file_path: str,
        runtime: ToolRuntime[None, FilesystemState],
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        if file_path.startswith("Error"):
            return file_path
        return resolved_backend.read(file_path, offset=offset, limit=limit)

    async def async_read_file(
        file_path: str,
        runtime: ToolRuntime[None, FilesystemState],
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        if file_path.startswith("Error"):
            return file_path
        return await resolved_backend.aread(file_path, offset=offset, limit=limit)

    return StructuredTool.from_function(
        name="read_file",
        description=READ_FILE_TOOL_DESCRIPTION,
        func=sync_read_file,
        coroutine=async_read_file,
    )


def _write_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> BaseTool:
    def sync_write_file(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        if file_path.startswith("Error"):
            return file_path
        res = resolved_backend.write(file_path, content)
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Updated file {res.path}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Updated file {res.path}"

    async def async_write_file(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        if file_path.startswith("Error"):
            return file_path
        res = await resolved_backend.awrite(file_path, content)
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Updated file {res.path}",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Updated file {res.path}"

    return StructuredTool.from_function(
        name="write_file",
        description=WRITE_FILE_TOOL_DESCRIPTION,
        func=sync_write_file,
        coroutine=async_write_file,
    )


def _edit_file_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> BaseTool:
    def sync_edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        runtime: ToolRuntime[None, FilesystemState],
        replace_all: bool = False,
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        if file_path.startswith("Error"):
            return file_path
        res = resolved_backend.edit(
            file_path, old_string, new_string, replace_all=replace_all
        )
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'"

    async def async_edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        runtime: ToolRuntime[None, FilesystemState],
        replace_all: bool = False,
    ) -> Command | str:
        resolved_backend = _get_backend(backend, runtime)
        file_path = _validate_path(file_path)
        if file_path.startswith("Error"):
            return file_path
        res = await resolved_backend.aedit(
            file_path, old_string, new_string, replace_all=replace_all
        )
        if res.error:
            return res.error
        if res.files_update is not None:
            return Command(
                update={
                    "files": res.files_update,
                    "messages": [
                        ToolMessage(
                            content=f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Successfully replaced {res.occurrences} instance(s) in '{res.path}'"

    return StructuredTool.from_function(
        name="edit_file",
        description=EDIT_FILE_TOOL_DESCRIPTION,
        func=sync_edit_file,
        coroutine=async_edit_file,
    )


def _glob_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> BaseTool:
    def sync_glob(
        pattern: str, runtime: ToolRuntime[None, FilesystemState], path: str = "/"
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        infos = resolved_backend.glob_info(pattern, path=path)
        paths = [fi.get("path", "") for fi in infos]
        return str(paths)

    async def async_glob(
        pattern: str, runtime: ToolRuntime[None, FilesystemState], path: str = "/"
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        infos = await resolved_backend.aglob_info(pattern, path=path)
        paths = [fi.get("path", "") for fi in infos]
        return str(paths)

    return StructuredTool.from_function(
        name="glob",
        description=GLOB_TOOL_DESCRIPTION,
        func=sync_glob,
        coroutine=async_glob,
    )


def _grep_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> BaseTool:
    def sync_grep(
        pattern: str,
        runtime: ToolRuntime[None, FilesystemState],
        path: str | None = None,
        glob: str | None = None,
        output_mode: str = "files_with_matches",
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        raw = resolved_backend.grep_raw(pattern, path=path, glob=glob)
        if isinstance(raw, str):
            return raw
        if output_mode == "files_with_matches":
            return str(list(set(m["path"] for m in raw)))
        elif output_mode == "content":
            return "\n".join(f"{m['path']}:{m['line']}: {m['text']}" for m in raw)
        else:
            counts = {}
            for m in raw:
                counts[m["path"]] = counts.get(m["path"], 0) + 1
            return str(counts)

    async def async_grep(
        pattern: str,
        runtime: ToolRuntime[None, FilesystemState],
        path: str | None = None,
        glob: str | None = None,
        output_mode: str = "files_with_matches",
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        raw = await resolved_backend.agrep_raw(pattern, path=path, glob=glob)
        if isinstance(raw, str):
            return raw
        if output_mode == "files_with_matches":
            return str(list(set(m["path"] for m in raw)))
        elif output_mode == "content":
            return "\n".join(f"{m['path']}:{m['line']}: {m['text']}" for m in raw)
        else:
            counts = {}
            for m in raw:
                counts[m["path"]] = counts.get(m["path"], 0) + 1
            return str(counts)

    return StructuredTool.from_function(
        name="grep",
        description=GREP_TOOL_DESCRIPTION,
        func=sync_grep,
        coroutine=async_grep,
    )


def _execute_tool_generator(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> BaseTool:
    def sync_execute(command: str, runtime: ToolRuntime[None, FilesystemState]) -> str:
        resolved_backend = _get_backend(backend, runtime)
        if not isinstance(resolved_backend, SandboxBackendProtocol):
            return "Error: Execution not available. Backend does not support SandboxBackendProtocol."
        try:
            result = resolved_backend.execute(command)
        except NotImplementedError as e:
            return f"Error: Execution not available. {e}"
        parts = [result.output]
        if result.exit_code is not None:
            status = "succeeded" if result.exit_code == 0 else "failed"
            parts.append(f"\n[Command {status} with exit code {result.exit_code}]")
        if result.truncated:
            parts.append("\n[Output was truncated due to size limits]")
        return "".join(parts)

    async def async_execute(
        command: str, runtime: ToolRuntime[None, FilesystemState]
    ) -> str:
        resolved_backend = _get_backend(backend, runtime)
        if not isinstance(resolved_backend, SandboxBackendProtocol):
            return "Error: Execution not available. Backend does not support SandboxBackendProtocol."
        try:
            result = await resolved_backend.aexecute(command)
        except NotImplementedError as e:
            return f"Error: Execution not available. {e}"
        parts = [result.output]
        if result.exit_code is not None:
            status = "succeeded" if result.exit_code == 0 else "failed"
            parts.append(f"\n[Command {status} with exit code {result.exit_code}]")
        if result.truncated:
            parts.append("\n[Output was truncated due to size limits]")
        return "".join(parts)

    return StructuredTool.from_function(
        name="execute",
        description=EXECUTE_TOOL_DESCRIPTION,
        func=sync_execute,
        coroutine=async_execute,
    )


def _get_filesystem_tools(
    backend: BackendProtocol | Callable[[ToolRuntime], BackendProtocol],
) -> list[BaseTool]:
    return [
        _ls_tool_generator(backend),
        _read_file_tool_generator(backend),
        _write_file_tool_generator(backend),
        _edit_file_tool_generator(backend),
        _glob_tool_generator(backend),
        _grep_tool_generator(backend),
        _execute_tool_generator(backend),
    ]


class FilesystemMiddleware(AgentMiddleware):
    state_schema = FilesystemState

    def __init__(
        self,
        backend: (
            BackendProtocol | Callable[[ToolRuntime], BackendProtocol] | None
        ) = None,
        system_prompt: str | None = None,
        tool_token_limit_before_evict: int | None = 20000,
    ) -> None:
        self.backend = backend if backend is not None else (lambda rt: StateBackend(rt))
        self._custom_system_prompt = system_prompt
        self.tool_token_limit_before_evict = tool_token_limit_before_evict
        self.tools = _get_filesystem_tools(self.backend)

    def _get_backend(self, runtime: ToolRuntime) -> BackendProtocol:
        if callable(self.backend):
            return self.backend(runtime)
        return self.backend

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        has_execute_tool = any(
            (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
            for tool in request.tools
        )
        backend_supports_execution = False
        if has_execute_tool:
            backend = self._get_backend(request.runtime)
            backend_supports_execution = isinstance(backend, SandboxBackendProtocol)
            if not backend_supports_execution:
                filtered_tools = [
                    tool
                    for tool in request.tools
                    if (tool.name if hasattr(tool, "name") else tool.get("name"))
                    != "execute"
                ]
                request = request.override(tools=filtered_tools)
                has_execute_tool = False

        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:
            prompt_parts = [FILESYSTEM_SYSTEM_PROMPT]
            if has_execute_tool and backend_supports_execution:
                prompt_parts.append(EXECUTION_SYSTEM_PROMPT)
            system_prompt = "\n\n".join(prompt_parts)

        if system_prompt:
            request = request.override(
                system_prompt=(
                    request.system_prompt + "\n\n" + system_prompt
                    if request.system_prompt
                    else system_prompt
                )
            )
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        has_execute_tool = any(
            (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
            for tool in request.tools
        )
        backend_supports_execution = False
        if has_execute_tool:
            backend = self._get_backend(request.runtime)
            backend_supports_execution = isinstance(backend, SandboxBackendProtocol)
            if not backend_supports_execution:
                filtered_tools = [
                    tool
                    for tool in request.tools
                    if (tool.name if hasattr(tool, "name") else tool.get("name"))
                    != "execute"
                ]
                request = request.override(tools=filtered_tools)
                has_execute_tool = False

        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:
            prompt_parts = [FILESYSTEM_SYSTEM_PROMPT]
            if has_execute_tool and backend_supports_execution:
                prompt_parts.append(EXECUTION_SYSTEM_PROMPT)
            system_prompt = "\n\n".join(prompt_parts)

        if system_prompt:
            request = request.override(
                system_prompt=(
                    request.system_prompt + "\n\n" + system_prompt
                    if request.system_prompt
                    else system_prompt
                )
            )
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        has_execute_tool = any(
            (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
            for tool in request.tools
        )
        backend_supports_execution = False
        if has_execute_tool:
            backend = self._get_backend(request.runtime)
            backend_supports_execution = isinstance(backend, SandboxBackendProtocol)
            if not backend_supports_execution:
                filtered_tools = [
                    tool
                    for tool in request.tools
                    if (tool.name if hasattr(tool, "name") else tool.get("name"))
                    != "execute"
                ]
                request = request.override(tools=filtered_tools)
                has_execute_tool = False

        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:
            prompt_parts = [FILESYSTEM_SYSTEM_PROMPT]
            if has_execute_tool and backend_supports_execution:
                prompt_parts.append(EXECUTION_SYSTEM_PROMPT)
            system_prompt = "\n\n".join(prompt_parts)

        if system_prompt:
            request = request.override(
                system_prompt=(
                    request.system_prompt + "\n\n" + system_prompt
                    if request.system_prompt
                    else system_prompt
                )
            )
        return await handler(request)

    def _process_large_message(
        self,
        message: ToolMessage,
        resolved_backend: BackendProtocol,
    ) -> tuple[ToolMessage, dict[str, Any] | None]:
        content = message.content
        if (
            not isinstance(content, str)
            or len(content) <= 4 * self.tool_token_limit_before_evict
        ):
            return message, None

        sanitized_id = message.tool_call_id.replace("/", "_").replace("\\", "_")
        file_path = f"/large_tool_results/{sanitized_id}"
        result = resolved_backend.write(file_path, content)
        if result.error:
            return message, None

        content_lines = content.splitlines()[:10]
        content_sample = "\n".join(
            f"{i+1}\t{line[:1000]}" for i, line in enumerate(content_lines)
        )

        processed_message = ToolMessage(
            TOO_LARGE_TOOL_MSG.format(
                tool_call_id=message.tool_call_id,
                file_path=file_path,
                content_sample=content_sample,
            ),
            tool_call_id=message.tool_call_id,
        )
        return processed_message, result.files_update

    def _intercept_large_tool_result(
        self, tool_result: ToolMessage | Command, runtime: ToolRuntime
    ) -> ToolMessage | Command:
        if isinstance(tool_result, ToolMessage) and isinstance(
            tool_result.content, str
        ):
            if not (
                self.tool_token_limit_before_evict
                and len(tool_result.content) > 4 * self.tool_token_limit_before_evict
            ):
                return tool_result
            resolved_backend = self._get_backend(runtime)
            processed_message, files_update = self._process_large_message(
                tool_result, resolved_backend
            )
            return (
                Command(
                    update={
                        "files": files_update,
                        "messages": [processed_message],
                    }
                )
                if files_update is not None
                else processed_message
            )

        if isinstance(tool_result, Command):
            update = tool_result.update
            if update is None:
                return tool_result
            command_messages = update.get("messages", [])
            accumulated_file_updates = dict(update.get("files", {}))
            resolved_backend = self._get_backend(runtime)
            processed_messages = []
            for message in command_messages:
                if not (
                    self.tool_token_limit_before_evict
                    and isinstance(message, ToolMessage)
                    and isinstance(message.content, str)
                    and len(message.content) > 4 * self.tool_token_limit_before_evict
                ):
                    processed_messages.append(message)
                    continue
                processed_message, files_update = self._process_large_message(
                    message, resolved_backend
                )
                processed_messages.append(processed_message)
                if files_update is not None:
                    accumulated_file_updates.update(files_update)
            return Command(
                update={
                    **update,
                    "messages": processed_messages,
                    "files": accumulated_file_updates,
                }
            )

        return tool_result

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command],
    ) -> ToolMessage | Command:
        if (
            self.tool_token_limit_before_evict is None
            or request.tool_call["name"] in TOOL_GENERATORS
        ):
            return handler(request)

        tool_result = handler(request)
        return self._intercept_large_tool_result(tool_result, request.runtime)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
    ) -> ToolMessage | Command:
        if (
            self.tool_token_limit_before_evict is None
            or request.tool_call["name"] in TOOL_GENERATORS
        ):
            return await handler(request)

        tool_result = await handler(request)
        return self._intercept_large_tool_result(tool_result, request.runtime)
