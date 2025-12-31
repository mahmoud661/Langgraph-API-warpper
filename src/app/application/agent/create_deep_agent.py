"""Deep agent creation with middleware composition."""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.app.workflow.react_agent import create_agent
from src.app.llm_provider import create_llm
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    InterruptOnConfig,
    TodoListMiddleware,
)
from langchain.agents.middleware.summarization import SummarizationMiddleware
from src.app.infrastructure.storage.protocol import BackendFactory
from src.app.application.middleware.filesystem_middleware import FilesystemMiddleware
from src.app.workflow.middleware.patch_tool_calls import PatchToolCallsMiddleware
from src.app.application.middleware.subagent_middleware import (
    CompiledSubAgent,
    SubAgent,
    SubAgentMiddleware,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import Any

    from langchain.agents.middleware.types import AgentMiddleware
    from langchain.agents.structured_output import ResponseFormat
    from langchain_core.language_models import BaseChatModel
    from langchain_core.tools import BaseTool
    from langgraph.cache.base import BaseCache
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer

    from src.app.domain.storage.protocol import BackendProtocol

BASE_AGENT_PROMPT = "In order to complete the objective that the user asks of you, you have access to a number of standard tools."


def get_default_model() -> BaseChatModel:
    """Get the default model for agent creation."""
    return create_llm()


def create_deep_agent(
    model: str | BaseChatModel | None = None,
    tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
    *,
    system_prompt: str | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    subagents: list[SubAgent | CompiledSubAgent] | None = None,
    response_format: ResponseFormat | None = None,
    context_schema: type[Any] | None = None,
    checkpointer: Checkpointer | None = None,
    store: BaseStore | None = None,
    backend: BackendProtocol | BackendFactory | None = None,
    interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
    debug: bool = False,
    name: str | None = None,
    cache: BaseCache | None = None,
) -> CompiledStateGraph:
    """Create deep agent with full middleware stack.

    Args:
        model: Chat model identifier or instance
        tools: Optional sequence of tools
        system_prompt: Optional system prompt
        middleware: Sequence of middleware instances
        subagents: Optional list of subagents
        response_format: Optional response format specification
        context_schema: Optional context schema
        checkpointer: Optional checkpointer
        store: Optional store
        backend: Optional backend for filesystem
        interrupt_on: Optional interrupt configuration
        debug: Enable debug mode
        name: Optional agent name
        cache: Optional cache

    Returns:
        Compiled state graph with full middleware stack
    """
    if model is None:
        model = get_default_model()

    if (
        model.profile is not None
        and isinstance(model.profile, dict)
        and "max_input_tokens" in model.profile
        and isinstance(model.profile["max_input_tokens"], int)
    ):
        trigger = ("fraction", 0.85)
        keep = ("fraction", 0.10)
    else:
        trigger = ("tokens", 170000)
        keep = ("messages", 6)

    deepagent_middleware = [
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        SubAgentMiddleware(
            default_model=model,
            default_tools=tools,
            subagents=subagents if subagents is not None else [],
            default_middleware=[
                TodoListMiddleware(),
                FilesystemMiddleware(backend=backend),
                SummarizationMiddleware(
                    model=model,
                    trigger=trigger,
                    keep=keep,
                    trim_tokens_to_summarize=None,
                ),
                PatchToolCallsMiddleware(),
            ],
            default_interrupt_on=interrupt_on,
            general_purpose_agent=True,
        ),
        SummarizationMiddleware(
            model=model,
            trigger=trigger,
            keep=keep,
            trim_tokens_to_summarize=None,
        ),
        PatchToolCallsMiddleware(),
    ]
    if middleware:
        deepagent_middleware.extend(middleware)
    if interrupt_on is not None:
        deepagent_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

    return create_agent(
        model,
        system_prompt=(
            system_prompt + "\n\n" + BASE_AGENT_PROMPT
            if system_prompt
            else BASE_AGENT_PROMPT
        ),
        tools=tools,
        middleware=deepagent_middleware,
        response_format=response_format,
        context_schema=context_schema,
        checkpointer=checkpointer,
        store=store,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config({"recursion_limit": 1000})


__all__ = [
    "create_deep_agent",
    "get_default_model",
]
