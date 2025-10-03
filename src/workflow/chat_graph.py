from typing import Annotated, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage
from langchain.chat_models import init_chat_model
import os


class ChatState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


llm = init_chat_model(
    model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp"),
    model_provider="google-genai",
    api_key=os.getenv("GEMINI_API_KEY"),
    temperature=1.0,
    max_retries=3,
)


async def call_chat_llm(state: ChatState) -> dict:
    response = await llm.ainvoke(state["messages"])
    return {"messages": [response]}


def create_chat_graph():
    workflow = StateGraph(ChatState)
    
    workflow.add_node("call_chat_llm", call_chat_llm)
    
    workflow.add_edge(START, "call_chat_llm")
    workflow.add_edge("call_chat_llm", END)
    
    return workflow
