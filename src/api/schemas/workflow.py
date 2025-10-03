from typing import Any, Literal

from pydantic import BaseModel


class RunWorkflowRequest(BaseModel):
    messages: Any
    thread_id: str | None = None


class RunWorkflowResponse(BaseModel):
    thread_id: str
    result: dict[str, Any]
    status: str


class ResumeWorkflowRequest(BaseModel):
    action: Literal["approve", "deny", "modify"]
    modified_args: dict[str, Any] | None = None


class ResumeWorkflowResponse(BaseModel):
    thread_id: str
    result: dict[str, Any]
    status: str


class GetStateResponse(BaseModel):
    values: dict[str, Any]
    next: list[str]
    tasks: list[Any]
    interrupts: list[dict[str, Any]]


class GetHistoryResponse(BaseModel):
    history: list[dict[str, Any]]


class UpdateStateRequest(BaseModel):
    values: dict[str, Any]
    checkpoint_id: str | None = None
