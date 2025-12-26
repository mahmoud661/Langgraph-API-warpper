from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable, Sequence

if TYPE_CHECKING:
    from langchain_core.messages import AIMessage, ToolMessage
    from langgraph.types import Command

    from langchain.agents.middleware.types import (
        ModelRequest,
        ModelResponse,
        ToolCallRequest,
        ToolCallWrapper,
    )


def _normalize_to_model_response(result: ModelResponse | AIMessage) -> ModelResponse:
    """Normalize middleware return value to ModelResponse."""
    from langchain_core.messages import AIMessage

    from langchain.agents.middleware.types import ModelResponse

    if isinstance(result, AIMessage):
        return ModelResponse(result=[result], structured_response=None)
    return result


def _chain_model_call_handlers(
    handlers: Sequence[
        Callable[
            [ModelRequest, Callable[[ModelRequest], ModelResponse]],
            ModelResponse | AIMessage,
        ]
    ],
) -> (
    Callable[
        [ModelRequest, Callable[[ModelRequest], ModelResponse]],
        ModelResponse,
    ]
    | None
):

    if not handlers:
        return None

    if len(handlers) == 1:
        # Single handler - wrap to normalize output
        single_handler = handlers[0]

        def normalized_single(
            request: ModelRequest,
            handler: Callable[[ModelRequest], ModelResponse],
        ) -> ModelResponse:
            result = single_handler(request, handler)
            return _normalize_to_model_response(result)

        return normalized_single

    def compose_two(
        outer: Callable[
            [ModelRequest, Callable[[ModelRequest], ModelResponse]],
            ModelResponse | AIMessage,
        ],
        inner: Callable[
            [ModelRequest, Callable[[ModelRequest], ModelResponse]],
            ModelResponse | AIMessage,
        ],
    ) -> Callable[
        [ModelRequest, Callable[[ModelRequest], ModelResponse]],
        ModelResponse,
    ]:
        """Compose two handlers where outer wraps inner."""

        def composed(
            request: ModelRequest,
            handler: Callable[[ModelRequest], ModelResponse],
        ) -> ModelResponse:
            # Create a wrapper that calls inner with the base handler and normalizes
            def inner_handler(req: ModelRequest) -> ModelResponse:
                inner_result = inner(req, handler)
                return _normalize_to_model_response(inner_result)

            # Call outer with the wrapped inner as its handler and normalize
            outer_result = outer(request, inner_handler)
            return _normalize_to_model_response(outer_result)

        return composed

    # Compose right-to-left: outer(inner(innermost(handler)))
    result = handlers[-1]
    for handler in reversed(handlers[:-1]):
        result = compose_two(handler, result)

    # Wrap to ensure final return type is exactly ModelResponse
    def final_normalized(
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        # result here is typed as returning ModelResponse | AIMessage but compose_two normalizes
        final_result = result(request, handler)
        return _normalize_to_model_response(final_result)

    return final_normalized


def _chain_async_model_call_handlers(
    handlers: Sequence[
        Callable[
            [ModelRequest, Callable[[ModelRequest], Awaitable[ModelResponse]]],
            Awaitable[ModelResponse | AIMessage],
        ]
    ],
) -> (
    Callable[
        [ModelRequest, Callable[[ModelRequest], Awaitable[ModelResponse]]],
        Awaitable[ModelResponse],
    ]
    | None
):

    if not handlers:
        return None

    if len(handlers) == 1:
        # Single handler - wrap to normalize output
        single_handler = handlers[0]

        async def normalized_single(
            request: ModelRequest,
            handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
        ) -> ModelResponse:
            result = await single_handler(request, handler)
            return _normalize_to_model_response(result)

        return normalized_single

    def compose_two(
        outer: Callable[
            [ModelRequest, Callable[[ModelRequest], Awaitable[ModelResponse]]],
            Awaitable[ModelResponse | AIMessage],
        ],
        inner: Callable[
            [ModelRequest, Callable[[ModelRequest], Awaitable[ModelResponse]]],
            Awaitable[ModelResponse | AIMessage],
        ],
    ) -> Callable[
        [ModelRequest, Callable[[ModelRequest], Awaitable[ModelResponse]]],
        Awaitable[ModelResponse],
    ]:
        """Compose two async handlers where outer wraps inner."""

        async def composed(
            request: ModelRequest,
            handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
        ) -> ModelResponse:
            # Create a wrapper that calls inner with the base handler and normalizes
            async def inner_handler(req: ModelRequest) -> ModelResponse:
                inner_result = await inner(req, handler)
                return _normalize_to_model_response(inner_result)

            # Call outer with the wrapped inner as its handler and normalize
            outer_result = await outer(request, inner_handler)
            return _normalize_to_model_response(outer_result)

        return composed

    # Compose right-to-left: outer(inner(innermost(handler)))
    result = handlers[-1]
    for handler in reversed(handlers[:-1]):
        result = compose_two(handler, result)

    # Wrap to ensure final return type is exactly ModelResponse
    async def final_normalized(
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        # result here is typed as returning ModelResponse | AIMessage but compose_two normalizes
        final_result = await result(request, handler)
        return _normalize_to_model_response(final_result)

    return final_normalized


def _chain_tool_call_wrappers(
    wrappers: Sequence[ToolCallWrapper],
) -> ToolCallWrapper | None:
    """Compose wrappers into middleware stack (first = outermost).

    Args:
        wrappers: Wrappers in middleware order.

    Returns:
        Composed wrapper, or `None` if empty.

    Example:
        wrapper = _chain_tool_call_wrappers([auth, cache, retry])
        # Request flows: auth -> cache -> retry -> tool
        # Response flows: tool -> retry -> cache -> auth
    """
    from langchain_core.messages import ToolMessage
    from langgraph.types import Command

    from langchain.agents.middleware.types import ToolCallRequest, ToolCallWrapper

    if not wrappers:
        return None

    if len(wrappers) == 1:
        return wrappers[0]

    def compose_two(outer: ToolCallWrapper, inner: ToolCallWrapper) -> ToolCallWrapper:
        """Compose two wrappers where outer wraps inner."""

        def composed(
            request: ToolCallRequest,
            execute: Callable[[ToolCallRequest], ToolMessage | Command],
        ) -> ToolMessage | Command:
            # Create a callable that invokes inner with the original execute
            def call_inner(req: ToolCallRequest) -> ToolMessage | Command:
                return inner(req, execute)

            # Outer can call call_inner multiple times
            return outer(request, call_inner)

        return composed

    # Chain all wrappers: first -> second -> ... -> last
    result = wrappers[-1]
    for wrapper in reversed(wrappers[:-1]):
        result = compose_two(wrapper, result)

    return result


def _chain_async_tool_call_wrappers(
    wrappers: Sequence[
        Callable[
            [
                ToolCallRequest,
                Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
            ],
            Awaitable[ToolMessage | Command],
        ]
    ],
) -> (
    Callable[
        [
            ToolCallRequest,
            Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
        ],
        Awaitable[ToolMessage | Command],
    ]
    | None
):
    """Compose async wrappers into middleware stack (first = outermost).

    Args:
        wrappers: Async wrappers in middleware order.

    Returns:
        Composed async wrapper, or `None` if empty.
    """
    from langchain_core.messages import ToolMessage
    from langgraph.types import Command

    from langchain.agents.middleware.types import ToolCallRequest

    if not wrappers:
        return None

    if len(wrappers) == 1:
        return wrappers[0]

    def compose_two(
        outer: Callable[
            [
                ToolCallRequest,
                Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
            ],
            Awaitable[ToolMessage | Command],
        ],
        inner: Callable[
            [
                ToolCallRequest,
                Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
            ],
            Awaitable[ToolMessage | Command],
        ],
    ) -> Callable[
        [
            ToolCallRequest,
            Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
        ],
        Awaitable[ToolMessage | Command],
    ]:
        """Compose two async wrappers where outer wraps inner."""

        async def composed(
            request: ToolCallRequest,
            execute: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]],
        ) -> ToolMessage | Command:
            # Create an async callable that invokes inner with the original execute
            async def call_inner(req: ToolCallRequest) -> ToolMessage | Command:
                return await inner(req, execute)

            # Outer can call call_inner multiple times
            return await outer(request, call_inner)

        return composed

    # Chain all wrappers: first -> second -> ... -> last
    result = wrappers[-1]
    for wrapper in reversed(wrappers[:-1]):
        result = compose_two(wrapper, result)

    return result
