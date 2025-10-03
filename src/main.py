"""Main module."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import chat, chat_websocket, websocket
from src.domain.services.chat_service import ChatService
from src.infra.database.connection import AsyncSessionLocal, engine
from src.infra.models.thread import Base as ThreadBase
from src.workflow.chat_runner import create_chat_runner
from src.workflow.runner import create_workflow_runner

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan.

    Args:
        app: Description of app.
    """
    async with engine.begin() as conn:
        await conn.run_sync(ThreadBase.metadata.create_all)

    app.state.db_session_maker = AsyncSessionLocal

    workflow_runner = await create_workflow_runner()
    app.state.workflow_runner = workflow_runner

    chat_runner = await create_chat_runner()
    app.state.chat_runner = chat_runner

    chat_service = ChatService(chat_runner, AsyncSessionLocal)
    app.state.chat_service = chat_service

    yield

    if hasattr(workflow_runner.checkpointer, "close"):
        await workflow_runner.checkpointer.close()  # type: ignore
    elif hasattr(workflow_runner.checkpointer, "pool"):
        await workflow_runner.checkpointer.pool.close()  # type: ignore

    if hasattr(chat_runner.checkpointer, "close"):
        await chat_runner.checkpointer.close()  # type: ignore
    elif hasattr(chat_runner.checkpointer, "pool"):
        await chat_runner.checkpointer.pool.close()  # type: ignore


app = FastAPI(
    title="LangGraph Workflow API",
    description="Reusable FastAPI skeleton for LangGraph workflows with interrupts, retries, checkpoints, and streaming",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(websocket.router)
app.include_router(chat.router)
app.include_router(chat_websocket.router)


@app.get("/")
async def root():
    """Root.

    Returns:
        Description of return value.
    """
    return {
        "message": "LangGraph Workflow API",
        "version": "1.0.0",
        "endpoints": {
            "resume_workflow": "/workflow/resume/{thread_id}",
            "stream_workflow": "/workflow/stream",
            "websocket_workflow": "/ws/workflow",
            "websocket_chat": "/ws/chat",
            "get_state": "/workflow/state/{thread_id}",
            "get_history": "/workflow/history/{thread_id}",
            "update_state": "/workflow/state/{thread_id}/update",
        },
    }


@app.get("/health")
async def health():
    """Health.

    Returns:
        Description of return value.
    """
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
