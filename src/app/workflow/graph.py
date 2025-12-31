"""Thin facade for graph creation - delegates to application layer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.application.agent.create_deep_agent import create_deep_agent
from src.app.application.agent.make_graph import make_graph

if TYPE_CHECKING:
    pass


__all__ = [
    "create_deep_agent",
    "make_graph",
]
