"""Middleware composition utilities."""

from __future__ import annotations

from src.app.application.middleware.model_call_chain import (
    chain_async_model_call_handlers,
    chain_model_call_handlers,
    normalize_to_model_response,
)
from src.app.application.middleware.tool_call_chain import (
    chain_async_tool_call_wrappers,
    chain_tool_call_wrappers,
)

__all__ = [
    "chain_model_call_handlers",
    "chain_async_model_call_handlers",
    "chain_tool_call_wrappers",
    "chain_async_tool_call_wrappers",
    "normalize_to_model_response",
]
