"""Filesystem tool generators and descriptions."""

# ruff: noqa: E501

from collections.abc import Callable
from typing import TYPE_CHECKING, Literal

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command

from src.app.domain.filesystem import FilesystemState, validate_path
from src.app.domain.storage.protocol import BackendProtocol, SandboxBackendProtocol
from src.app.domain.storage.types import EditResult, WriteResult
from src.app.infrastructure.storage.utils import (
    format_content_with_line_numbers,
    format_grep_matches,
    truncate_if_too_long,
)

EMPTY_CONTENT_WARNING = "System reminder: File exists but has empty contents"
MAX_LINE_LENGTH = 2000
LINE_NUMBER_WIDTH = 6
DEFAULT_READ_OFFSET = 0
DEFAULT_READ_LIMIT = 500

LIST_FILES_TOOL_DESCRIPTION = """Lists all files in the filesystem, filtering by directory.

Usage:
- The path parameter must be an absolute path, not a relative path
- The list_files tool will return a list of all files in the specified directory.
- This is very useful for exploring the file system and finding the right file to read or edit.
- You should almost ALWAYS use this tool before using the Read or Edit tools."""

READ_FILE_TOOL_DESCRIPTION = """Reads a file from the filesystem. You can access any file directly by using this tool.
Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- By default, it reads up to 500 lines starting from the beginning of the file
- **IMPORTANT for large files and codebase exploration**: Use pagination with offset and limit parameters to avoid context overflow
  - First scan: read_file(path, limit=100) to see file structure
  - Read more sections: read_file(path, offset=100, limit=200) for next 200 lines
  - Only omit limit (read full file) when necessary for editing
- Specify offset and limit: read_file(path, offset=0, limit=100) reads first 100 lines
- Any lines longer than 2000 characters will be truncated
- Results are returned using cat -n format, with line numbers starting at 1
- You have the capability to call multiple tools in a single response. It is always better to speculatively read multiple files as a batch that are potentially useful.
- If you read a file that exists but has empty contents you will receive a system reminder warning in place of file contents.
- You should ALWAYS make sure a file has been read before editing it."""

EDIT_FILE_TOOL_DESCRIPTION = """Performs exact string replacements in files.

Usage:
- You must use your `Read` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file.
- When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. The line number prefix format is: spaces + line number + tab. Everything after that tab is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string.
- ALWAYS prefer editing existing files. NEVER write new files unless explicitly required.
- Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked.
- The edit will FAIL if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`.
- Use `replace_all` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance."""

WRITE_FILE_TOOL_DESCRIPTION = """Writes to a new file in the filesystem.

Usage:
- The file_path parameter must be an absolute path, not a relative path
- The content parameter must be a string
- The write_file tool will create the a new file.
- Prefer to edit existing files over creating new ones when possible."""

GLOB_TOOL_DESCRIPTION = """Find files matching a glob pattern.

Usage:
- The glob tool finds files by matching patterns with wildcards
- Supports standard glob patterns: `*` (any characters), `**` (any directories), `?` (single character)
- Patterns can be absolute (starting with `/`) or relative
- Returns a list of absolute file paths that match the pattern

Examples:
- `**/*.py` - Find all Python files
- `*.txt` - Find all text files in root
- `/subdir/**/*.md` - Find all markdown files under /subdir"""

GREP_TOOL_DESCRIPTION = """Search for a pattern in files.

Usage:
- The grep tool searches for text patterns across files
- The pattern parameter is the text to search for (literal string, not regex)
- The path parameter filters which directory to search in (default is the current working directory)
- The glob parameter accepts a glob pattern to filter which files to search (e.g., `*.py`)
- The output_mode parameter controls the output format:
  - `files_with_matches`: List only file paths containing matches (default)
  - `content`: Show matching lines with file path and line numbers
  - `count`: Show count of matches per file

Examples:
- Search all files: `grep(pattern="TODO")`
- Search Python files only: `grep(pattern="import", glob="*.py")`
- Show matching lines: `grep(pattern="error", output_mode="content")`"""

