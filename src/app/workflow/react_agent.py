"""Thin facade for agent creation - delegates to application layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.application.agent import create_agent_impl

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


def create_agent(
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
    """Create an agent with the given model, tools, and configuration.

    This is a thin facade that delegates to the application layer implementation.

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
    return create_agent_impl(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
        response_format=response_format,
        state_schema=state_schema,
        context_schema=context_schema,
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        debug=debug,
        name=name,
        cache=cache,
    )


__all__ = [
    "create_agent",
]
