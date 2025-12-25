"""Main module."""

from dotenv import load_dotenv

load_dotenv()

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

from src.api.di import create_base_injector  # noqa: E402
from src.api.routes import chat, chat_websocket  # noqa: E402
from src.app.services.chat_service import ChatService  # noqa: E402
from src.app.workflow.chat_runner import ChatRunner, create_chat_runner  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown.

    Args:
        app: FastAPI application instance
    """
    # Initialize ChatRunner instance
    chat_runner = await create_chat_runner()

    # Create base injector and bind ChatRunner instance
    from injector import Binder, Module

    class RuntimeModule(Module):
        def configure(self, binder: Binder) -> None:
            binder.bind(ChatRunner, to=chat_runner)

    base_injector = create_base_injector()
    app.state.base_injector = base_injector.create_child_injector(RuntimeModule())

    yield

    # Cleanup
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
            "chat_websocket_chat": "/ws/chat-stream",
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