EXECUTE_TOOL_DESCRIPTION = """Executes a given command in the sandbox environment with proper handling and security measures.

Before executing the command, please follow these steps:

1. Directory Verification:
   - If the command will create new directories or files, first use the ls tool to verify the parent directory exists and is the correct location
   - For example, before running "mkdir foo/bar", first use ls to check that "foo" exists and is the intended parent directory

2. Command Execution:
   - Always quote file paths that contain spaces with double quotes (e.g., cd "path with spaces/file.txt")
   - Examples of proper quoting:
     - cd "/Users/name/My Documents" (correct)
     - cd /Users/name/My Documents (incorrect - will fail)
     - python "/path/with spaces/script.py" (correct)
     - python /path/with spaces/script.py (incorrect - will fail)
   - After ensuring proper quoting, execute the command
   - Capture the output of the command

Usage notes:
  - The command parameter is required
  - Commands run in an isolated sandbox environment
  - Returns combined stdout/stderr output with exit code
  - If the output is very large, it may be truncated
  - VERY IMPORTANT: You MUST avoid using search commands like find and grep. Instead use the grep, glob tools to search. You MUST avoid read tools like cat, head, tail, and use read_file to read files.
  - When issuing multiple commands, use the ';' or '&&' operator to separate them. DO NOT use newlines (newlines are ok in quoted strings)
    - Use '&&' when commands depend on each other (e.g., "mkdir dir && cd dir")
    - Use ';' only when you need to run commands sequentially but don't care if earlier commands fail
  - Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of cd

Examples:
  Good examples:
    - execute(command="pytest /foo/bar/tests")
    - execute(command="python /path/to/script.py")
    - execute(command="npm install && npm test")

  Bad examples (avoid these):
    - execute(command="cd /foo/bar && pytest tests")  # Use absolute path instead
    - execute(command="cat file.txt")  # Use read_file tool instead
    - execute(command="find . -name '*.py'")  # Use glob tool instead
    - execute(command="grep -r 'pattern' .")  # Use grep tool instead

Note: This tool is only available if the backend supports execution (SandboxBackendProtocol).
If execution is not supported, the tool will return an error message."""

FILESYSTEM_SYSTEM_PROMPT = """## Filesystem Tools `ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`

You have access to a filesystem which you can interact with using these tools.
All file paths must start with a /.

- ls: list files in a directory (requires absolute path)
- read_file: read a file from the filesystem
- write_file: write to a file in the filesystem
- edit_file: edit a file in the filesystem
- glob: find files matching a pattern (e.g., "**/*.py")
- grep: search for text within files"""

EXECUTION_SYSTEM_PROMPT = """## Execute Tool `execute`

You have access to an `execute` tool for running shell commands in a sandboxed environment.
Use this tool to run commands, scripts, tests, builds, and other shell operations.

- execute: run a shell command in the sandbox (returns output and exit code)"""


def _get_backend(
    backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol]",
    runtime: "ToolRuntime",
) -> BackendProtocol:
    """Get the resolved backend instance from backend or factory.

    Args:
        backend: Backend instance or factory function.
        runtime: The tool runtime context.

    Returns:
        Resolved backend instance.
    """
    if callable(backend):
        return backend(runtime)
    return backend


def _ls_tool_generator(
    backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol]",
    custom_description: str | None = None,
) -> BaseTool:
    """Generate ls tool for listing files."""
    tool_description = custom_description or LIST_FILES_TOOL_DESCRIPTION

    def sync_ls(runtime: ToolRuntime[None, FilesystemState], path: str) -> str:
        """Synchronous wrapper for ls tool."""
        resolved_backend = _get_backend(backend, runtime)
        validated_path = validate_path(path)
        infos = resolved_backend.ls_info(validated_path)
        paths = [fi.get("path", "") for fi in infos]
        result = truncate_if_too_long(paths)
        return str(result)

    async def async_ls(runtime: ToolRuntime[None, FilesystemState], path: str) -> str:
        """Asynchronous wrapper for ls tool."""
        resolved_backend = _get_backend(backend, runtime)
        validated_path = validate_path(path)
        infos = await resolved_backend.als_info(validated_path)
        paths = [fi.get("path", "") for fi in infos]
        result = truncate_if_too_long(paths)
        return str(result)

    return StructuredTool.from_function(
        name="ls",
        description=tool_description,
        func=sync_ls,
        coroutine=async_ls,
    )


