"""StateGraph construction and node addition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents.middleware.types import AgentMiddleware
from langgraph._internal._runnable import RunnableCallable
from langgraph.graph.state import StateGraph

from src.app.application.nodes import make_amodel_node, make_model_node

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import SystemMessage
    from langchain_core.tools import BaseTool
    from langgraph.prebuilt.tool_node import ToolNode
    from langgraph.typing import ContextT

    from langchain.agents.middleware.types import StateT_co, AgentState, ResponseT
    from langchain.agents.structured_output import (
        AutoStrategy,
        OutputToolBinding,
        ProviderStrategy,
        ToolStrategy,
    )


def create_state_graph(
    resolved_state_schema: type,
    input_schema: type,
    output_schema: type,
    context_schema: type[ContextT] | None,
) -> StateGraph:
    """Create StateGraph with resolved schemas.

    Args:
        resolved_state_schema: Resolved state schema from middleware
        input_schema: Resolved input schema
        output_schema: Resolved output schema
        context_schema: Optional context schema

    Returns:
        StateGraph instance
    """
    return StateGraph(
        state_schema=resolved_state_schema,
        input_schema=input_schema,
        output_schema=output_schema,
        context_schema=context_schema,
    )


def add_model_node(
    graph: StateGraph,
    model: BaseChatModel,
    default_tools: list[BaseTool | dict[str, Any]],
    system_message: SystemMessage | None,
    initial_response_format: ToolStrategy | ProviderStrategy | AutoStrategy | None,
    wrap_model_call_handler: Callable | None,
    awrap_model_call_handler: Callable | None,
    tool_node: ToolNode | None,
    structured_output_tools: dict[str, OutputToolBinding],
    name: str | None,
) -> None:
    """Add model node to graph with sync/async support.

    Args:
        graph: StateGraph to add node to
        model: Chat model instance
        default_tools: Default tools for model
        system_message: Optional system message
        initial_response_format: Response format strategy
        wrap_model_call_handler: Composed sync model handler
        awrap_model_call_handler: Composed async model handler
        tool_node: Optional tool node
        structured_output_tools: Structured output tool bindings
        name: Optional agent name
    """
    model_node = make_model_node(
        model=model,
        default_tools=default_tools,
        system_message=system_message,
        initial_response_format=initial_response_format,
        wrap_model_call_handler=wrap_model_call_handler,
        tool_node=tool_node,
        structured_output_tools=structured_output_tools,
        name=name,
    )

    amodel_node = make_amodel_node(
        model=model,
        default_tools=default_tools,
        system_message=system_message,
        initial_response_format=initial_response_format,
        awrap_model_call_handler=awrap_model_call_handler,
        tool_node=tool_node,
        structured_output_tools=structured_output_tools,
        name=name,
    )

    # Use sync or async based on model capabilities
    graph.add_node("model", RunnableCallable(model_node, amodel_node, trace=False))


def add_tool_node(
    graph: StateGraph,
    tool_node: ToolNode | None,
) -> None:
    """Add tool node to graph if tools exist.

    Args:
        graph: StateGraph to add node to
        tool_node: Optional tool node
    """
    if tool_node is not None:
        graph.add_node("tools", tool_node)


def add_middleware_nodes(
    graph: StateGraph,
    middleware_by_hook: dict[str, list[AgentMiddleware]],
    resolved_state_schema: type,
) -> None:
    """Add middleware nodes to graph.

    Args:
        graph: StateGraph to add nodes to
        middleware_by_hook: Middleware grouped by hook type
        resolved_state_schema: Resolved state schema
    """
    middleware_w_before_agent = middleware_by_hook["before_agent"]
    middleware_w_before_model = middleware_by_hook["before_model"]
    middleware_w_after_model = middleware_by_hook["after_model"]
    middleware_w_after_agent = middleware_by_hook["after_agent"]

    # Combine all middleware to process
    all_middleware_to_add = (
        middleware_w_before_agent
        + middleware_w_before_model
        + middleware_w_after_model
        + middleware_w_after_agent
    )

    for m in all_middleware_to_add:
        # Add before_agent node if implemented
        if (
            m.__class__.before_agent is not AgentMiddleware.before_agent
            or m.__class__.abefore_agent is not AgentMiddleware.abefore_agent
        ):
            sync_before_agent = (
                m.before_agent
                if m.__class__.before_agent is not AgentMiddleware.before_agent
                else None
            )
            async_before_agent = (
                m.abefore_agent
                if m.__class__.abefore_agent is not AgentMiddleware.abefore_agent
                else None
            )
            before_agent_node = RunnableCallable(
                sync_before_agent, async_before_agent, trace=False
            )
            graph.add_node(
                f"{m.name}.before_agent",
                before_agent_node,
                input_schema=resolved_state_schema,
            )

        # Add before_model node if implemented
        if (
            m.__class__.before_model is not AgentMiddleware.before_model
            or m.__class__.abefore_model is not AgentMiddleware.abefore_model
        ):
            sync_before = (
                m.before_model
                if m.__class__.before_model is not AgentMiddleware.before_model
                else None
            )
            async_before = (
                m.abefore_model
                if m.__class__.abefore_model is not AgentMiddleware.abefore_model
                else None
            )
            before_node = RunnableCallable(sync_before, async_before, trace=False)
            graph.add_node(
                f"{m.name}.before_model",
                before_node,
                input_schema=resolved_state_schema,
            )

        # Add after_model node if implemented
        if (
            m.__class__.after_model is not AgentMiddleware.after_model
            or m.__class__.aafter_model is not AgentMiddleware.aafter_model
        ):
            sync_after = (
                m.after_model
                if m.__class__.after_model is not AgentMiddleware.after_model
                else None
            )
            async_after = (
                m.aafter_model
                if m.__class__.aafter_model is not AgentMiddleware.aafter_model
                else None
            )
            after_node = RunnableCallable(sync_after, async_after, trace=False)
            graph.add_node(
                f"{m.name}.after_model", after_node, input_schema=resolved_state_schema
            )

        # Add after_agent node if implemented
        if (
            m.__class__.after_agent is not AgentMiddleware.after_agent
            or m.__class__.aafter_agent is not AgentMiddleware.aafter_agent
        ):
            sync_after_agent = (
                m.after_agent
                if m.__class__.after_agent is not AgentMiddleware.after_agent
                else None
            )
            async_after_agent = (
                m.aafter_agent
                if m.__class__.aafter_agent is not AgentMiddleware.aafter_agent
                else None
            )
            after_agent_node = RunnableCallable(
                sync_after_agent, async_after_agent, trace=False
            )
            graph.add_node(
                f"{m.name}.after_agent",
                after_agent_node,
                input_schema=resolved_state_schema,
            )


__all__ = [
    "create_state_graph",
    "add_model_node",
    "add_tool_node",
    "add_middleware_nodes",
]
