"""Filesystem middleware for LangGraph agents."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain.tools.tool_node import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from src.app.domain.filesystem import FilesystemState
from src.app.domain.storage.protocol import BackendProtocol
from src.app.infrastructure.filesystem.tools import (
    EXECUTION_SYSTEM_PROMPT,
    FILESYSTEM_SYSTEM_PROMPT,
    TOOL_GENERATORS,
    get_filesystem_tools,
    supports_execution,
)
from src.app.infrastructure.storage import StateBackend
from src.app.infrastructure.storage.utils import (
    format_content_with_line_numbers,
    sanitize_tool_call_id,
)

TOO_LARGE_TOOL_MSG = """Tool result too large, the result of this tool call {tool_call_id} was saved in the filesystem at this path: {file_path}
You can read the result from the filesystem by using the read_file tool, but make sure to only read part of the result at a time.
You can do this by specifying an offset and limit in the read_file tool call.
For example, to read the first 100 lines, you can use the read_file tool with offset=0 and limit=100.

Here are the first 10 lines of the result:
{content_sample}
"""


class FilesystemMiddleware(AgentMiddleware):
    """LangGraph middleware that provides filesystem tools to agents."""

    state_schema = FilesystemState

    def __init__(
        self,
        *,
        backend: "BackendProtocol | Callable[[ToolRuntime], BackendProtocol] | None" = None,
        system_prompt: str | None = None,
        custom_tool_descriptions: dict[str, str] | None = None,
        tool_token_limit_before_evict: int | None = 20000,
    ) -> None:
        """Initialize FilesystemMiddleware.

        Args:
            backend: Backend instance or factory function. Defaults to StateBackend.
            system_prompt: Custom system prompt override. If None, generates dynamically.
            custom_tool_descriptions: Optional custom descriptions for tools.
            tool_token_limit_before_evict: Token limit before evicting large tool results.
        """
        self.tool_token_limit_before_evict = tool_token_limit_before_evict

        # Use provided backend or default to StateBackend factory
        self.backend = backend if backend is not None else (lambda rt: StateBackend(rt))

        # Set system prompt (allow full override or None to generate dynamically)
        self._custom_system_prompt = system_prompt

        self.tools = get_filesystem_tools(self.backend, custom_tool_descriptions)

    def _get_backend(self, runtime: "ToolRuntime") -> BackendProtocol:
        """Resolve backend instance from backend or factory."""
        if callable(self.backend):
            return self.backend(runtime)
        return self.backend

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        """Wrap model call to inject filesystem system prompt."""
        # Check if execute tool is present and if backend supports it
        has_execute_tool = any(
            (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
            for tool in request.tools
        )

        backend_supports_execution = False
        if has_execute_tool:
            # Resolve backend to check execution support
            backend = self._get_backend(request.runtime)
            backend_supports_execution = supports_execution(backend)

            # If execute tool exists but backend doesn't support it, filter it out
            if not backend_supports_execution:
                filtered_tools = [
                    tool
                    for tool in request.tools
                    if (tool.name if hasattr(tool, "name") else tool.get("name"))
                    != "execute"
                ]
                request = request.override(tools=filtered_tools)
                has_execute_tool = False

        # Use custom system prompt if provided, otherwise generate dynamically
        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:
            # Build dynamic system prompt based on available tools
            prompt_parts = [FILESYSTEM_SYSTEM_PROMPT]

            # Add execution instructions if execute tool is available
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
        """Wrap async model call to inject filesystem system prompt."""
        # Check if execute tool is present and if backend supports it
        has_execute_tool = any(
            (tool.name if hasattr(tool, "name") else tool.get("name")) == "execute"
            for tool in request.tools
        )

        backend_supports_execution = False
        if has_execute_tool:
            # Resolve backend to check execution support
            backend = self._get_backend(request.runtime)
            backend_supports_execution = supports_execution(backend)

            # If execute tool exists but backend doesn't support it, filter it out
            if not backend_supports_execution:
                filtered_tools = [
                    tool
                    for tool in request.tools
                    if (tool.name if hasattr(tool, "name") else tool.get("name"))
                    != "execute"
                ]
                request = request.override(tools=filtered_tools)
                has_execute_tool = False

        # Use custom system prompt if provided, otherwise generate dynamically
        if self._custom_system_prompt is not None:
            system_prompt = self._custom_system_prompt
        else:
            # Build dynamic system prompt based on available tools
            prompt_parts = [FILESYSTEM_SYSTEM_PROMPT]

            # Add execution instructions if execute tool is available
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
    ) -> tuple[ToolMessage, dict | None]:
        """Process large tool message by writing to file."""
        content = message.content
        if (
            not isinstance(content, str)
            or len(content) <= 4 * self.tool_token_limit_before_evict
        ):
            return message, None

        sanitized_id = sanitize_tool_call_id(message.tool_call_id)
        file_path = f"/large_tool_results/{sanitized_id}"
        result = resolved_backend.write(file_path, content)
        if result.error:
            return message, None
        content_sample = format_content_with_line_numbers(
            [line[:1000] for line in content.splitlines()[:10]], start_line=1
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
        self, tool_result: ToolMessage | Command, runtime: "ToolRuntime"
    ) -> ToolMessage | Command:
        """Intercept large tool results and write to filesystem."""
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
                tool_result,
                resolved_backend,
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
                    message,
                    resolved_backend,
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
        """Wrap tool call to handle large results."""
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
        """Wrap async tool call to handle large results."""
        if (
            self.tool_token_limit_before_evict is None
            or request.tool_call["name"] in TOOL_GENERATORS
        ):
            return await handler(request)

        tool_result = await handler(request)
        return self._intercept_large_tool_result(tool_result, request.runtime)
