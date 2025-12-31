"""Model executor factories that wrap domain logic with middleware support."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langgraph.prebuilt.tool_node import ToolNode

    from langchain.agents.middleware.types import ModelRequest, ModelResponse
    from langchain.agents.structured_output import OutputToolBinding

from src.app.domain.model import get_bound_model, handle_model_output


def make_execute_model_sync(
    tool_node: ToolNode | None,
    structured_output_tools: dict[str, OutputToolBinding],
    name: str | None,
):
    """Create a synchronous model executor function.

    This is the core model execution logic wrapped by `wrap_model_call` handlers.
    """
    from langchain.agents.middleware.types import ModelRequest, ModelResponse

    def _execute_model_sync(request: ModelRequest) -> ModelResponse:
        """Execute model and return response.

        Raises any exceptions that occur during model invocation.
        """
        # Get the bound model (with auto-detection if needed)
        model_, effective_response_format = get_bound_model(
            request, tool_node, structured_output_tools
        )
        messages = request.messages
        if request.system_message:
            messages = [request.system_message, *messages]

        output = model_.invoke(messages)
        if name:
            output.name = name

        # Handle model output to get messages and structured_response
        handled_output = handle_model_output(
            output, effective_response_format, structured_output_tools
        )
        messages_list = handled_output["messages"]
        structured_response = handled_output.get("structured_response")

        return ModelResponse(
            result=messages_list,
            structured_response=structured_response,
        )

    return _execute_model_sync


def make_execute_model_async(
    tool_node: ToolNode | None,
    structured_output_tools: dict[str, OutputToolBinding],
    name: str | None,
):
    """Create an asynchronous model executor function.

    This is the core model execution logic wrapped by `awrap_model_call` handlers.
    """
    from langchain.agents.middleware.types import ModelRequest, ModelResponse

    async def _execute_model_async(request: ModelRequest) -> ModelResponse:
        """Execute model asynchronously and return response.

        Raises any exceptions that occur during model invocation.
        """
        # Get the bound model (with auto-detection if needed)
        model_, effective_response_format = get_bound_model(
            request, tool_node, structured_output_tools
        )
        messages = request.messages
        if request.system_message:
            messages = [request.system_message, *messages]

        output = await model_.ainvoke(messages)
        if name:
            output.name = name

        # Handle model output to get messages and structured_response
        handled_output = handle_model_output(
            output, effective_response_format, structured_output_tools
        )
        messages_list = handled_output["messages"]
        structured_response = handled_output.get("structured_response")

        return ModelResponse(
            result=messages_list,
            structured_response=structured_response,
        )

    return _execute_model_async
