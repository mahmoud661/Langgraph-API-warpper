"""Edge routing from tools node back to model node."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, cast

from langchain_core.messages import AIMessage, ToolMessage

if TYPE_CHECKING:
    from langchain_core.messages import AnyMessage
    from langgraph.prebuilt.tool_node import ToolNode

    from langchain.agents.structured_output import OutputToolBinding


def _fetch_last_ai_and_tool_messages(
    messages: list[AnyMessage],
) -> tuple[AIMessage, list[ToolMessage]]:
    """Extract the last AI message and subsequent tool messages from the message list."""
    last_ai_index: int
    last_ai_message: AIMessage

    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], AIMessage):
            last_ai_index = i
            last_ai_message = cast("AIMessage", messages[i])
            break

    tool_messages = [
        m for m in messages[last_ai_index + 1 :] if isinstance(m, ToolMessage)
    ]
    return last_ai_message, tool_messages


def make_tools_to_model_edge(
    *,
    tool_node: ToolNode,
    model_destination: str,
    structured_output_tools: dict[str, OutputToolBinding],
    end_destination: str,
) -> Callable[[dict[str, Any]], str | None]:
    """Create an edge function that routes from tools to model node."""

    def tools_to_model(state: dict[str, Any]) -> str | None:
        last_ai_message, tool_messages = _fetch_last_ai_and_tool_messages(
            state["messages"]
        )

        # 1. Exit condition: All executed tools have return_direct=True
        # Filter to only client-side tools (provider tools are not in tool_node)
        client_side_tool_calls = [
            c
            for c in last_ai_message.tool_calls
            if c["name"] in tool_node.tools_by_name
        ]
        if client_side_tool_calls and all(
            tool_node.tools_by_name[c["name"]].return_direct
            for c in client_side_tool_calls
        ):
            return end_destination

        # 2. Exit condition: A structured output tool was executed
        if any(t.name in structured_output_tools for t in tool_messages):
            return end_destination

        # 3. Default: Continue the loop
        #    Tool execution completed successfully, route back to the model
        #    so it can process the tool results and decide the next action.
        return model_destination

    return tools_to_model
