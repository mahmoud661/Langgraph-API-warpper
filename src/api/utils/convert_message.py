"""Convert Message module."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from api.schemas.chat import ChatMessage
from src.domain.chat_content import ContentBlock, ImageContent, SourceType, TextContent


def convert_langchain_message_to_chat_message(msg: BaseMessage) -> ChatMessage:
    """
    Convert a LangGraph BaseMessage to ChatMessage schema with ID.

    Args:
        msg: LangGraph message (HumanMessage, AIMessage, etc.)

    Returns:
        ChatMessage with role, content blocks, and ID
    """
    if isinstance(msg, HumanMessage):
        role = "user"
    elif isinstance(msg, AIMessage):
        role = "assistant"
    else:
        role = "system"

    content_blocks: list[ContentBlock] = []
    msg_content = msg.content

    if isinstance(msg_content, str):
        content_blocks = [TextContent(data=msg_content)]
    elif isinstance(msg_content, list):
        for item in msg_content:
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
        content_blocks = [TextContent(data=str(msg_content))]

    message_id = getattr(msg, 'id', None)

    return ChatMessage(
        role=role,
        content=content_blocks,
        id=message_id,
        timestamp=None
    )
