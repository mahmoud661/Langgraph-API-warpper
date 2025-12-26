from __future__ import annotations

import itertools
from typing import (
    TYPE_CHECKING,
    Any,
)

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langgraph._internal._runnable import RunnableCallable
from langgraph.constants import END, START
from langgraph.graph.state import StateGraph
from langgraph.prebuilt.tool_node import ToolNode
from langgraph.typing import ContextT
from langchain.chat_models import init_chat_model

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ResponseT,
    StateT_co,
    _InputAgentState,
    _OutputAgentState,
)
from langchain.agents.structured_output import (
    AutoStrategy,
    OutputToolBinding,
    ProviderStrategy,
    ResponseFormat,
    ToolStrategy,
)

from src.app.workflow.graph_routing import (
    _add_middleware_edge,
    _make_model_to_model_edge,
    _make_model_to_tools_edge,
    _make_tools_to_model_edge,
)
from src.app.workflow.middleware_chain import (
    _chain_async_model_call_handlers,
    _chain_async_tool_call_wrappers,
    _chain_model_call_handlers,
    _chain_tool_call_wrappers,
)
from src.app.workflow.model_handlers import make_amodel_node, make_model_node
from src.app.workflow.schema_utils import _get_can_jump_to, _resolve_schema

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from langgraph.cache.base import BaseCache
    from langgraph.graph.state import CompiledStateGraph
    from langgraph.store.base import BaseStore
    from langgraph.types import Checkpointer


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
    # init chat model
    if isinstance(model, str):
        model = init_chat_model(model)

    # Convert system_prompt to SystemMessage if needed
    system_message: SystemMessage | None = None
    if system_prompt is not None:
        if isinstance(system_prompt, SystemMessage):
            system_message = system_prompt
        else:
            system_message = SystemMessage(content=system_prompt)

    # Handle tools being None or empty
    if tools is None:
        tools = []

    # Convert response format and setup structured output tools
    # Raw schemas are wrapped in AutoStrategy to preserve auto-detection intent.
    # AutoStrategy is converted to ToolStrategy upfront to calculate tools during agent creation,
    # but may be replaced with ProviderStrategy later based on model capabilities.
    initial_response_format: ToolStrategy | ProviderStrategy | AutoStrategy | None
    if response_format is None:
        initial_response_format = None
    elif isinstance(response_format, (ToolStrategy, ProviderStrategy)):
        # Preserve explicitly requested strategies
        initial_response_format = response_format
    elif isinstance(response_format, AutoStrategy):
        # AutoStrategy provided - preserve it for later auto-detection
        initial_response_format = response_format
    else:
        # Raw schema - wrap in AutoStrategy to enable auto-detection
        initial_response_format = AutoStrategy(schema=response_format)

    # For AutoStrategy, convert to ToolStrategy to setup tools upfront
    # (may be replaced with ProviderStrategy later based on model)
    tool_strategy_for_setup: ToolStrategy | None = None
    if isinstance(initial_response_format, AutoStrategy):
        tool_strategy_for_setup = ToolStrategy(schema=initial_response_format.schema)
    elif isinstance(initial_response_format, ToolStrategy):
        tool_strategy_for_setup = initial_response_format

    structured_output_tools: dict[str, OutputToolBinding] = {}
    if tool_strategy_for_setup:
        for response_schema in tool_strategy_for_setup.schema_specs:
            structured_tool_info = OutputToolBinding.from_schema_spec(response_schema)
            structured_output_tools[structured_tool_info.tool.name] = (
                structured_tool_info
            )
    middleware_tools = [t for m in middleware for t in getattr(m, "tools", [])]

    # Collect middleware with wrap_tool_call or awrap_tool_call hooks
    # Include middleware with either implementation to ensure NotImplementedError is raised
    # when middleware doesn't support the execution path
    middleware_w_wrap_tool_call = [
        m
        for m in middleware
        if m.__class__.wrap_tool_call is not AgentMiddleware.wrap_tool_call
        or m.__class__.awrap_tool_call is not AgentMiddleware.awrap_tool_call
    ]

    # Chain all wrap_tool_call handlers into a single composed handler
    wrap_tool_call_wrapper = None
    if middleware_w_wrap_tool_call:
        wrappers = [m.wrap_tool_call for m in middleware_w_wrap_tool_call]
        wrap_tool_call_wrapper = _chain_tool_call_wrappers(wrappers)

    # Collect middleware with awrap_tool_call or wrap_tool_call hooks
    # Include middleware with either implementation to ensure NotImplementedError is raised
    # when middleware doesn't support the execution path
    middleware_w_awrap_tool_call = [
        m
        for m in middleware
        if m.__class__.awrap_tool_call is not AgentMiddleware.awrap_tool_call
        or m.__class__.wrap_tool_call is not AgentMiddleware.wrap_tool_call
    ]

    # Chain all awrap_tool_call handlers into a single composed async handler
    awrap_tool_call_wrapper = None
    if middleware_w_awrap_tool_call:
        async_wrappers = [m.awrap_tool_call for m in middleware_w_awrap_tool_call]
        awrap_tool_call_wrapper = _chain_async_tool_call_wrappers(async_wrappers)

    # Setup tools
    tool_node: ToolNode | None = None
    # Extract built-in provider tools (dict format) and regular tools (BaseTool/callables)
    built_in_tools = [t for t in tools if isinstance(t, dict)]
    regular_tools = [t for t in tools if not isinstance(t, dict)]

    # Tools that require client-side execution (must be in ToolNode)
    available_tools = middleware_tools + regular_tools

    # Only create ToolNode if we have client-side tools
    tool_node = (
        ToolNode(
            tools=available_tools,
            wrap_tool_call=wrap_tool_call_wrapper,
            awrap_tool_call=awrap_tool_call_wrapper,
        )
        if available_tools
        else None
    )

    # Default tools for ModelRequest initialization
    # Use converted BaseTool instances from ToolNode (not raw callables)
    # Include built-ins and converted tools (can be changed dynamically by middleware)
    # Structured tools are NOT included - they're added dynamically based on response_format
    if tool_node:
        default_tools = list(tool_node.tools_by_name.values()) + built_in_tools
    else:
        default_tools = list(built_in_tools)

    # validate middleware
    if len({m.name for m in middleware}) != len(middleware):
        msg = "Please remove duplicate middleware instances."
        raise AssertionError(msg)
    middleware_w_before_agent = [
        m
        for m in middleware
        if m.__class__.before_agent is not AgentMiddleware.before_agent
        or m.__class__.abefore_agent is not AgentMiddleware.abefore_agent
    ]
    middleware_w_before_model = [
        m
        for m in middleware
        if m.__class__.before_model is not AgentMiddleware.before_model
        or m.__class__.abefore_model is not AgentMiddleware.abefore_model
    ]
    middleware_w_after_model = [
        m
        for m in middleware
        if m.__class__.after_model is not AgentMiddleware.after_model
        or m.__class__.aafter_model is not AgentMiddleware.aafter_model
    ]
    middleware_w_after_agent = [
        m
        for m in middleware
        if m.__class__.after_agent is not AgentMiddleware.after_agent
        or m.__class__.aafter_agent is not AgentMiddleware.aafter_agent
    ]
    # Collect middleware with wrap_model_call or awrap_model_call hooks
    # Include middleware with either implementation to ensure NotImplementedError is raised
    # when middleware doesn't support the execution path
    middleware_w_wrap_model_call = [
        m
        for m in middleware
        if m.__class__.wrap_model_call is not AgentMiddleware.wrap_model_call
        or m.__class__.awrap_model_call is not AgentMiddleware.awrap_model_call
    ]
    # Collect middleware with awrap_model_call or wrap_model_call hooks
    # Include middleware with either implementation to ensure NotImplementedError is raised
    # when middleware doesn't support the execution path
    middleware_w_awrap_model_call = [
        m
        for m in middleware
        if m.__class__.awrap_model_call is not AgentMiddleware.awrap_model_call
        or m.__class__.wrap_model_call is not AgentMiddleware.wrap_model_call
    ]

    # Compose wrap_model_call handlers into a single middleware stack (sync)
    wrap_model_call_handler = None
    if middleware_w_wrap_model_call:
        sync_handlers = [m.wrap_model_call for m in middleware_w_wrap_model_call]
        wrap_model_call_handler = _chain_model_call_handlers(sync_handlers)

    # Compose awrap_model_call handlers into a single middleware stack (async)
    awrap_model_call_handler = None
    if middleware_w_awrap_model_call:
        async_handlers = [m.awrap_model_call for m in middleware_w_awrap_model_call]
        awrap_model_call_handler = _chain_async_model_call_handlers(async_handlers)

    state_schemas: set[type] = {m.state_schema for m in middleware}
    # Use provided state_schema if available, otherwise use base AgentState
    base_state = state_schema if state_schema is not None else AgentState
    state_schemas.add(base_state)

    resolved_state_schema = _resolve_schema(state_schemas, "StateSchema", None)
    input_schema = _resolve_schema(state_schemas, "InputSchema", "input")
    output_schema = _resolve_schema(state_schemas, "OutputSchema", "output")

    # create graph, add nodes
    graph: StateGraph[
        AgentState[ResponseT], ContextT, _InputAgentState, _OutputAgentState[ResponseT]
    ] = StateGraph(
        state_schema=resolved_state_schema,
        input_schema=input_schema,
        output_schema=output_schema,
        context_schema=context_schema,
    )

    # Create model node functions
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

    # Only add tools node if we have tools
    if tool_node is not None:
        graph.add_node("tools", tool_node)

    # Add middleware nodes
    for m in middleware:
        if (
            m.__class__.before_agent is not AgentMiddleware.before_agent
            or m.__class__.abefore_agent is not AgentMiddleware.abefore_agent
        ):
            # Use RunnableCallable to support both sync and async
            # Pass None for sync if not overridden to avoid signature conflicts
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

        if (
            m.__class__.before_model is not AgentMiddleware.before_model
            or m.__class__.abefore_model is not AgentMiddleware.abefore_model
        ):
            # Use RunnableCallable to support both sync and async
            # Pass None for sync if not overridden to avoid signature conflicts
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

        if (
            m.__class__.after_model is not AgentMiddleware.after_model
            or m.__class__.aafter_model is not AgentMiddleware.aafter_model
        ):
            # Use RunnableCallable to support both sync and async
            # Pass None for sync if not overridden to avoid signature conflicts
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

        if (
            m.__class__.after_agent is not AgentMiddleware.after_agent
            or m.__class__.aafter_agent is not AgentMiddleware.aafter_agent
        ):
            # Use RunnableCallable to support both sync and async
            # Pass None for sync if not overridden to avoid signature conflicts
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

    # Determine the entry node (runs once at start): before_agent -> before_model -> model
    if middleware_w_before_agent:
        entry_node = f"{middleware_w_before_agent[0].name}.before_agent"
    elif middleware_w_before_model:
        entry_node = f"{middleware_w_before_model[0].name}.before_model"
    else:
        entry_node = "model"

    # Determine the loop entry node (beginning of agent loop, excludes before_agent)
    # This is where tools will loop back to for the next iteration
    if middleware_w_before_model:
        loop_entry_node = f"{middleware_w_before_model[0].name}.before_model"
    else:
        loop_entry_node = "model"

    # Determine the loop exit node (end of each iteration, can run multiple times)
    # This is after_model or model, but NOT after_agent
    if middleware_w_after_model:
        loop_exit_node = f"{middleware_w_after_model[0].name}.after_model"
    else:
        loop_exit_node = "model"

    # Determine the exit node (runs once at end): after_agent or END
    if middleware_w_after_agent:
        exit_node = f"{middleware_w_after_agent[-1].name}.after_agent"
    else:
        exit_node = END

    graph.add_edge(START, entry_node)
    # add conditional edges only if tools exist
    if tool_node is not None:
        # Only include exit_node in destinations if any tool has return_direct=True
        # or if there are structured output tools
        tools_to_model_destinations = [loop_entry_node]
        if (
            any(tool.return_direct for tool in tool_node.tools_by_name.values())
            or structured_output_tools
        ):
            tools_to_model_destinations.append(exit_node)

        graph.add_conditional_edges(
            "tools",
            RunnableCallable(
                _make_tools_to_model_edge(
                    tool_node=tool_node,
                    model_destination=loop_entry_node,
                    structured_output_tools=structured_output_tools,
                    end_destination=exit_node,
                ),
                trace=False,
            ),
            tools_to_model_destinations,
        )

        # base destinations are tools and exit_node
        # we add the loop_entry node to edge destinations if:
        # - there is an after model hook(s) -- allows jump_to to model
        #   potentially artificially injected tool messages, ex HITL
        # - there is a response format -- to allow for jumping to model to handle
        #   regenerating structured output tool calls
        model_to_tools_destinations = ["tools", exit_node]
        if response_format or loop_exit_node != "model":
            model_to_tools_destinations.append(loop_entry_node)

        graph.add_conditional_edges(
            loop_exit_node,
            RunnableCallable(
                _make_model_to_tools_edge(
                    model_destination=loop_entry_node,
                    structured_output_tools=structured_output_tools,
                    end_destination=exit_node,
                ),
                trace=False,
            ),
            model_to_tools_destinations,
        )
    elif len(structured_output_tools) > 0:
        graph.add_conditional_edges(
            loop_exit_node,
            RunnableCallable(
                _make_model_to_model_edge(
                    model_destination=loop_entry_node,
                    end_destination=exit_node,
                ),
                trace=False,
            ),
            [loop_entry_node, exit_node],
        )
    elif loop_exit_node == "model":
        # If no tools and no after_model, go directly to exit_node
        graph.add_edge(loop_exit_node, exit_node)
    # No tools but we have after_model - connect after_model to exit_node
    else:
        _add_middleware_edge(
            graph,
            name=f"{middleware_w_after_model[0].name}.after_model",
            default_destination=exit_node,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(middleware_w_after_model[0], "after_model"),
        )

    # Add before_agent middleware edges
    if middleware_w_before_agent:
        for m1, m2 in itertools.pairwise(middleware_w_before_agent):
            _add_middleware_edge(
                graph,
                name=f"{m1.name}.before_agent",
                default_destination=f"{m2.name}.before_agent",
                model_destination=loop_entry_node,
                end_destination=exit_node,
                can_jump_to=_get_can_jump_to(m1, "before_agent"),
            )
        # Connect last before_agent to loop_entry_node (before_model or model)
        _add_middleware_edge(
            graph,
            name=f"{middleware_w_before_agent[-1].name}.before_agent",
            default_destination=loop_entry_node,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(middleware_w_before_agent[-1], "before_agent"),
        )

    # Add before_model middleware edges
    if middleware_w_before_model:
        for m1, m2 in itertools.pairwise(middleware_w_before_model):
            _add_middleware_edge(
                graph,
                name=f"{m1.name}.before_model",
                default_destination=f"{m2.name}.before_model",
                model_destination=loop_entry_node,
                end_destination=exit_node,
                can_jump_to=_get_can_jump_to(m1, "before_model"),
            )
        # Go directly to model after the last before_model
        _add_middleware_edge(
            graph,
            name=f"{middleware_w_before_model[-1].name}.before_model",
            default_destination="model",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(middleware_w_before_model[-1], "before_model"),
        )

    # Add after_model middleware edges
    if middleware_w_after_model:
        graph.add_edge("model", f"{middleware_w_after_model[-1].name}.after_model")
        for idx in range(len(middleware_w_after_model) - 1, 0, -1):
            m1 = middleware_w_after_model[idx]
            m2 = middleware_w_after_model[idx - 1]
            _add_middleware_edge(
                graph,
                name=f"{m1.name}.after_model",
                default_destination=f"{m2.name}.after_model",
                model_destination=loop_entry_node,
                end_destination=exit_node,
                can_jump_to=_get_can_jump_to(m1, "after_model"),
            )
        # Note: Connection from after_model to after_agent/END is handled above
        # in the conditional edges section

    # Add after_agent middleware edges
    if middleware_w_after_agent:
        # Chain after_agent middleware (runs once at the very end, before END)
        for idx in range(len(middleware_w_after_agent) - 1, 0, -1):
            m1 = middleware_w_after_agent[idx]
            m2 = middleware_w_after_agent[idx - 1]
            _add_middleware_edge(
                graph,
                name=f"{m1.name}.after_agent",
                default_destination=f"{m2.name}.after_agent",
                model_destination=loop_entry_node,
                end_destination=exit_node,
                can_jump_to=_get_can_jump_to(m1, "after_agent"),
            )

        # Connect the last after_agent to END
        _add_middleware_edge(
            graph,
            name=f"{middleware_w_after_agent[0].name}.after_agent",
            default_destination=END,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(middleware_w_after_agent[0], "after_agent"),
        )

    return graph.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config({"recursion_limit": 10_000})


__all__ = [
    "create_agent",
]
