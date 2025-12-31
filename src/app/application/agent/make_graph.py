"""Graph factory for LangGraph compilation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.application.agent.create_deep_agent import create_deep_agent

if TYPE_CHECKING:
    from typing import Any
    from langgraph.graph.state import CompiledStateGraph


def make_graph(config: dict[str, Any]) -> CompiledStateGraph:
    """Make a compiled state graph from configuration.

    Args:
        config: Configuration dictionary for graph creation

    Returns:
        Compiled state graph
    """
    return create_deep_agent()


__all__ = [
    "make_graph",
]
