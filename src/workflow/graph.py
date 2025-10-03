from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import Command, RetryPolicy
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
import os
from langchain.chat_models import init_chat_model
from src.workflow.tools import search_tool, calculator_tool


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def call_llm(state: AgentState) -> dict:
    llm = init_chat_model(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
        model_provider="google-genai",
        api_key=os.getenv("GEMINI_API_KEY"),
        temperature=1.0,
        max_retries=3,
    )
    llm = llm.bind_tools([search_tool, calculator_tool])
    response = llm.invoke(state["messages"])
    
    return {"messages": [response]}


def tool_node(state: AgentState) -> dict:
    
    last_message = state["messages"][-1]
    tool_calls = getattr(last_message, "tool_calls", [])
    
    tool_messages = []
    
    tools_map = {
        "search_tool": search_tool,
        "calculator_tool": calculator_tool,
    }
    
    for tool_call in tool_calls:
        tool_name = tool_call.get("name")
        tool_args = tool_call.get("args", {})
        
        if tool_name in tools_map:
            result = tools_map[tool_name](**tool_args)
            tool_messages.append(
                ToolMessage(
                    content=str(result),
                    tool_call_id=tool_call.get("id"),
                    name=tool_name
                )
            )
    
    return {"messages": tool_messages}


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    last_message = state["messages"][-1]
    
    tool_calls = getattr(last_message, "tool_calls", [])
    if tool_calls:
        return "tools"
    return "end"


def create_workflow():
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", call_llm)
    workflow.add_node("tools", tool_node, retry_policy=RetryPolicy(max_attempts=3))
    
    workflow.add_edge(START, "agent")
    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            "end": END
        }
    )
    workflow.add_edge("tools", "agent")
    
    return workflow
