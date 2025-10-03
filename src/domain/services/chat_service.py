"""Chat Service module."""
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from src.domain.chat_content import AudioContent, ContentBlock, FileContent, ImageContent, SourceType, TextContent
from src.infra.models.thread import Thread
from src.workflow.chat_runner import ChatRunner


class ChatService:
    """
    Service layer for chat operations that handles all business logic.

    This service:
    - Manages LangGraph interactions (running graphs, getting state, checkpoints)
    - Converts between domain models (ContentBlocks) and LangGraph formats
    - Handles database operations for thread metadata
    - Returns raw LangGraph messages with IDs (doesn't serialize to API schemas)
    """

    def __init__(self, chat_runner: ChatRunner, db_session_maker):
        """
        Initialize the chat service with dependencies.

        Args:
            chat_runner: ChatRunner instance for LangGraph operations
            db_session_maker: SQLAlchemy async session maker for database operations
        """
        self.chat_runner = chat_runner
        self.db_session_maker = db_session_maker

    async def send_message(
        self,
        content: list[ContentBlock],
        thread_id: str | None = None,
        user_id: str = "default"
    ) -> dict[str, Any]:
        """
        Send a message and get the response.

        Args:
            content: List of ContentBlock objects representing the message
            thread_id: Optional thread ID to continue a conversation
            user_id: User ID for thread management

        Returns:
            Dict containing:
                - thread_id: str
                - messages: List[BaseMessage] with IDs
                - last_message: AIMessage
                - status: str
        """
        if thread_id is None:
            thread_id = str(uuid.uuid4())

        content_blocks = self._convert_content_blocks_to_langchain(content)
        human_message = HumanMessage(content=cast(list, content_blocks))

        result = await self.chat_runner.run(
            messages=[human_message],
            thread_id=thread_id
        )

        messages = result.get("messages", [])
        if not messages:
            raise ValueError("No response generated from the assistant")

        last_message = messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError("Expected AI response but got different message type")

        return {
            "thread_id": thread_id,
            "messages": messages,
            "last_message": last_message,
            "status": "completed"
        }

    async def stream_message(
        self,
        content: list[ContentBlock],
        thread_id: str | None = None,
        user_id: str = "default"
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream message responses as they are generated.

        Args:
            content: List of ContentBlock objects representing the message
            thread_id: Optional thread ID to continue a conversation
            user_id: User ID for thread management

        Yields:
            Dict containing streaming events with types:
                - 'metadata': Initial metadata with thread_id
                - 'token': Content tokens as they arrive
                - 'done': Completion signal
                - 'error': Error information
        """
        accumulated_content = ""

        if thread_id is None:
            thread_id = str(uuid.uuid4())

        yield {
            "type": "metadata",
            "thread_id": thread_id
        }

        try:
            content_blocks = self._convert_content_blocks_to_langchain(content)
            human_message = HumanMessage(content=cast(list, content_blocks))

            async for event in self.chat_runner.stream(
                messages=[human_message],
                thread_id=thread_id,
                stream_mode="messages"
            ):
                chunk = event.get("chunk")

                if chunk and isinstance(chunk, tuple) and len(chunk) >= 2:
                    message_chunk = chunk[0]

                    if isinstance(message_chunk, AIMessageChunk):
                        if isinstance(message_chunk.content, str):
                            if message_chunk.content:
                                accumulated_content += message_chunk.content
                                yield {
                                    "type": "token",
                                    "content": message_chunk.content
                                }
                        elif isinstance(message_chunk.content, list):
                            for item in message_chunk.content:
                                if isinstance(item, str) and item:
                                    accumulated_content += item
                                    yield {
                                        "type": "token",
                                        "content": item
                                    }
                                elif isinstance(item, dict) and item.get("type") == "text":
                                    text = item.get("text", "")
                                    if text:
                                        accumulated_content += text
                                        yield {
                                            "type": "token",
                                            "content": text
                                        }

        except Exception as e:
            yield {
                "type": "error",
                "error": str(e)
            }

    async def retry_message(
        self,
        thread_id: str,
        message_id: str,
        modified_content: list[ContentBlock] | None = None
    ) -> dict[str, Any]:
        """
        Retry/regenerate a message using message ID-based replacement.

        Pattern 1 (without modification): Remove messages after target, invoke to regenerate
        Pattern 2 (with modification): Update message with same ID, then invoke

        Args:
            thread_id: Thread ID
            message_id: ID of message to retry from
            modified_content: Optional new content for the message

        Returns:
            Dict with thread_id, messages, last_message, status
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        state = await self.chat_runner.graph.aget_state(config)
        messages = list(state.values.get("messages", []))

        if not messages:
            raise ValueError(f"No messages found for thread: {thread_id}")

        message_index = None
        for i, msg in enumerate(messages):
            if msg.id == message_id:
                message_index = i
                break

        if message_index is None:
            raise ValueError(f"Message with ID {message_id} not found")

        target_message = messages[message_index]

        messages_to_update = []

        if modified_content:
            content_blocks = self._convert_content_blocks_to_langchain(modified_content)

            if isinstance(target_message, HumanMessage):
                updated_message = HumanMessage(
                    content=cast(list, content_blocks),
                    id=message_id
                )
            elif isinstance(target_message, AIMessage):
                text_content = ""
                for block in content_blocks:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_content = block.get("text", "")
                        break
                updated_message = AIMessage(
                    content=text_content,
                    id=message_id
                )
            else:
                raise ValueError(f"Unsupported message type: {type(target_message)}")

            messages_to_update.append(updated_message)

        messages_to_delete = [
            RemoveMessage(id=msg.id)
            for msg in messages[message_index + 1:]
        ]
        messages_to_update.extend(messages_to_delete)

        new_config = await self.chat_runner.graph.aupdate_state(
            config,
            values={"messages": messages_to_update},
            as_node="__start__"
        )

        result = await self.chat_runner.graph.ainvoke(None, new_config)

        result_messages = result.get("messages", [])
        if not result_messages:
            raise ValueError("No response generated")

        last_message = result_messages[-1]
        if not isinstance(last_message, AIMessage):
            raise ValueError("Expected AI response")

        return {
            "thread_id": thread_id,
            "messages": result_messages,
            "last_message": last_message,
            "status": "completed"
        }

    async def get_history(self, thread_id: str) -> dict[str, Any]:
        """
        Get message history for a thread with message IDs from state.

        Args:
            thread_id: Thread ID to get history for

        Returns:
            Dict containing:
                - thread_id: str
                - messages: List[BaseMessage] with IDs and metadata
                - state: Full state object
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        state = await self.chat_runner.graph.aget_state(config)

        messages = state.values.get("messages", [])

        if not messages:
            raise ValueError(f"No history found for thread: {thread_id}")

        return {
            "thread_id": thread_id,
            "messages": messages,
            "state": state
        }

    async def get_threads(self, user_id: str = "default") -> list[dict[str, Any]]:
        """
        Get list of threads for a user from database.

        Args:
            user_id: User ID to filter threads

        Returns:
            List of thread dictionaries containing:
                - thread_id: str
                - title: str
                - created_at: datetime
                - updated_at: datetime
                - last_message: str
        """
        async with self.db_session_maker() as session:
            stmt = select(Thread).where(
                Thread.user_id == user_id
            ).order_by(Thread.updated_at.desc())

            result = await session.execute(stmt)
            threads = result.scalars().all()

            return [
                {
                    "thread_id": thread.thread_id,
                    "title": thread.title,
                    "created_at": thread.created_at,
                    "updated_at": thread.updated_at,
                    "last_message": thread.last_message or ""
                }
                for thread in threads
            ]

    async def get_checkpoints(
        self,
        thread_id: str,
        limit: int = 10
    ) -> list[dict[str, Any]]:
        """
        Get checkpoint history for time-travel debugging and recovery.

        Args:
            thread_id: Thread ID to get checkpoints for
            limit: Maximum number of checkpoints to retrieve

        Returns:
            List of checkpoint dictionaries containing:
                - checkpoint_id: Optional[str]
                - messages: List[BaseMessage]
                - metadata: Dict
                - config: Dict
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        checkpoints = []

        count = 0
        async for checkpoint in self.chat_runner.graph.aget_state_history(config):
            if count >= limit:
                break

            checkpoint_data = {
                "checkpoint_id": checkpoint.config.get("configurable", {}).get("checkpoint_id"),
                "messages": checkpoint.values.get("messages", []),
                "metadata": checkpoint.metadata,
                "config": checkpoint.config,
                "next": checkpoint.next,
                "tasks": checkpoint.tasks
            }
            checkpoints.append(checkpoint_data)
            count += 1

        return checkpoints

    async def resume_from_failure(self, thread_id: str) -> dict[str, Any]:
        """
        Resume execution from a failed state using LangGraph durable execution pattern.

        This uses the proper durable execution approach by calling invoke(None, config)
        which automatically resumes from the last checkpoint with the same thread_id.

        Args:
            thread_id: Thread ID to resume

        Returns:
            Dict containing:
                - thread_id: str
                - messages: List[BaseMessage]
                - last_message: AIMessage
                - status: str
                - resumed_from_checkpoint: bool
        """
        config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
        state = await self.chat_runner.graph.aget_state(config)

        messages = state.values.get("messages", [])

        if not messages:
            raise ValueError(f"No state found for thread: {thread_id}")

        if messages and isinstance(messages[-1], AIMessage):
            return {
                "thread_id": thread_id,
                "messages": messages,
                "last_message": messages[-1],
                "status": "already_completed",
                "resumed_from_checkpoint": False
            }

        result = await self.chat_runner.graph.ainvoke(None, config)

        result_messages = result.get("messages", [])
        if not result_messages:
            raise ValueError("No response generated during resume")

        last_message = result_messages[-1]

        return {
            "thread_id": thread_id,
            "messages": result_messages,
            "last_message": last_message,
            "status": "resumed_and_completed",
            "resumed_from_checkpoint": True
        }

    def _convert_content_blocks_to_langchain(
        self,
        content_blocks: list[ContentBlock]
    ) -> list[dict[str, Any]]:
        """
        Convert ContentBlock domain models to LangChain format.

        Args:
            content_blocks: List of ContentBlock objects

        Returns:
            List of dictionaries in LangChain format
        """
        return [block.to_langchain_format() for block in content_blocks]

    def _convert_langchain_to_content_blocks(
        self,
        langchain_content: Any
    ) -> list[ContentBlock]:
        """
        Convert LangChain message content to ContentBlock domain models.

        Args:
            langchain_content: LangChain message content (str, list, or dict)

        Returns:
            List of ContentBlock objects
        """
        content_blocks: list[ContentBlock] = []

        if isinstance(langchain_content, str):
            content_blocks = [TextContent(data=langchain_content)]
        elif isinstance(langchain_content, list):
            for item in langchain_content:
                if isinstance(item, str):
                    content_blocks.append(TextContent(data=item))
                elif isinstance(item, dict):
                    if item.get("type") == "text":
                        content_blocks.append(TextContent(data=item.get("text", "")))
                    elif item.get("type") == "image_url":
                        image_url = item.get("image_url", {}).get("url", "")
                        if image_url.startswith("data:"):
                            parts = image_url.split(",", 1)
                            if len(parts) == 2:
                                mime_type = parts[0].split(";")[0].replace("data:", "")
                                data = parts[1]
                                content_blocks.append(ImageContent(
                                    data=data,
                                    mime_type=mime_type,
                                    source_type=SourceType.BASE64
                                ))
                        else:
                            content_blocks.append(ImageContent(
                                data=image_url,
                                mime_type="image/jpeg",
                                source_type=SourceType.URL
                            ))
                    else:
                        content_blocks.append(TextContent(data=str(item)))
                else:
                    content_blocks.append(TextContent(data=str(item)))
        else:
            content_blocks = [TextContent(data=str(langchain_content))]

        return content_blocks

    def _extract_display_text_from_content_blocks(
        self,
        content_blocks: list[ContentBlock]
    ) -> str:
        """
        Extract display text from ContentBlocks for storage and display.

        Handles all content types:
        - TextContent: use actual text data
        - ImageContent: use "[Image]"
        - FileContent: use "[File: filename]" or "[File]"
        - AudioContent: use "[Audio]"

        Args:
            content_blocks: List of ContentBlock objects

        Returns:
            Concatenated display text
        """
        parts = []
        for block in content_blocks:
            if isinstance(block, TextContent):
                parts.append(block.data)
            elif isinstance(block, ImageContent):
                parts.append("[Image]")
            elif isinstance(block, FileContent):
                if block.filename:
                    parts.append(f"[File: {block.filename}]")
                else:
                    parts.append("[File]")
            elif isinstance(block, AudioContent):
                parts.append("[Audio]")
        return " ".join(parts).strip()
