from typing import AsyncIterator, Dict, Any, Optional, List, cast
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import StreamMode
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from psycopg import AsyncConnection
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
import os
import uuid
from src.workflow.graph import create_workflow

class ChatRunner:
    def __init__(self, checkpointer: AsyncPostgresSaver):
        self.checkpointer = checkpointer
        from src.workflow.chat_graph import create_chat_graph, ChatState
        
        workflow = create_workflow()
        self.graph = workflow.compile(checkpointer=checkpointer)
    
    async def run(
        self, 
        messages: List[BaseMessage], 
        thread_id: Optional[str] = None
    ) -> Dict[str, Any]:
        if thread_id is None:
            thread_id = str(uuid.uuid4())
        
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        
        from src.workflow.chat_graph import ChatState
        result = await self.graph.ainvoke(
            cast(ChatState, {"messages": messages}),
            config=config
        )
        
        return {
            "thread_id": thread_id,
            "messages": result.get("messages", []),
            "status": "completed"
        }
    
    async def stream(
        self,
        messages: List[BaseMessage],
        thread_id: Optional[str] = None,
        stream_mode: StreamMode = "messages"
    ) -> AsyncIterator[Dict[str, Any]]:
        if thread_id is None:
            thread_id = str(uuid.uuid4())
        
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        
        from src.workflow.chat_graph import ChatState
        async for chunk in self.graph.astream(
            cast(ChatState, {"messages": messages}),
            config=config,
            stream_mode=stream_mode
        ):
            yield {
                "thread_id": thread_id,
                "chunk": chunk
            }
    
    async def get_history(
        self,
        thread_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        history = []
        
        count = 0
        async for checkpoint in self.graph.aget_state_history(config):
            if count >= limit:
                break
            
            history.append({
                "checkpoint_id": checkpoint.config.get("configurable", {}).get("checkpoint_id"),
                "messages": checkpoint.values.get("messages", []),
                "metadata": checkpoint.metadata
            })
            count += 1
        
        return history
    
    async def retry_message(
        self,
        thread_id: str,
        checkpoint_id: Optional[str] = None
    ) -> Dict[str, Any]:
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        if checkpoint_id:
            config["configurable"]["checkpoint_id"] = checkpoint_id
        
        state = await self.graph.aget_state(config)
        
        messages = state.values.get("messages", [])
        if not messages:
            return {
                "thread_id": thread_id,
                "status": "error",
                "error": "No messages in history to retry"
            }
        
        last_message = messages[-1]
        if isinstance(last_message, AIMessage):
            messages = messages[:-1]
        
        from src.workflow.chat_graph import ChatState
        result = await self.graph.ainvoke(
            cast(ChatState, {"messages": messages}),
            config=config
        )
        
        return {
            "thread_id": thread_id,
            "messages": result.get("messages", []),
            "status": "completed"
        }


async def create_chat_runner() -> ChatRunner:
    db_url = os.getenv("DATABASE_URL", "")
    
    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
        "row_factory": dict_row,
    }
    
    pool: AsyncConnectionPool[AsyncConnection[Any]] = AsyncConnectionPool(
        conninfo=db_url,
        kwargs=connection_kwargs,
        min_size=2,
        max_size=10,
        max_idle=300,
        timeout=30,
        open=False
    )
    
    await pool.open()
    
    checkpointer = AsyncPostgresSaver(pool)
    await checkpointer.setup()
    
    return ChatRunner(checkpointer)
