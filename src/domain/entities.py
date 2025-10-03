from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime


class InterruptPayload(BaseModel):
    tool_name: str
    tool_args: Dict[str, Any]
    reasoning: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ResumeAction(BaseModel):
    action: Literal["approve", "deny", "modify"]
    modified_args: Optional[Dict[str, Any]] = None


class WorkflowState(BaseModel):
    messages: List[Dict[str, Any]] = []
    tool_calls: List[Dict[str, Any]] = []
    current_step: str = "start"
    metadata: Dict[str, Any] = {}


class CheckpointInfo(BaseModel):
    checkpoint_id: str
    thread_id: str
    timestamp: datetime
    state_values: Dict[str, Any]
    next_nodes: List[str]


class WorkflowRun(BaseModel):
    run_id: str
    thread_id: str
    status: Literal["running", "interrupted", "completed", "failed"]
    created_at: datetime
    updated_at: datetime
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
