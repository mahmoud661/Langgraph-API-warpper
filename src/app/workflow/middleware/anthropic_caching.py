"""Anthropic prompt caching middleware for reducing API costs.

This middleware enables Anthropic's prompt caching feature which allows
caching of system prompts and conversation history to reduce API costs
and improve response times.
"""

from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..state import AgentState


class AnthropicPromptCachingMiddleware:
    """Middleware that adds cache_control breakpoints for Anthropic models.

    Anthropic's prompt caching allows caching portions of prompts to reduce
    costs and latency. This middleware automatically adds cache breakpoints:
    - After system messages
    - Before the most recent user message

    This works only with Anthropic models (Claude). For other models,
    the cache_control attributes are ignored.
    """

    def __init__(
        self,
        *,
        cache_system_prompt: bool = True,
        cache_conversation: bool = True,
        min_cached_tokens: int = 1024,
    ):
        """Initialize Anthropic caching middleware.

        Args:
            cache_system_prompt: Whether to cache system prompts
            cache_conversation: Whether to cache conversation history
            min_cached_tokens: Minimum tokens required for caching (default 1024)
        """
        self.cache_system_prompt = cache_system_prompt
        self.cache_conversation = cache_conversation
        self.min_cached_tokens = min_cached_tokens

    def _add_cache_breakpoints(
        self, messages: Sequence[BaseMessage]
    ) -> list[BaseMessage]:
        """Add cache_control breakpoints to messages.

        Args:
            messages: Input messages

        Returns:
            Messages with cache_control added
        """
        if not messages:
            return list(messages)

        # Convert to list for modification
        result = []

        # Find last system message index
        last_system_idx = -1
        for i, msg in enumerate(messages):
            if isinstance(msg, SystemMessage):
                last_system_idx = i

        # Find last user message index (before final AI response if any)
        last_user_idx = -1
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], HumanMessage):
                last_user_idx = i
                break

        # Add messages with cache breakpoints
        for i, msg in enumerate(messages):
            # Copy message to avoid modifying original
            if hasattr(msg, "model_copy"):
                new_msg = msg.model_copy(deep=True)
            else:
                new_msg = msg.copy(deep=True)

            # Add cache breakpoint after last system message
            if self.cache_system_prompt and i == last_system_idx:
                if not hasattr(new_msg, "additional_kwargs"):
                    new_msg.additional_kwargs = {}
                new_msg.additional_kwargs["cache_control"] = {"type": "ephemeral"}

            # Add cache breakpoint before last user message
            elif self.cache_conversation and i == last_user_idx:
                if not hasattr(new_msg, "additional_kwargs"):
                    new_msg.additional_kwargs = {}
                # Add to previous message (the one before this user message)
                if result:
                    prev_msg = result[-1]
                    if not hasattr(prev_msg, "additional_kwargs"):
                        prev_msg.additional_kwargs = {}
                    prev_msg.additional_kwargs["cache_control"] = {"type": "ephemeral"}

            result.append(new_msg)

        return result

    def _estimate_tokens(self, messages: Sequence[BaseMessage]) -> int:
        """Estimate token count for messages (rough approximation)."""
        total_chars = 0
        for msg in messages:
            if hasattr(msg, "content") and isinstance(msg.content, str):
                total_chars += len(msg.content)
        # Rough estimate: 4 chars per token
        return total_chars // 4

    def wrap_model_call(
        self,
        func: Callable[[Sequence[BaseMessage], RunnableConfig], BaseMessage],
    ) -> Callable[[Sequence[BaseMessage], RunnableConfig], BaseMessage]:
        """Wrap synchronous model call to add cache breakpoints.

        Args:
            func: Original model call function

        Returns:
            Wrapped function that adds cache_control before calling model
        """

        def wrapper(
            messages: Sequence[BaseMessage], config: RunnableConfig
        ) -> BaseMessage:
            # Check if we have enough tokens to benefit from caching
            if self._estimate_tokens(messages) < self.min_cached_tokens:
                return func(messages, config)

            # Add cache breakpoints
            cached_messages = self._add_cache_breakpoints(messages)

            # Call model with cached messages
            return func(cached_messages, config)

        return wrapper

    def awrap_model_call(
        self,
        func: Callable[
            [Sequence[BaseMessage], RunnableConfig],
            AsyncIterator[BaseMessage | str],
        ],
    ) -> Callable[
        [Sequence[BaseMessage], RunnableConfig],
        AsyncIterator[BaseMessage | str],
    ]:
        """Wrap async streaming model call to add cache breakpoints.

        Args:
            func: Original async model call function

        Returns:
            Wrapped async function that adds cache_control before calling model
        """

        async def wrapper(
            messages: Sequence[BaseMessage], config: RunnableConfig
        ) -> AsyncIterator[BaseMessage | str]:
            # Check if we have enough tokens to benefit from caching
            if self._estimate_tokens(messages) < self.min_cached_tokens:
                async for chunk in func(messages, config):
                    yield chunk
                return

            # Add cache breakpoints
            cached_messages = self._add_cache_breakpoints(messages)

            # Call model with cached messages
            async for chunk in func(cached_messages, config):
                yield chunk

        return wrapper

    def __call__(self, state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        """Process state (no-op for this middleware).

        This middleware only wraps model calls, so the state processing is a no-op.
        """
        return {}
