"""Model initialization and configuration for agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

if TYPE_CHECKING:
    from typing import Any


def initialize_model(model: str | BaseChatModel) -> BaseChatModel:
    """Initialize chat model from string or return existing instance.

    Args:
        model: Either a model identifier string or a BaseChatModel instance

    Returns:
        Initialized BaseChatModel instance
    """
    if isinstance(model, str):
        return init_chat_model(model)
    return model


def prepare_system_message(
    system_prompt: str | SystemMessage | None,
) -> SystemMessage | None:
    """Convert system prompt to SystemMessage format.

    Args:
        system_prompt: Either a SystemMessage, string, or None

    Returns:
        SystemMessage instance or None
    """
    if system_prompt is None:
        return None

    if isinstance(system_prompt, SystemMessage):
        return system_prompt

    return SystemMessage(content=system_prompt)


__all__ = [
    "initialize_model",
    "prepare_system_message",
]
