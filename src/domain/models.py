"""Entities module."""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class InterruptPayload(BaseModel):
    """InterruptPayload class."""
    tool_name: str
    tool_args: dict[str, Any]
    reasoning: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ResumeAction(BaseModel):
    """ResumeAction class."""
    action: Literal["approve", "deny", "modify"]
    modified_args: dict[str, Any] | None = None


class WorkflowState(BaseModel):
    """WorkflowState class."""
    messages: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    current_step: str = "start"
    metadata: dict[str, Any] = {}


class CheckpointInfo(BaseModel):
    """CheckpointInfo class."""
    checkpoint_id: str
    thread_id: str
    timestamp: datetime
    state_values: dict[str, Any]
    next_nodes: list[str]


class WorkflowRun(BaseModel):
    """WorkflowRun class."""
    run_id: str
    thread_id: str
    status: Literal["running", "interrupted", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    result: dict[str, Any] | None = None
    error: str | None = None
