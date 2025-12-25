from collections.abc import Awaitable, Callable, Sequence
from typing import Any, NotRequired
from typing_extensions import TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
)
from langchain.tools import BaseTool, ToolRuntime
from langchain_core.tools import StructuredTool
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.types import Command


class SubAgent(TypedDict):
    name: str
    description: str
    system_prompt: str
    tools: Sequence[BaseTool | Callable | dict[str, Any]]
    model: NotRequired[str | BaseChatModel]
    middleware: NotRequired[list[AgentMiddleware]]
    interrupt_on: NotRequired[dict[str, bool | InterruptOnConfig]]


class CompiledSubAgent(TypedDict):
    name: str
    description: str
    runnable: Runnable


DEFAULT_SUBAGENT_PROMPT = "In order to complete the objective that the user asks of you, you have access to a number of standard tools."

_EXCLUDED_STATE_KEYS = {"messages", "todos", "structured_response"}

TASK_TOOL_DESCRIPTION = """Launch an ephemeral subagent to handle complex, multi-step independent tasks with isolated context windows.

Available agent types:
{available_agents}

When using the Task tool, specify a subagent_type parameter to select which agent type to use.

## Usage notes:
1. Launch multiple agents concurrently whenever possible
2. Each agent returns a single message back to you
3. Each agent invocation is stateless
4. Clearly tell the agent whether to create content, perform analysis, or research
5. Use for context isolation and complex multi-step tasks"""


class SubAgentMiddleware(AgentMiddleware):
    def __init__(
        self,
        default_model: str | BaseChatModel,
        default_tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
        subagents: list[SubAgent | CompiledSubAgent] | None = None,
        default_middleware: list[AgentMiddleware] | None = None,
        default_interrupt_on: dict[str, bool | InterruptOnConfig] | None = None,
        general_purpose_agent: bool = True,
    ) -> None:
        self.default_model = default_model
        self.default_tools = default_tools or []
        self.subagents = subagents or []
        self.default_middleware = default_middleware or []
        self.default_interrupt_on = default_interrupt_on
        self.general_purpose_agent = general_purpose_agent

        self._compiled_subagents = {}
        for subagent in self.subagents:
            if "runnable" in subagent:
                self._compiled_subagents[subagent["name"]] = subagent["runnable"]
            else:
                self._compiled_subagents[subagent["name"]] = self._compile_subagent(
                    subagent
                )

        self.tools = [self._create_task_tool()]

    def _compile_subagent(self, subagent: SubAgent) -> Runnable:
        model = subagent.get("model", self.default_model)
        tools = subagent.get("tools", self.default_tools)
        middleware = list(self.default_middleware)
        if "middleware" in subagent:
            middleware.extend(subagent["middleware"])
        interrupt_on = subagent.get("interrupt_on", self.default_interrupt_on)

        if interrupt_on:
            middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

        return create_agent(
            model=model,
            tools=tools,
            middleware=middleware,
            system_prompt=subagent["system_prompt"],
        )

    def _create_task_tool(self) -> BaseTool:
        agent_descriptions = []
        if self.general_purpose_agent:
            agent_descriptions.append(
                '"general-purpose": use this agent for general purpose tasks'
            )
        for subagent in self.subagents:
            agent_descriptions.append(
                f'"{subagent["name"]}": {subagent["description"]}'
            )

        available_agents = "\n".join(agent_descriptions)
        tool_description = TASK_TOOL_DESCRIPTION.format(
            available_agents=available_agents
        )

        def sync_task(
            runtime: ToolRuntime,
            prompt: str,
            subagent_type: str = "general-purpose",
        ) -> str:
            if subagent_type == "general-purpose" and self.general_purpose_agent:
                agent = create_agent(
                    model=self.default_model,
                    tools=self.default_tools,
                    middleware=self.default_middleware,
                    system_prompt=DEFAULT_SUBAGENT_PROMPT,
                )
            elif subagent_type in self._compiled_subagents:
                agent = self._compiled_subagents[subagent_type]
            else:
                return f"Error: Unknown subagent type: {subagent_type}"

            state = dict(runtime.state)
            for key in _EXCLUDED_STATE_KEYS:
                state.pop(key, None)
            state["messages"] = [HumanMessage(content=prompt)]

            result = agent.invoke(state)
            final_message = result["messages"][-1]
            return (
                final_message.content
                if hasattr(final_message, "content")
                else str(final_message)
            )

        async def async_task(
            runtime: ToolRuntime,
            prompt: str,
            subagent_type: str = "general-purpose",
        ) -> str:
            if subagent_type == "general-purpose" and self.general_purpose_agent:
                agent = create_agent(
                    model=self.default_model,
                    tools=self.default_tools,
                    middleware=self.default_middleware,
                    system_prompt=DEFAULT_SUBAGENT_PROMPT,
                )
            elif subagent_type in self._compiled_subagents:
                agent = self._compiled_subagents[subagent_type]
            else:
                return f"Error: Unknown subagent type: {subagent_type}"

            state = dict(runtime.state)
            for key in _EXCLUDED_STATE_KEYS:
                state.pop(key, None)
            state["messages"] = [HumanMessage(content=prompt)]

            result = await agent.ainvoke(state)
            final_message = result["messages"][-1]
            return (
                final_message.content
                if hasattr(final_message, "content")
                else str(final_message)
            )

        return StructuredTool.from_function(
            name="task",
            description=tool_description,
            func=sync_task,
            coroutine=async_task,
        )

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(request)
