"""Agent factory - orchestrates agent creation from components."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.application.agent.model_setup import (
    initialize_model,
    prepare_system_message,
)
from src.app.application.agent.response_format_handler import (
    convert_response_format,
    create_structured_output_tools,
)
from src.app.application.agent.tool_setup import (
    collect_middleware_with_tool_wrappers,
    create_tool_wrappers,
    setup_tools,
)
from src.app.application.agent.middleware_processor import (
    validate_middleware,
    collect_middleware_by_hook,
    create_model_call_handlers,
    resolve_state_schemas,
)
from src.app.application.graph.graph_builder import (
    create_state_graph,
    add_model_node,
    add_tool_node,
    add_middleware_nodes,
)
from src.app.application.graph.edge_router import (
    determine_routing_nodes,
    add_start_edge,
    add_tool_edges,
    add_structured_output_edges,
    add_simple_edge,
    add_middleware_edges,
    compile_graph,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import SystemMessage
    from langchain_core.tools import BaseTool
    from langgraph.cache.base import BaseCache
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer
    from langgraph.typing import ContextT

    from langchain.agents.middleware.types import (
        AgentMiddleware,
        AgentState,
        ResponseT,
        StateT_co,
        _InputAgentState,
        _OutputAgentState,
    )
    from langchain.agents.structured_output import ResponseFormat


def create_agent_impl(
    model: str | BaseChatModel,
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    *,
    system_prompt: str | SystemMessage | None = None,
    middleware: Sequence[AgentMiddleware[StateT_co, ContextT]] = (),
    response_format: ResponseFormat[ResponseT] | type[ResponseT] | None = None,
    state_schema: type[AgentState[ResponseT]] | None = None,
    context_schema: type[ContextT] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    interrupt_before: list[str] | None = None,
    interrupt_after: list[str] | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph[
    AgentState[ResponseT], ContextT, _InputAgentState, _OutputAgentState[ResponseT]
]:
    """Implementation of agent creation - orchestrates all components.

    Args:
        model: Chat model identifier or instance
        tools: Optional sequence of tools
        system_prompt: Optional system prompt
        middleware: Sequence of middleware instances
        response_format: Optional response format specification
        state_schema: Optional state schema
        context_schema: Optional context schema
        checkpointer: Optional checkpointer
        store: Optional store
        interrupt_before: Optional list of nodes to interrupt before
        interrupt_after: Optional list of nodes to interrupt after
        debug: Enable debug mode
        name: Optional agent name
        cache: Optional cache

    Returns:
        Compiled state graph
    """
    # Phase 1: Initialize model and system message
    model_instance = initialize_model(model)
    system_message = prepare_system_message(system_prompt)

    # Phase 2: Convert response format and setup structured output
    initial_response_format, tool_strategy_for_setup = convert_response_format(
        response_format
    )
    structured_output_tools = create_structured_output_tools(tool_strategy_for_setup)

    # Phase 3: Setup tool wrappers
    middleware_w_wrap_tool_call, middleware_w_awrap_tool_call = (
        collect_middleware_with_tool_wrappers(middleware)
    )
    wrap_tool_call_wrapper, awrap_tool_call_wrapper = create_tool_wrappers(
        middleware_w_wrap_tool_call, middleware_w_awrap_tool_call
    )

    # Phase 4: Setup tools and tool node
    tool_node, default_tools = setup_tools(
        tools, middleware, wrap_tool_call_wrapper, awrap_tool_call_wrapper
    )

    # Phase 5: Validate and process middleware
    validate_middleware(middleware)
    middleware_by_hook = collect_middleware_by_hook(middleware)
    wrap_model_call_handler, awrap_model_call_handler = create_model_call_handlers(
        middleware_by_hook["wrap_model_call"], middleware_by_hook["awrap_model_call"]
    )

    # Phase 6: Resolve state schemas
    resolved_state_schema, input_schema, output_schema = resolve_state_schemas(
        middleware, state_schema
    )

    # Phase 7: Create graph and add nodes
    graph = create_state_graph(
        resolved_state_schema, input_schema, output_schema, context_schema
    )

    add_model_node(
        graph,
        model_instance,
        default_tools,
        system_message,
        initial_response_format,
        wrap_model_call_handler,
        awrap_model_call_handler,
        tool_node,
        structured_output_tools,
        name,
    )

    add_tool_node(graph, tool_node)
    add_middleware_nodes(graph, middleware_by_hook, resolved_state_schema)

    # Phase 8: Determine routing nodes
    entry_node, loop_entry_node, loop_exit_node, exit_node = determine_routing_nodes(
        middleware_by_hook
    )

    # Phase 9: Add edges
    add_start_edge(graph, entry_node)

    if tool_node is not None:
        add_tool_edges(
            graph,
            tool_node,
            loop_entry_node,
            loop_exit_node,
            exit_node,
            response_format,
            structured_output_tools,
        )
    elif len(structured_output_tools) > 0:
        add_structured_output_edges(graph, loop_entry_node, loop_exit_node, exit_node)
    else:
        add_simple_edge(
            graph, loop_exit_node, exit_node, middleware_by_hook, loop_entry_node
        )

    add_middleware_edges(graph, middleware_by_hook, loop_entry_node, exit_node)

    # Phase 10: Compile and return
    return compile_graph(
        graph,
        checkpointer,
        store,
        interrupt_before,
        interrupt_after,
        debug,
        name,
        cache,
    )


__all__ = [
    "create_agent_impl",
]
