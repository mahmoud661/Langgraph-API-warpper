"""Middleware validation and processing."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents.middleware.types import AgentMiddleware

from src.app.application.middleware import (
    chain_async_model_call_handlers,
    chain_model_call_handlers,
)
from src.app.application.graph.schema_resolver import resolve_schema

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from langgraph.typing import ContextT
    from langchain.agents.middleware.types import StateT_co, AgentState, ResponseT


def validate_middleware(
    middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> None:
    """Validate middleware instances for duplicates.

    Args:
        middleware: Sequence of middleware instances

    Raises:
        AssertionError: If duplicate middleware instances are found
    """
    if len({m.name for m in middleware}) != len(middleware):
        msg = "Please remove duplicate middleware instances."
        raise AssertionError(msg)


def collect_middleware_by_hook(
    middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> dict[str, list[AgentMiddleware[StateT_co, ContextT]]]:
    """Collect middleware grouped by hook type.

    Args:
        middleware: Sequence of middleware instances

    Returns:
        Dictionary mapping hook names to lists of middleware implementing them
    """
    return {
        "before_agent": [
            m
            for m in middleware
            if m.__class__.before_agent is not AgentMiddleware.before_agent
            or m.__class__.abefore_agent is not AgentMiddleware.abefore_agent
        ],
        "before_model": [
            m
            for m in middleware
            if m.__class__.before_model is not AgentMiddleware.before_model
            or m.__class__.abefore_model is not AgentMiddleware.abefore_model
        ],
        "after_model": [
            m
            for m in middleware
            if m.__class__.after_model is not AgentMiddleware.after_model
            or m.__class__.aafter_model is not AgentMiddleware.aafter_model
        ],
        "after_agent": [
            m
            for m in middleware
            if m.__class__.after_agent is not AgentMiddleware.after_agent
            or m.__class__.aafter_agent is not AgentMiddleware.aafter_agent
        ],
        "wrap_model_call": [
            m
            for m in middleware
            if m.__class__.wrap_model_call is not AgentMiddleware.wrap_model_call
            or m.__class__.awrap_model_call is not AgentMiddleware.awrap_model_call
        ],
        "awrap_model_call": [
            m
            for m in middleware
            if m.__class__.awrap_model_call is not AgentMiddleware.awrap_model_call
            or m.__class__.wrap_model_call is not AgentMiddleware.wrap_model_call
        ],
    }


def create_model_call_handlers(
    middleware_w_wrap_model_call: list[AgentMiddleware[StateT_co, ContextT]],
    middleware_w_awrap_model_call: list[AgentMiddleware[StateT_co, ContextT]],
) -> tuple[Callable | None, Callable | None]:
    """Create composed model call handlers from middleware.

    Args:
        middleware_w_wrap_model_call: Middleware with sync model wrappers
        middleware_w_awrap_model_call: Middleware with async model wrappers

    Returns:
        Tuple of (wrap_model_call_handler, awrap_model_call_handler)
    """
    wrap_model_call_handler = None
    if middleware_w_wrap_model_call:
        sync_handlers = [m.wrap_model_call for m in middleware_w_wrap_model_call]
        wrap_model_call_handler = chain_model_call_handlers(sync_handlers)

    awrap_model_call_handler = None
    if middleware_w_awrap_model_call:
        async_handlers = [m.awrap_model_call for m in middleware_w_awrap_model_call]
        awrap_model_call_handler = chain_async_model_call_handlers(async_handlers)

    return wrap_model_call_handler, awrap_model_call_handler


def resolve_state_schemas(
    middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
    state_schema: type[AgentState[ResponseT]] | None,
) -> tuple[type, type, type]:
    """Resolve state schemas from middleware and user-provided schema.

    Args:
        middleware: Sequence of middleware instances
        state_schema: User-provided state schema (optional)

    Returns:
        Tuple of (resolved_state_schema, input_schema, output_schema)
    """
    from langchain.agents.middleware.types import AgentState

    state_schemas: set[type] = {m.state_schema for m in middleware}
    # Use provided state_schema if available, otherwise use base AgentState
    base_state = state_schema if state_schema is not None else AgentState
    state_schemas.add(base_state)

    resolved_state_schema = resolve_schema(state_schemas, "StateSchema", None)
    input_schema = resolve_schema(state_schemas, "InputSchema", "input")
    output_schema = resolve_schema(state_schemas, "OutputSchema", "output")

    return resolved_state_schema, input_schema, output_schema


__all__ = [
    "validate_middleware",
    "collect_middleware_by_hook",
    "create_model_call_handlers",
    "resolve_state_schemas",
]
