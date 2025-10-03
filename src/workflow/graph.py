"""Graph module for creating LangGraph workflow with built-in tool handling."""

import os
from typing import Annotated, Literal, TypedDict

from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import RetryPolicy

from src.workflow.tools import calculator_tool, search_tool


class AgentState(TypedDict):
    """State definition for the agent workflow.

    Contains the conversation messages that flow through the graph nodes.
    """
    messages: Annotated[list[BaseMessage], add_messages]


def call_llm(state: AgentState) -> dict:
    """Call LLM with bound tools.

    Args:
        state: The current agent state containing messages.

    Returns:
        Dictionary containing the LLM response message.
    """
    # Define available tools
    available_tools = [calculator_tool, search_tool]

    # Initialize and configure the LLM
    llm = init_chat_model(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
        model_provider="google-genai",
        api_key=os.getenv("GEMINI_API_KEY"),
        temperature=1.0,
        max_retries=3,
    )

    # Bind tools to the LLM
    llm_with_tools = llm.bind_tools(available_tools)

    # Invoke the LLM with the current messages
    response = llm_with_tools.invoke(state["messages"])

    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    """Determine if the workflow should continue to tools or end.

    Args:
        state: The current agent state containing messages.

    Returns:
        "tools" if the last message contains tool calls, "end" otherwise.
    """

    last_message = state["messages"][-1]

    # Check if the LLM wants to use any tools
    tool_calls = getattr(last_message, "tool_calls", [])
    if tool_calls:
        return "tools"
    return "end"


def create_workflow():
    """Create workflow with built-in ToolNode.

    Returns:
        StateGraph: Compiled workflow graph ready for execution.
    """
    # Define available tools for the ToolNode
    available_tools = [calculator_tool, search_tool]

    # Create the workflow graph
    workflow = StateGraph(AgentState)

    # Add nodes
    workflow.add_node("agent", call_llm)
    workflow.add_node(
        "tools",
        ToolNode(available_tools),
        retry_policy=RetryPolicy(max_attempts=3)
    )

    # Define the flow
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", "end": END}
    )
    workflow.add_edge("tools", "agent")

    return workflow
