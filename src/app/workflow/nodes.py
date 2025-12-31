import os
from typing import Literal

from langchain.chat_models import init_chat_model

from src.app.domain.workflow.state import AgentState


def call_llm(state: AgentState) -> dict:
    available_tools = []

    llm = init_chat_model(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
        model_provider="google-genai",
        api_key=os.getenv("GEMINI_API_KEY"),
        temperature=1.0,
        max_retries=3,
    )

    llm_with_tools = llm.bind_tools(available_tools)

    response = llm_with_tools.invoke(state["messages"])

    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", "end"]:
    last_message = state["messages"][-1]

    tool_calls = getattr(last_message, "tool_calls", [])
    if tool_calls:
        return "tools"
    return "end"