def _read_file_tool_generator(
    backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol]",
    custom_description: str | None = None,
) -> BaseTool:
    """Generate read_file tool for reading files."""
    tool_description = custom_description or READ_FILE_TOOL_DESCRIPTION

    def sync_read_file(
        file_path: str,
        runtime: ToolRuntime[None, FilesystemState],
        offset: int = DEFAULT_READ_OFFSET,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> str:
        """Synchronous wrapper for read_file tool."""
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        return resolved_backend.read(file_path, offset=offset, limit=limit)

    async def async_read_file(
        file_path: str,
        runtime: ToolRuntime[None, FilesystemState],
        offset: int = DEFAULT_READ_OFFSET,
        limit: int = DEFAULT_READ_LIMIT,
    ) -> str:
        """Asynchronous wrapper for read_file tool."""
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        return await resolved_backend.aread(file_path, offset=offset, limit=limit)

    return StructuredTool.from_function(
        name="read_file",
        description=tool_description,
        func=sync_read_file,
        coroutine=async_read_file,
    )


def _write_file_tool_generator(
    backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol]",
    custom_description: str | None = None,
) -> BaseTool:
    """Generate write_file tool for writing files."""
    tool_description = custom_description or WRITE_FILE_TOOL_DESCRIPTION

    def sync_write_file(
        file_path: str,
        content: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> Command | str:
        """Synchronous wrapper for write_file tool."""
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        res: WriteResult = resolved_backend.write(file_path, content)
        if res.error:
            return res.error
        # If backend returns state update, wrap into Command with ToolMessage
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
        """Asynchronous wrapper for write_file tool."""
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        res: WriteResult = await resolved_backend.awrite(file_path, content)
        if res.error:
            return res.error
        # If backend returns state update, wrap into Command with ToolMessage
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
        description=tool_description,
        func=sync_write_file,
        coroutine=async_write_file,
    )


def _edit_file_tool_generator(
    backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol]",
    custom_description: str | None = None,
) -> BaseTool:
    """Generate edit_file tool for editing files."""
    tool_description = custom_description or EDIT_FILE_TOOL_DESCRIPTION

    def sync_edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        runtime: ToolRuntime[None, FilesystemState],
        *,
        replace_all: bool = False,
    ) -> Command | str:
        """Synchronous wrapper for edit_file tool."""
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        res: EditResult = resolved_backend.edit(
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
                            content=f"Successfully replaced {res.occurrences} instance(s) of the string in '{res.path}'",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Successfully replaced {res.occurrences} instance(s) of the string in '{res.path}'"

    async def async_edit_file(
        file_path: str,
        old_string: str,
        new_string: str,
        runtime: ToolRuntime[None, FilesystemState],
        *,
        replace_all: bool = False,
    ) -> Command | str:
        """Asynchronous wrapper for edit_file tool."""
        resolved_backend = _get_backend(backend, runtime)
        file_path = validate_path(file_path)
        res: EditResult = await resolved_backend.aedit(
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
                            content=f"Successfully replaced {res.occurrences} instance(s) of the string in '{res.path}'",
                            tool_call_id=runtime.tool_call_id,
                        )
                    ],
                }
            )
        return f"Successfully replaced {res.occurrences} instance(s) of the string in '{res.path}'"

    return StructuredTool.from_function(
        name="edit_file",
        description=tool_description,
        func=sync_edit_file,
        coroutine=async_edit_file,
    )


def _glob_tool_generator(
    backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol]",
    custom_description: str | None = None,
) -> BaseTool:
    """Generate glob tool for pattern matching files."""
    tool_description = custom_description or GLOB_TOOL_DESCRIPTION

    def sync_glob(
        pattern: str, runtime: ToolRuntime[None, FilesystemState], path: str = "/"
    ) -> str:
        """Synchronous wrapper for glob tool."""
        resolved_backend = _get_backend(backend, runtime)
        infos = resolved_backend.glob_info(pattern, path=path)
        paths = [fi.get("path", "") for fi in infos]
        result = truncate_if_too_long(paths)
        return str(result)

    async def async_glob(
        pattern: str, runtime: ToolRuntime[None, FilesystemState], path: str = "/"
    ) -> str:
        """Asynchronous wrapper for glob tool."""
        resolved_backend = _get_backend(backend, runtime)
        infos = await resolved_backend.aglob_info(pattern, path=path)
        paths = [fi.get("path", "") for fi in infos]
        result = truncate_if_too_long(paths)
        return str(result)

    return StructuredTool.from_function(
        name="glob",
        description=tool_description,
        func=sync_glob,
        coroutine=async_glob,
    )


def _grep_tool_generator(
    backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol]",
    custom_description: str | None = None,
) -> BaseTool:
    """Generate grep tool for searching files."""
    tool_description = custom_description or GREP_TOOL_DESCRIPTION

    def sync_grep(
        pattern: str,
        runtime: ToolRuntime[None, FilesystemState],
        path: str | None = None,
        glob: str | None = None,
        output_mode: Literal[
            "files_with_matches", "content", "count"
        ] = "files_with_matches",
    ) -> str:
        """Synchronous wrapper for grep tool."""
        resolved_backend = _get_backend(backend, runtime)
        raw = resolved_backend.grep_raw(pattern, path=path, glob=glob)
        if isinstance(raw, str):
            return raw
        formatted = format_grep_matches(raw, output_mode)
        return truncate_if_too_long(formatted)  # type: ignore[arg-type]

    async def async_grep(
        pattern: str,
        runtime: ToolRuntime[None, FilesystemState],
        path: str | None = None,
        glob: str | None = None,
        output_mode: Literal[
            "files_with_matches", "content", "count"
        ] = "files_with_matches",
    ) -> str:
        """Asynchronous wrapper for grep tool."""
        resolved_backend = _get_backend(backend, runtime)
        raw = await resolved_backend.agrep_raw(pattern, path=path, glob=glob)
        if isinstance(raw, str):
            return raw
        formatted = format_grep_matches(raw, output_mode)
        return truncate_if_too_long(formatted)  # type: ignore[arg-type]

    return StructuredTool.from_function(
        name="grep",
        description=tool_description,
        func=sync_grep,
        coroutine=async_grep,
    )


