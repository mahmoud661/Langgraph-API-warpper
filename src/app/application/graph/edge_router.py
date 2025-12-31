"""Edge routing and graph compilation."""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from langgraph._internal._runnable import RunnableCallable
from langgraph.constants import END, START
from langgraph.graph.state import StateGraph

from src.app.application.edges import (
    add_middleware_edge,
    make_model_to_model_edge,
    make_model_to_tools_edge,
    make_tools_to_model_edge,
)
from src.app.application.graph.schema_resolver import get_can_jump_to

if TYPE_CHECKING:
    from langgraph.prebuilt.tool_node import ToolNode
    from langgraph.cache.base import BaseCache
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer
    from langgraph.graph.state import CompiledStateGraph

    from langchain.agents.middleware.types import (
        AgentMiddleware,
        AgentState,
        ResponseT,
        _InputAgentState,
        _OutputAgentState,
    )
    from langchain.agents.structured_output import OutputToolBinding, ResponseFormat
    from langgraph.typing import ContextT


def determine_routing_nodes(
    middleware_by_hook: dict[str, list[AgentMiddleware]],
) -> tuple[str, str, str, str]:
    """Determine entry, loop entry, loop exit, and exit nodes.

    Args:
        middleware_by_hook: Middleware grouped by hook type

    Returns:
        Tuple of (entry_node, loop_entry_node, loop_exit_node, exit_node)
    """
    middleware_w_before_agent = middleware_by_hook["before_agent"]
    middleware_w_before_model = middleware_by_hook["before_model"]
    middleware_w_after_model = middleware_by_hook["after_model"]
    middleware_w_after_agent = middleware_by_hook["after_agent"]

    # Entry node (runs once at start): before_agent -> before_model -> model
    if middleware_w_before_agent:
        entry_node = f"{middleware_w_before_agent[0].name}.before_agent"
    elif middleware_w_before_model:
        entry_node = f"{middleware_w_before_model[0].name}.before_model"
    else:
        entry_node = "model"

    # Loop entry node (beginning of agent loop, excludes before_agent)
    if middleware_w_before_model:
        loop_entry_node = f"{middleware_w_before_model[0].name}.before_model"
    else:
        loop_entry_node = "model"

    # Loop exit node (end of each iteration, can run multiple times)
    if middleware_w_after_model:
        loop_exit_node = f"{middleware_w_after_model[0].name}.after_model"
    else:
        loop_exit_node = "model"

    # Exit node (runs once at end): after_agent or END
    if middleware_w_after_agent:
        exit_node = f"{middleware_w_after_agent[-1].name}.after_agent"
    else:
        exit_node = END

    return entry_node, loop_entry_node, loop_exit_node, exit_node


def add_start_edge(
    graph: StateGraph,
    entry_node: str,
) -> None:
    """Add edge from START to entry node.

    Args:
        graph: StateGraph to add edge to
        entry_node: Node to connect from START
    """
    graph.add_edge(START, entry_node)


def add_tool_edges(
    graph: StateGraph,
    tool_node: ToolNode,
    loop_entry_node: str,
    loop_exit_node: str,
    exit_node: str,
    response_format: ResponseFormat[ResponseT] | type[ResponseT] | None,
    structured_output_tools: dict[str, OutputToolBinding],
) -> None:
    """Add conditional edges for tool routing.

    Args:
        graph: StateGraph to add edges to
        tool_node: Tool node instance
        loop_entry_node: Node to loop back to
        loop_exit_node: Node at end of iteration
        exit_node: Final exit node
        response_format: Response format configuration
        structured_output_tools: Structured output tool bindings
    """
    # Only include exit_node in destinations if any tool has return_direct=True
    # or if there are structured output tools
    tools_to_model_destinations = [loop_entry_node]
    if (
        any(tool.return_direct for tool in tool_node.tools_by_name.values())
        or structured_output_tools
    ):
        tools_to_model_destinations.append(exit_node)

    graph.add_conditional_edges(
        "tools",
        RunnableCallable(
            make_tools_to_model_edge(
                tool_node=tool_node,
                model_destination=loop_entry_node,
                structured_output_tools=structured_output_tools,
                end_destination=exit_node,
            ),
            trace=False,
        ),
        tools_to_model_destinations,
    )

    # base destinations are tools and exit_node
    # we add the loop_entry node to edge destinations if:
    # - there is an after model hook(s) -- allows jump_to to model
    #   potentially artificially injected tool messages, ex HITL
    # - there is a response format -- to allow for jumping to model to handle
    #   regenerating structured output tool calls
    model_to_tools_destinations = ["tools", exit_node]
    if response_format or loop_exit_node != "model":
        model_to_tools_destinations.append(loop_entry_node)

    graph.add_conditional_edges(
        loop_exit_node,
        RunnableCallable(
            make_model_to_tools_edge(
                model_destination=loop_entry_node,
                structured_output_tools=structured_output_tools,
                end_destination=exit_node,
            ),
            trace=False,
        ),
        model_to_tools_destinations,
    )


def add_structured_output_edges(
    graph: StateGraph,
    loop_entry_node: str,
    loop_exit_node: str,
    exit_node: str,
) -> None:
    """Add conditional edges for structured output (no tools).

    Args:
        graph: StateGraph to add edges to
        loop_entry_node: Node to loop back to
        loop_exit_node: Node at end of iteration
        exit_node: Final exit node
    """
    graph.add_conditional_edges(
        loop_exit_node,
        RunnableCallable(
            make_model_to_model_edge(
                model_destination=loop_entry_node,
                end_destination=exit_node,
            ),
            trace=False,
        ),
        [loop_entry_node, exit_node],
    )


