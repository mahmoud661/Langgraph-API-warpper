"""Model binding, execution, and output handling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.runnables import Runnable
    from langchain_core.tools import BaseTool
    from langgraph.prebuilt.tool_node import ToolNode
    from langgraph.runtime import Runtime
    from langgraph.typing import ContextT

    from langchain.agents.middleware.types import (
        AgentState,
        ModelRequest,
        ModelResponse,
    )
    from langchain.agents.structured_output import (
        AutoStrategy,
        OutputToolBinding,
        ProviderStrategy,
        ResponseFormat,
        ToolStrategy,
    )

from src.app.workflow.strategy_detection import (
    _handle_structured_output_error,
    _supports_provider_strategy,
)


def _handle_model_output(
    output: AIMessage,
    effective_response_format: ResponseFormat | None,
    structured_output_tools: dict[str, OutputToolBinding],
) -> dict[str, Any]:
    """Handle model output including structured responses.

    Args:
        output: The AI message output from the model.
        effective_response_format: The actual strategy used
            (may differ from initial if auto-detected).
        structured_output_tools: Dictionary of structured output tool bindings.
    """
    from langchain_core.messages import AIMessage, ToolMessage

    from langchain.agents.structured_output import (
        MultipleStructuredOutputsError,
        ProviderStrategy,
        ProviderStrategyBinding,
        StructuredOutputError,
        StructuredOutputValidationError,
        ToolStrategy,
    )

    # Handle structured output with provider strategy
    if isinstance(effective_response_format, ProviderStrategy):
        if not output.tool_calls:
            provider_strategy_binding = ProviderStrategyBinding.from_schema_spec(
                effective_response_format.schema_spec
            )
            try:
                structured_response = provider_strategy_binding.parse(output)
            except Exception as exc:
                schema_name = getattr(
                    effective_response_format.schema_spec.schema,
                    "__name__",
                    "response_format",
                )
                validation_error = StructuredOutputValidationError(
                    schema_name, exc, output
                )
                raise validation_error from exc
            else:
                return {
                    "messages": [output],
                    "structured_response": structured_response,
                }
        return {"messages": [output]}

    # Handle structured output with tool strategy
    if (
        isinstance(effective_response_format, ToolStrategy)
        and isinstance(output, AIMessage)
        and output.tool_calls
    ):
        structured_tool_calls = [
            tc for tc in output.tool_calls if tc["name"] in structured_output_tools
        ]

        if structured_tool_calls:
            exception: StructuredOutputError | None = None
            if len(structured_tool_calls) > 1:
                # Handle multiple structured outputs error
                tool_names = [tc["name"] for tc in structured_tool_calls]
                exception = MultipleStructuredOutputsError(tool_names, output)
                should_retry, error_message = _handle_structured_output_error(
                    exception, effective_response_format
                )
                if not should_retry:
                    raise exception

                # Add error messages and retry
                tool_messages = [
                    ToolMessage(
                        content=error_message,
                        tool_call_id=tc["id"],
                        name=tc["name"],
                    )
                    for tc in structured_tool_calls
                ]
                return {"messages": [output, *tool_messages]}

            # Handle single structured output
            tool_call = structured_tool_calls[0]
            try:
                structured_tool_binding = structured_output_tools[tool_call["name"]]
                structured_response = structured_tool_binding.parse(tool_call["args"])

                tool_message_content = (
                    effective_response_format.tool_message_content
                    if effective_response_format.tool_message_content
                    else f"Returning structured response: {structured_response}"
                )

                return {
                    "messages": [
                        output,
                        ToolMessage(
                            content=tool_message_content,
                            tool_call_id=tool_call["id"],
                            name=tool_call["name"],
                        ),
                    ],
                    "structured_response": structured_response,
                }
            except Exception as exc:
                exception = StructuredOutputValidationError(
                    tool_call["name"], exc, output
                )
                should_retry, error_message = _handle_structured_output_error(
                    exception, effective_response_format
                )
                if not should_retry:
                    raise exception from exc

                return {
                    "messages": [
                        output,
                        ToolMessage(
                            content=error_message,
                            tool_call_id=tool_call["id"],
                            name=tool_call["name"],
                        ),
                    ],
                }

    return {"messages": [output]}


def _get_bound_model(
    request: ModelRequest,
    tool_node: ToolNode | None,
    structured_output_tools: dict[str, OutputToolBinding],
) -> tuple[Runnable, ResponseFormat | None]:
    """Get the model with appropriate tool bindings.

    Performs auto-detection of strategy if needed based on model capabilities.

    Args:
        request: The model request containing model, tools, and response format.
        tool_node: The tool node containing available tools.
        structured_output_tools: Dictionary of structured output tool bindings.

    Returns:
        Tuple of `(bound_model, effective_response_format)` where
        `effective_response_format` is the actual strategy used (may differ from
        initial if auto-detected).
    """
    from langchain_core.tools import BaseTool

    from langchain.agents.structured_output import (
        AutoStrategy,
        ProviderStrategy,
        ToolStrategy,
    )

    # Validate ONLY client-side tools that need to exist in tool_node
    # Build map of available client-side tools from the ToolNode
    # (which has already converted callables)
    available_tools_by_name = {}
    if tool_node:
        available_tools_by_name = tool_node.tools_by_name.copy()

    # Check if any requested tools are unknown CLIENT-SIDE tools
    unknown_tool_names = []
    for t in request.tools:
        # Only validate BaseTool instances (skip built-in dict tools)
        if isinstance(t, dict):
            continue
        if isinstance(t, BaseTool) and t.name not in available_tools_by_name:
            unknown_tool_names.append(t.name)

    if unknown_tool_names:
        available_tool_names = sorted(available_tools_by_name.keys())
        msg = (
            f"Middleware returned unknown tool names: {unknown_tool_names}\n\n"
            f"Available client-side tools: {available_tool_names}\n\n"
            "To fix this issue:\n"
            "1. Ensure the tools are passed to create_agent() via "
            "the 'tools' parameter\n"
            "2. If using custom middleware with tools, ensure "
            "they're registered via middleware.tools attribute\n"
            "3. Verify that tool names in ModelRequest.tools match "
            "the actual tool.name values\n"
            "Note: Built-in provider tools (dict format) can be added dynamically."
        )
        raise ValueError(msg)

    # Determine effective response format (auto-detect if needed)
    effective_response_format: ResponseFormat | None
    if isinstance(request.response_format, AutoStrategy):
        # User provided raw schema via AutoStrategy - auto-detect best strategy based on model
        if _supports_provider_strategy(request.model, tools=request.tools):
            # Model supports provider strategy - use it
            effective_response_format = ProviderStrategy(
                schema=request.response_format.schema
            )
        else:
            # Model doesn't support provider strategy - use ToolStrategy
            effective_response_format = ToolStrategy(
                schema=request.response_format.schema
            )
    else:
        # User explicitly specified a strategy - preserve it
        effective_response_format = request.response_format

    # Build final tools list including structured output tools
    # request.tools now only contains BaseTool instances (converted from callables)
    # and dicts (built-ins)
    final_tools = list(request.tools)
    if isinstance(effective_response_format, ToolStrategy):
        # Add structured output tools to final tools list
        structured_tools = [info.tool for info in structured_output_tools.values()]
        final_tools.extend(structured_tools)

    # Bind model based on effective response format
    if isinstance(effective_response_format, ProviderStrategy):
        # (Backward compatibility) Use OpenAI format structured output
        kwargs = effective_response_format.to_model_kwargs()
        return (
            request.model.bind_tools(
                final_tools, strict=True, **kwargs, **request.model_settings
            ),
            effective_response_format,
        )

    if isinstance(effective_response_format, ToolStrategy):
        # Current implementation requires that tools used for structured output
        # have to be declared upfront when creating the agent as part of the
        # response format. Middleware is allowed to change the response format
        # to a subset of the original structured tools when using ToolStrategy,
        # but not to add new structured tools that weren't declared upfront.
        # Compute output binding
        for tc in effective_response_format.schema_specs:
            if tc.name not in structured_output_tools:
                msg = (
                    f"ToolStrategy specifies tool '{tc.name}' "
                    "which wasn't declared in the original "
                    "response format when creating the agent."
                )
                raise ValueError(msg)

        # Force tool use if we have structured output tools
        tool_choice = "any" if structured_output_tools else request.tool_choice
        return (
            request.model.bind_tools(
                final_tools, tool_choice=tool_choice, **request.model_settings
            ),
            effective_response_format,
        )

    # No structured output - standard model binding
    if final_tools:
        return (
            request.model.bind_tools(
                final_tools, tool_choice=request.tool_choice, **request.model_settings
            ),
            None,
        )
    return request.model.bind(**request.model_settings), None


def make_execute_model_sync(
    tool_node: ToolNode | None,
    structured_output_tools: dict[str, OutputToolBinding],
    name: str | None,
):
    """Create a sync model execution function.

    Args:
        tool_node: The tool node containing available tools.
        structured_output_tools: Dictionary of structured output tool bindings.
        name: Optional name for the agent.

    Returns:
        A function that executes the model synchronously.
    """
    from langchain.agents.middleware.types import ModelRequest, ModelResponse

    def _execute_model_sync(request: ModelRequest) -> ModelResponse:
        """Execute model and return response.

        This is the core model execution logic wrapped by `wrap_model_call` handlers.
        Raises any exceptions that occur during model invocation.
        """
        # Get the bound model (with auto-detection if needed)
        model_, effective_response_format = _get_bound_model(
            request, tool_node, structured_output_tools
        )
        messages = request.messages
        if request.system_message:
            messages = [request.system_message, *messages]

        output = model_.invoke(messages)
        if name:
            output.name = name

        # Handle model output to get messages and structured_response
        handled_output = _handle_model_output(
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
    """Create an async model execution function.

    Args:
        tool_node: The tool node containing available tools.
        structured_output_tools: Dictionary of structured output tool bindings.
        name: Optional name for the agent.

    Returns:
        A function that executes the model asynchronously.
    """
    from langchain.agents.middleware.types import ModelRequest, ModelResponse

    async def _execute_model_async(request: ModelRequest) -> ModelResponse:
        """Execute model asynchronously and return response.

        This is the core async model execution logic wrapped by `wrap_model_call`
        handlers.

        Raises any exceptions that occur during model invocation.
        """
        # Get the bound model (with auto-detection if needed)
        model_, effective_response_format = _get_bound_model(
            request, tool_node, structured_output_tools
        )
        messages = request.messages
        if request.system_message:
            messages = [request.system_message, *messages]

        output = await model_.ainvoke(messages)
        if name:
            output.name = name

        # Handle model output to get messages and structured_response
        handled_output = _handle_model_output(
            output, effective_response_format, structured_output_tools
        )
        messages_list = handled_output["messages"]
        structured_response = handled_output.get("structured_response")

        return ModelResponse(
            result=messages_list,
            structured_response=structured_response,
        )

    return _execute_model_async


def make_model_node(
    model: BaseChatModel,
    default_tools: list[BaseTool],
    system_message,
    initial_response_format,
    wrap_model_call_handler,
    tool_node: ToolNode | None,
    structured_output_tools: dict[str, OutputToolBinding],
    name: str | None,
):
    """Create a sync model node function.

    Args:
        model: The chat model to use.
        default_tools: Default tools available to the model.
        system_message: System message for the model.
        initial_response_format: Initial response format configuration.
        wrap_model_call_handler: Composed sync middleware handler.
        tool_node: The tool node containing available tools.
        structured_output_tools: Dictionary of structured output tool bindings.
        name: Optional name for the agent.

    Returns:
        A function that handles sync model requests.
    """
    from langchain.agents.middleware.types import AgentState, ModelRequest

    _execute_model_sync = make_execute_model_sync(
        tool_node, structured_output_tools, name
    )

    def model_node(state: AgentState, runtime: Runtime[ContextT]) -> dict[str, Any]:
        """Sync model request handler with sequential middleware processing."""
        request = ModelRequest(
            model=model,
            tools=default_tools,
            system_message=system_message,
            response_format=initial_response_format,
            messages=state["messages"],
            tool_choice=None,
            state=state,
            runtime=runtime,
        )

        if wrap_model_call_handler is None:
            # No handlers - execute directly
            response = _execute_model_sync(request)
        else:
            # Call composed handler with base handler
            response = wrap_model_call_handler(request, _execute_model_sync)

        # Extract state updates from ModelResponse
        state_updates = {"messages": response.result}
        if response.structured_response is not None:
            state_updates["structured_response"] = response.structured_response

        return state_updates

    return model_node


def make_amodel_node(
    model: BaseChatModel,
    default_tools: list[BaseTool],
    system_message,
    initial_response_format,
    awrap_model_call_handler,
    tool_node: ToolNode | None,
    structured_output_tools: dict[str, OutputToolBinding],
    name: str | None,
):
    """Create an async model node function.

    Args:
        model: The chat model to use.
        default_tools: Default tools available to the model.
        system_message: System message for the model.
        initial_response_format: Initial response format configuration.
        awrap_model_call_handler: Composed async middleware handler.
        tool_node: The tool node containing available tools.
        structured_output_tools: Dictionary of structured output tool bindings.
        name: Optional name for the agent.

    Returns:
        A function that handles async model requests.
    """
    from langchain.agents.middleware.types import AgentState, ModelRequest

    _execute_model_async = make_execute_model_async(
        tool_node, structured_output_tools, name
    )

    async def amodel_node(
        state: AgentState, runtime: Runtime[ContextT]
    ) -> dict[str, Any]:
        """Async model request handler with sequential middleware processing."""
        request = ModelRequest(
            model=model,
            tools=default_tools,
            system_message=system_message,
            response_format=initial_response_format,
            messages=state["messages"],
            tool_choice=None,
            state=state,
            runtime=runtime,
        )

        if awrap_model_call_handler is None:
            # No async handlers - execute directly
            response = await _execute_model_async(request)
        else:
            # Call composed async handler with base handler
            response = await awrap_model_call_handler(request, _execute_model_async)

        # Extract state updates from ModelResponse
        state_updates = {"messages": response.result}
        if response.structured_response is not None:
            state_updates["structured_response"] = response.structured_response

        return state_updates

    return amodel_node
