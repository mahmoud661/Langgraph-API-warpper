from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Literal


class RunWorkflowRequest(BaseModel):
    messages: Any
    thread_id: Optional[str] = None


class RunWorkflowResponse(BaseModel):
    thread_id: str
    result: Dict[str, Any]
    status: str


class ResumeWorkflowRequest(BaseModel):
    action: Literal["approve", "deny", "modify"]
    modified_args: Optional[Dict[str, Any]] = None


class ResumeWorkflowResponse(BaseModel):
    thread_id: str
    result: Dict[str, Any]
    status: str


class GetStateResponse(BaseModel):
    values: Dict[str, Any]
    next: List[str]
    tasks: List[Any]
    interrupts: List[Dict[str, Any]]


class GetHistoryResponse(BaseModel):
    history: List[Dict[str, Any]]


class UpdateStateRequest(BaseModel):
    values: Dict[str, Any]
    checkpoint_id: Optional[str] = None
