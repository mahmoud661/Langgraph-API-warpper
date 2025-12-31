"""Tool setup and organization for agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents.middleware.types import AgentMiddleware
from langgraph.prebuilt.tool_node import ToolNode

from src.app.application.middleware import (
    chain_async_tool_call_wrappers,
    chain_tool_call_wrappers,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from langchain_core.tools import BaseTool
    from langchain.agents.structured_output import OutputToolBinding
    from langgraph.typing import ContextT
    from langchain.agents.middleware.types import StateT_co


def collect_middleware_with_tool_wrappers(
    middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> tuple[
    list[AgentMiddleware[StateT_co, ContextT]],
    list[AgentMiddleware[StateT_co, ContextT]],
]:
    """Collect middleware that implements wrap_tool_call or awrap_tool_call.

    Args:
        middleware: Sequence of middleware instances

    Returns:
        Tuple of (middleware_w_wrap_tool_call, middleware_w_awrap_tool_call)
    """
    # Collect middleware with wrap_tool_call or awrap_tool_call hooks
    middleware_w_wrap_tool_call = [
        m
        for m in middleware
        if m.__class__.wrap_tool_call is not AgentMiddleware.wrap_tool_call
        or m.__class__.awrap_tool_call is not AgentMiddleware.awrap_tool_call
    ]

    middleware_w_awrap_tool_call = [
        m
        for m in middleware
        if m.__class__.awrap_tool_call is not AgentMiddleware.awrap_tool_call
        or m.__class__.wrap_tool_call is not AgentMiddleware.wrap_tool_call
    ]

    return middleware_w_wrap_tool_call, middleware_w_awrap_tool_call


def create_tool_wrappers(
    middleware_w_wrap_tool_call: list[AgentMiddleware[StateT_co, ContextT]],
    middleware_w_awrap_tool_call: list[AgentMiddleware[StateT_co, ContextT]],
) -> tuple[Callable | None, Callable | None]:
    """Create composed tool call wrappers from middleware.

    Args:
        middleware_w_wrap_tool_call: Middleware with sync tool wrappers
        middleware_w_awrap_tool_call: Middleware with async tool wrappers

    Returns:
        Tuple of (wrap_tool_call_wrapper, awrap_tool_call_wrapper)
    """
    wrap_tool_call_wrapper = None
    if middleware_w_wrap_tool_call:
        wrappers = [m.wrap_tool_call for m in middleware_w_wrap_tool_call]
        wrap_tool_call_wrapper = chain_tool_call_wrappers(wrappers)

    awrap_tool_call_wrapper = None
    if middleware_w_awrap_tool_call:
        async_wrappers = [m.awrap_tool_call for m in middleware_w_awrap_tool_call]
        awrap_tool_call_wrapper = chain_async_tool_call_wrappers(async_wrappers)

    return wrap_tool_call_wrapper, awrap_tool_call_wrapper


def setup_tools(
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None,
    middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
    wrap_tool_call_wrapper: Callable | None,
    awrap_tool_call_wrapper: Callable | None,
) -> tuple[ToolNode | None, list[BaseTool | dict[str, Any]]]:
    """Setup tool node and default tools list.

    Args:
        tools: User-provided tools (can be BaseTool, callables, or dicts)
        middleware: Sequence of middleware instances
        wrap_tool_call_wrapper: Composed sync tool wrapper
        awrap_tool_call_wrapper: Composed async tool wrapper

    Returns:
        Tuple of (tool_node, default_tools)
        - tool_node: ToolNode instance if client-side tools exist, else None
        - default_tools: List of tools for ModelRequest initialization
    """
    # Handle tools being None or empty
    if tools is None:
        tools = []

    # Extract middleware tools
    middleware_tools = [t for m in middleware for t in getattr(m, "tools", [])]

    # Extract built-in provider tools (dict format) and regular tools (BaseTool/callables)
    built_in_tools = [t for t in tools if isinstance(t, dict)]
    regular_tools = [t for t in tools if not isinstance(t, dict)]

    # Tools that require client-side execution (must be in ToolNode)
    available_tools = middleware_tools + regular_tools

    # Only create ToolNode if we have client-side tools
    tool_node = (
        ToolNode(
            tools=available_tools,
            wrap_tool_call=wrap_tool_call_wrapper,
            awrap_tool_call=awrap_tool_call_wrapper,
        )
        if available_tools
        else None
    )

    # Default tools for ModelRequest initialization
    # Use converted BaseTool instances from ToolNode (not raw callables)
    # Include built-ins and converted tools (can be changed dynamically by middleware)
    # Structured tools are NOT included - they're added dynamically based on response_format
    if tool_node:
        default_tools = list(tool_node.tools_by_name.values()) + built_in_tools
    else:
        default_tools = list(built_in_tools)

    return tool_node, default_tools


__all__ = [
    "collect_middleware_with_tool_wrappers",
    "create_tool_wrappers",
    "setup_tools",
]
