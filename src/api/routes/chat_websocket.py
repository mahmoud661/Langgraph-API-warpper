"""Chat Websocket module."""

import json
import uuid
from datetime import datetime
from typing import List, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from sqlalchemy import select

from src.domain.chat_content import AudioContent, ContentBlock, FileContent, ImageContent, TextContent
from src.infra.models.thread import Thread

router = APIRouter(prefix="/ws", tags=["websocket-chat"])


async def save_or_update_thread(
    session_maker,
    thread_id: str,
    user_message: str,
    assistant_message: str,
    user_id: str = "default"
):
    """Save Or Update Thread.

        Args:
            session_maker: Description of session_maker.
            thread_id: Description of thread_id.
            user_message: Description of user_message.
            assistant_message: Description of assistant_message.
            user_id: Description of user_id.
        """


    async with session_maker() as session:
        stmt = select(Thread).where(Thread.thread_id == thread_id)
        result = await session.execute(stmt)
        thread = result.scalar_one_or_none()

        if thread is None:
            if user_message:
                title = user_message[:50] if len(user_message) > 50 else user_message
            else:
                title = "New Conversation"

            last_msg = assistant_message[:200] if len(assistant_message) > 200 else assistant_message
            if not last_msg:
                last_msg = "(no text)"

            thread = Thread(
                thread_id=thread_id,
                user_id=user_id,
                title=title,
                last_message=last_msg,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(thread)
        else:
            last_msg = assistant_message[:200] if len(assistant_message) > 200 else assistant_message
            if not last_msg:
                last_msg = "(no text)"
            thread.last_message = last_msg
            thread.updated_at = datetime.utcnow()

        await session.commit()


def parse_content_blocks(content_data: list) -> List[ContentBlock]:
    """Parse Content Blocks.

        Args:
            content_data: Description of content_data.

        Returns:
            Description of return value.
        """

    content_blocks: List[ContentBlock] = []
    for item in content_data:
        if isinstance(item, dict):
            content_type = item.get("type")
            if content_type == "text":
                content_blocks.append(TextContent(**item))
            elif content_type == "image":
                from src.domain.chat_content import ImageContent
                content_blocks.append(ImageContent(**item))
            elif content_type == "file":
                from src.domain.chat_content import FileContent
                content_blocks.append(FileContent(**item))
            elif content_type == "audio":
                from src.domain.chat_content import AudioContent
                content_blocks.append(AudioContent(**item))
            else:
                content_blocks.append(TextContent(data=str(item)))
        else:
            content_blocks.append(TextContent(data=str(item)))
    return content_blocks


def extract_text_from_content(content_blocks: List[ContentBlock]) -> str:
    """
    Extract display text from ContentBlocks, handling all types.
    - TextContent: use actual text data
    - ImageContent: use "[Image]"
    - FileContent: use "[File: filename]" or "[File]"
    - AudioContent: use "[Audio]"
    Concatenates all blocks with spaces.
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


@router.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """Websocket Chat.

        Args:
            websocket: Description of websocket.
        """

    await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            request_data = json.loads(data)

            action = request_data.get("action")
            runner = websocket.app.state.chat_runner

            if action == "send":
                try:
                    content_data = request_data.get("content", [])
                    thread_id = request_data.get("thread_id") or str(uuid.uuid4())

                    content_blocks = parse_content_blocks(content_data)

                    langchain_content = [block.to_langchain_format() for block in content_blocks]
                    human_message = HumanMessage(content=cast(list, langchain_content))

                    result = await runner.run(
                        messages=[human_message],
                        thread_id=thread_id
                    )

                    messages = result.get("messages", [])
                    if not messages:
                        await websocket.send_json({
                            "type": "error",
                            "error": "No response generated from the assistant"
                        })
                        continue

                    last_message = messages[-1]
                    if not isinstance(last_message, AIMessage):
                        await websocket.send_json({
                            "type": "error",
                            "error": "Expected AI response but got different message type"
                        })
                        continue

                    ai_content = last_message.content
                    content_blocks_response: List[ContentBlock] = []
                    if isinstance(ai_content, str):
                        content_blocks_response = [TextContent(data=ai_content)]
                    elif isinstance(ai_content, list):
                        for item in ai_content:
                            if isinstance(item, str):
                                content_blocks_response.append(TextContent(data=item))
                            elif isinstance(item, dict) and item.get("type") == "text":
                                content_blocks_response.append(TextContent(data=item.get("text", "")))
                            else:
                                content_blocks_response.append(TextContent(data=str(item)))
                    else:
                        content_blocks_response = [TextContent(data=str(ai_content))]

                    timestamp = datetime.now()

                    message = {
                        "role": "assistant",
                        "content": [block.model_dump() for block in content_blocks_response],
                        "timestamp": timestamp.isoformat()
                    }

                    user_message_text = extract_text_from_content(content_blocks)
                    assistant_message_text = extract_text_from_content(content_blocks_response)

                    if hasattr(websocket.app.state, 'db_session_maker'):
                        try:
                            await save_or_update_thread(
                                websocket.app.state.db_session_maker,
                                thread_id,
                                user_message_text,
                                assistant_message_text
                            )
                        except Exception:
                            pass

                    await websocket.send_json({
                        "type": "response",
                        "thread_id": thread_id,
                        "message": message
                    })

                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Error processing send request: {str(e)}"
                    })

            elif action == "stream":
                accumulated_content = ""
                try:
                    content_data = request_data.get("content", [])
                    thread_id = request_data.get("thread_id") or str(uuid.uuid4())

                    await websocket.send_json({
                        "type": "metadata",
                        "thread_id": thread_id
                    })

                    content_blocks = parse_content_blocks(content_data)

                    langchain_content = [block.to_langchain_format() for block in content_blocks]
                    human_message = HumanMessage(content=cast(list, langchain_content))

                    async for event in runner.stream(
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
                                        await websocket.send_json({
                                            "type": "token",
                                            "content": message_chunk.content
                                        })
                                elif isinstance(message_chunk.content, list):
                                    for item in message_chunk.content:
                                        if isinstance(item, str) and item:
                                            accumulated_content += item
                                            await websocket.send_json({
                                                "type": "token",
                                                "content": item
                                            })
                                        elif isinstance(item, dict) and item.get("type") == "text":
                                            text = item.get("text", "")
                                            if text:
                                                accumulated_content += text
                                                await websocket.send_json({
                                                    "type": "token",
                                                    "content": text
                                                })

                    user_message_text = extract_text_from_content(content_blocks)

                    if hasattr(websocket.app.state, 'db_session_maker') and accumulated_content:
                        try:
                            await save_or_update_thread(
                                websocket.app.state.db_session_maker,
                                thread_id,
                                user_message_text,
                                accumulated_content
                            )
                        except Exception:
                            pass

                    await websocket.send_json({"type": "done"})

                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "error": f"Error processing stream request: {str(e)}"
                    })

            else:
                await websocket.send_json({
                    "type": "error",
                    "error": f"Unknown action: {action}. Expected 'send' or 'stream'"
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({
                "type": "error",
                "error": f"WebSocket error: {str(e)}"
            })
        except:
            pass
        finally:
            try:
                await websocket.close()
            except:
                pass
