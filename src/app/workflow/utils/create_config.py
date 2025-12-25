"""Utility to build RunnableConfig objects for LangGraph runs."""

from langchain_core.runnables import RunnableConfig


def create_config(thread_id: str, checkpoint_id: str | None = None) -> RunnableConfig:
    """Create runnable config with thread_id and optional checkpoint_id.

    Args:
        thread_id: Identifier for the conversation thread.
        checkpoint_id: Optional checkpoint identifier to resume from.

    Returns:
        RunnableConfig: The configuration dictionary for LangGraph runnables.
    """
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    if checkpoint_id:
        config["configurable"]["checkpoint_id"] = checkpoint_id
    return config