def supports_execution(backend: BackendProtocol) -> bool:
    """Check if backend supports command execution."""
    # Import here to avoid circular dependency
    from src.app.infrastructure.storage.composite import CompositeBackend

    # For CompositeBackend, check the default backend
    if isinstance(backend, CompositeBackend):
        return isinstance(backend.default, SandboxBackendProtocol)

    # For other backends, use isinstance check
    return isinstance(backend, SandboxBackendProtocol)


def _execute_tool_generator(
    backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol]",
    custom_description: str | None = None,
) -> BaseTool:
    """Generate execute tool for running commands."""
    tool_description = custom_description or EXECUTE_TOOL_DESCRIPTION

    def sync_execute(
        command: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> str:
        """Synchronous wrapper for execute tool."""
        resolved_backend = _get_backend(backend, runtime)

        # Runtime check - fail gracefully if not supported
        if not supports_execution(resolved_backend):
            return (
                "Error: Execution not available. This agent's backend "
                "does not support command execution (SandboxBackendProtocol). "
                "To use the execute tool, provide a backend that implements SandboxBackendProtocol."
            )

        try:
            result = resolved_backend.execute(command)
        except NotImplementedError as e:
            # Handle case where execute() exists but raises NotImplementedError
            return f"Error: Execution not available. {e}"

        # Format output for LLM consumption
        parts = [result.output]

        if result.exit_code is not None:
            status = "succeeded" if result.exit_code == 0 else "failed"
            parts.append(f"\n[Command {status} with exit code {result.exit_code}]")

        if result.truncated:
            parts.append("\n[Output was truncated due to size limits]")

        return "".join(parts)

    async def async_execute(
        command: str,
        runtime: ToolRuntime[None, FilesystemState],
    ) -> str:
        """Asynchronous wrapper for execute tool."""
        resolved_backend = _get_backend(backend, runtime)

        # Runtime check - fail gracefully if not supported
        if not supports_execution(resolved_backend):
            return (
                "Error: Execution not available. This agent's backend "
                "does not support command execution (SandboxBackendProtocol). "
                "To use the execute tool, provide a backend that implements SandboxBackendProtocol."
            )

        try:
            result = await resolved_backend.aexecute(command)
        except NotImplementedError as e:
            # Handle case where execute() exists but raises NotImplementedError
            return f"Error: Execution not available. {e}"

        # Format output for LLM consumption
        parts = [result.output]

        if result.exit_code is not None:
            status = "succeeded" if result.exit_code == 0 else "failed"
            parts.append(f"\n[Command {status} with exit code {result.exit_code}]")

        if result.truncated:
            parts.append("\n[Output was truncated due to size limits]")

        return "".join(parts)

    return StructuredTool.from_function(
        name="execute",
        description=tool_description,
        func=sync_execute,
        coroutine=async_execute,
    )


TOOL_GENERATORS = {
    "ls": _ls_tool_generator,
    "read_file": _read_file_tool_generator,
    "write_file": _write_file_tool_generator,
    "edit_file": _edit_file_tool_generator,
    "glob": _glob_tool_generator,
    "grep": _grep_tool_generator,
    "execute": _execute_tool_generator,
}


def get_filesystem_tools(
    backend: BackendProtocol,
    custom_tool_descriptions: dict[str, str] | None = None,
) -> list[BaseTool]:
    """Generate all filesystem tools for the given backend.

    Args:
        backend: Backend instance or factory function.
        custom_tool_descriptions: Optional custom descriptions for tools.

    Returns:
        List of filesystem tools.
    """
    if custom_tool_descriptions is None:
        custom_tool_descriptions = {}
    tools = []

    for tool_name, tool_generator in TOOL_GENERATORS.items():
        tool = tool_generator(backend, custom_tool_descriptions.get(tool_name))
        tools.append(tool)
    return tools