def add_simple_edge(
    graph: StateGraph,
    loop_exit_node: str,
    exit_node: str,
    middleware_by_hook: dict[str, list[AgentMiddleware]],
    loop_entry_node: str,
) -> None:
    """Add simple edge when no tools or structured output.

    Args:
        graph: StateGraph to add edge to
        loop_exit_node: Node at end of iteration
        exit_node: Final exit node
        middleware_by_hook: Middleware grouped by hook type
        loop_entry_node: Node to loop back to
    """
    middleware_w_after_model = middleware_by_hook["after_model"]

    if loop_exit_node == "model":
        # If no tools and no after_model, go directly to exit_node
        graph.add_edge(loop_exit_node, exit_node)
    else:
        # No tools but we have after_model - connect after_model to exit_node
        add_middleware_edge(
            graph,
            name=f"{middleware_w_after_model[0].name}.after_model",
            default_destination=exit_node,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=get_can_jump_to(middleware_w_after_model[0], "after_model"),
        )


def add_middleware_edges(
    graph: StateGraph,
    middleware_by_hook: dict[str, list[AgentMiddleware]],
    loop_entry_node: str,
    exit_node: str,
) -> None:
    """Add all middleware edges to graph.

    Args:
        graph: StateGraph to add edges to
        middleware_by_hook: Middleware grouped by hook type
        loop_entry_node: Node to loop back to
        exit_node: Final exit node
    """
    middleware_w_before_agent = middleware_by_hook["before_agent"]
    middleware_w_before_model = middleware_by_hook["before_model"]
    middleware_w_after_model = middleware_by_hook["after_model"]
    middleware_w_after_agent = middleware_by_hook["after_agent"]

    # Add before_agent middleware edges
    if middleware_w_before_agent:
        for m1, m2 in itertools.pairwise(middleware_w_before_agent):
            add_middleware_edge(
                graph,
                name=f"{m1.name}.before_agent",
                default_destination=f"{m2.name}.before_agent",
                model_destination=loop_entry_node,
                end_destination=exit_node,
                can_jump_to=get_can_jump_to(m1, "before_agent"),
            )
        # Connect last before_agent to loop_entry_node
        add_middleware_edge(
            graph,
            name=f"{middleware_w_before_agent[-1].name}.before_agent",
            default_destination=loop_entry_node,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=get_can_jump_to(middleware_w_before_agent[-1], "before_agent"),
        )

    # Add before_model middleware edges
    if middleware_w_before_model:
        for m1, m2 in itertools.pairwise(middleware_w_before_model):
            add_middleware_edge(
                graph,
                name=f"{m1.name}.before_model",
                default_destination=f"{m2.name}.before_model",
                model_destination=loop_entry_node,
                end_destination=exit_node,
                can_jump_to=get_can_jump_to(m1, "before_model"),
            )
        # Go directly to model after the last before_model
        add_middleware_edge(
            graph,
            name=f"{middleware_w_before_model[-1].name}.before_model",
            default_destination="model",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=get_can_jump_to(middleware_w_before_model[-1], "before_model"),
        )

    # Add after_model middleware edges
    if middleware_w_after_model:
        graph.add_edge("model", f"{middleware_w_after_model[-1].name}.after_model")
        for idx in range(len(middleware_w_after_model) - 1, 0, -1):
            m1 = middleware_w_after_model[idx]
            m2 = middleware_w_after_model[idx - 1]
            add_middleware_edge(
                graph,
                name=f"{m1.name}.after_model",
                default_destination=f"{m2.name}.after_model",
                model_destination=loop_entry_node,
                end_destination=exit_node,
                can_jump_to=get_can_jump_to(m1, "after_model"),
            )

    # Add after_agent middleware edges
    if middleware_w_after_agent:
        # Chain after_agent middleware (runs once at the very end, before END)
        for idx in range(len(middleware_w_after_agent) - 1, 0, -1):
            m1 = middleware_w_after_agent[idx]
            m2 = middleware_w_after_agent[idx - 1]
            add_middleware_edge(
                graph,
                name=f"{m1.name}.after_agent",
                default_destination=f"{m2.name}.after_agent",
                model_destination=loop_entry_node,
                end_destination=exit_node,
                can_jump_to=get_can_jump_to(m1, "after_agent"),
            )

        # Connect the last after_agent to END
        add_middleware_edge(
            graph,
            name=f"{middleware_w_after_agent[0].name}.after_agent",
            default_destination=END,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=get_can_jump_to(middleware_w_after_agent[0], "after_agent"),
        )


def compile_graph(
    graph: StateGraph,
    checkpointer: Checkpointer | None,
    store: BaseStore | None,
    interrupt_before: list[str] | None,
    interrupt_after: list[str] | None,
    debug: bool,
    name: str | None,
    cache: BaseCache | None,
) -> CompiledStateGraph:
    """Compile state graph with configuration.

    Args:
        graph: StateGraph to compile
        checkpointer: Optional checkpointer
        store: Optional store
        interrupt_before: Optional list of nodes to interrupt before
        interrupt_after: Optional list of nodes to interrupt after
        debug: Enable debug mode
        name: Optional graph name
        cache: Optional cache

    Returns:
        Compiled state graph
    """
    return graph.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config({"recursion_limit": 10_000})


__all__ = [
    "determine_routing_nodes",
    "add_start_edge",
    "add_tool_edges",
    "add_structured_output_edges",
    "add_simple_edge",
    "add_middleware_edges",
    "compile_graph",
]
