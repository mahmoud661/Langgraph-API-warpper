from typing import Annotated, Any, NotRequired
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    files: NotRequired[dict[str, Any]]
    todos: NotRequired[list[dict[str, Any]]]
