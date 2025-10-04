"""Main module."""

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from src.api.routes import chat, chat_websocket, unified_websocket  # noqa: E402
from src.app.services.chat_service import ChatService  # noqa: E402
from src.workflow.chat_runner import create_chat_runner  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan.

    Args:
        app: Description of app.
    """
    chat_runner = await create_chat_runner()
    app.state.chat_runner = chat_runner

    chat_service = ChatService(chat_runner)
    app.state.chat_service = chat_service

    yield

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

app.include_router(chat.router)
app.include_router(chat_websocket.router)
app.include_router(unified_websocket.router)


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
            "unified_websocket_chat": "/ws/unified-chat",
            "websocket_stats": "/ws/stats",
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
