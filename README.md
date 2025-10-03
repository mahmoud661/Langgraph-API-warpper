# LangGraph Workflow and Chat API

## Overview

This project provides a production-ready FastAPI application offering two distinct AI interaction interfaces:

1.  **Chat API**: A ChatGPT-like conversational interface supporting multimodal inputs (text, images, files, audio) for straightforward interactions without tool approvals. It focuses on natural conversation, streaming responses, and thread management.

2.  **Workflow API**: An advanced agentic system featuring human-in-the-loop interactions for tool approvals. It uses custom LangGraph graphs with tool interrupt wrappers to pause execution for human oversight before tool actions are taken.

Both APIs utilize PostgreSQL for checkpoint persistence and support REST, SSE streaming, and WebSocket interfaces, powered by Google's Gemini model (gemini-2.0-flash-exp). The project aims to provide flexible and robust AI interaction capabilities, ranging from simple chat to complex, supervised agentic workflows.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

The application employs a **four-layer architecture**: API, Domain, Workflow, and Infrastructure, ensuring clear separation of concerns.

### UI/UX Decisions

-   **Multimodal Content Structure**: A standardized `{type, data}` array format is used for all chat messages (TextContent, ImageContent, FileContent, AudioContent), ensuring consistency and simplifying front-end integration. This structure is validated and automatically converted to LangChain-compatible formats.
-   **Streaming**: Both Chat and Workflow APIs offer SSE and WebSocket streaming for real-time updates and improved user experience.
-   **Thread Management**: Conversation metadata (thread\_id, user\_id, title, timestamps) is managed via SQLAlchemy for efficient querying and display in UIs (e.g., for listing past conversations).

### Technical Implementations

-   **Service Layer Architecture (SOLID Principles)**: Business logic is completely separated from HTTP concerns using a dedicated `ChatService` in the domain layer. Routes handle only HTTP parsing/formatting while all LangGraph interactions, content conversions, and database operations are delegated to the service layer, following Single Responsibility Principle.
-   **Chat API Graph**: A simple LangGraph structure (`START → call_chat_llm → END`) designed for fast, direct conversational responses without tool execution or interrupts. It uses `ChatState` for messages and `ChatRunner` for execution and streaming.
-   **Workflow API Graph**: A custom, more complex LangGraph implementation that wires an LLM node (`call_llm`) with a tool execution node (`tool_node`). It uses conditional edges for routing and `AgentState` for managing message history and tool context.
-   **Tool Interrupt Wrapper System**: Tools are decorated with `@require_approval` to raise LangGraph interrupts, pausing execution for human approval. The API provides structured payloads for decisions (approve, modify, deny) and automatically checkpoints the state.
-   **State Management & Checkpoints**: PostgreSQL-backed `AsyncPostgresSaver` from LangGraph is used for checkpoint persistence, enabling time-travel debugging and state recovery. Thread metadata is managed via SQLAlchemy models with proper connection pooling (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`).
-   **Message-ID Retry Pattern**: Implements message-based retry using `message_id` to identify target messages. Uses `RemoveMessage` to delete subsequent messages, `aupdate_state(as_node="__start__")` to reposition execution before the LLM node, and `ainvoke(None)` to regenerate responses. Supports both regeneration (no modification) and content modification scenarios.
-   **Durable Execution**: Supports resuming workflows from failures using `invoke(None, config)` pattern, allowing recovery from interruptions without reprocessing previous steps.
-   **Message ID Tracking**: All responses include LangGraph message IDs for precise state tracking and debugging. Messages are returned in their raw format without unnecessary serialization.
-   **Safe Expression Evaluation**: The `calculator_tool` uses AST-based parsing to safely evaluate mathematical expressions, preventing arbitrary code execution.
-   **API Design**: A triple interface strategy provides REST API for synchronous operations, SSE for real-time streaming, and WebSockets for bidirectional communication.
-   **Application Lifecycle**: FastAPI's lifespan context manager handles initialization (e.g., `AsyncConnectionPool`, `AsyncPostgresSaver`, `ChatService`) and graceful shutdown.

### Feature Specifications

-   **Chat API Endpoints**:
    -   `POST /chat/send`: Synchronous chat completion with message IDs.
    -   `POST /chat/stream`: SSE streaming for real-time token delivery.
    -   `POST /chat/retry/{thread_id}`: Message-ID based retry with required `message_id` and optional `content` modification to regenerate responses from any point in the conversation.
    -   `GET /chat/history/{thread_id}`: Retrieve full conversation history with message IDs.
    -   `GET /chat/threads`: List conversation metadata for a user.
    -   `GET /chat/checkpoints/{thread_id}`: Get checkpoint history for debugging and time-travel.
    -   `POST /chat/resume/{thread_id}`: Resume execution from failure (durable execution).
    -   `WS /ws/chat`: WebSocket interface for bidirectional chat.
-   **Workflow API Endpoints**:
    -   `POST /workflow/stream`: SSE streaming for workflow execution with tool interrupts.
    -   `POST /workflow/resume/{thread_id}`: Resume with approval decisions.
    -   `GET /workflow/state/{thread_id}`: Inspect current workflow state.
    -   `GET /workflow/history/{thread_id}`: Get checkpoint history.
    -   `WS /ws/workflow`: WebSocket interface for workflow interaction.
-   **Tool System**: Pluggable tool registry with `@require_approval` for human-in-the-loop control. Current tools include a mock `search_tool` and a secure `calculator_tool`.

## External Dependencies

-   **AI/LLM Services**:
    -   Google Gemini AI (`gemini-2.0-flash-exp`) via `ChatGoogleGenerativeAI` (requires `GEMINI_API_KEY`).
-   **Database**:
    -   PostgreSQL for LangGraph checkpoint persistence and API-specific data (requires `DATABASE_URL`). Managed with `psycopg` (v3) and `AsyncConnectionPool`.
-   **Core Frameworks**:
    -   **FastAPI**: Web framework.
    -   **LangGraph**: Workflow orchestration.
    -   **LangChain**: LLM abstractions.
    -   **Pydantic**: Data validation.
    -   **Uvicorn**: ASGI server.
-   **Infrastructure Libraries**:
    -   **SQLAlchemy**: ORM for API-specific models.
    -   **psycopg[binary]**: PostgreSQL driver.
    -   **psycopg-pool**: PostgreSQL connection pooling.
    -   **python-dotenv**: Environment variable management.