from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime
from src.domain.chat_content import ContentBlock, TextContent


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"] = Field(
        ..., 
        description="Role of the message sender"
    )
    content: List[ContentBlock] = Field(
        ...,
        description="Multimodal message content as a list of content blocks"
    )
    id: Optional[str] = Field(
        None,
        description="Message ID from LangGraph for tracking and time-travel"
    )
    timestamp: Optional[datetime] = Field(
        None,
        description="Timestamp of when the message was created"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "data": "Hello, can you help me?"
                        }
                    ],
                    "timestamp": "2025-10-01T12:00:00"
                },
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "text",
                            "data": "Of course! How can I assist you today?"
                        }
                    ],
                    "timestamp": "2025-10-01T12:00:05"
                }
            ]
        }
    }


class ChatSendRequest(BaseModel):
    content: List[ContentBlock] = Field(
        ...,
        description="Multimodal message content to send to the assistant"
    )
    thread_id: Optional[str] = Field(
        None,
        description="Thread ID for continuing an existing conversation"
    )
    model: Optional[str] = Field(
        "gemini-2.0-flash-exp",
        description="Model to use for the chat completion"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "content": [
                        {
                            "type": "text",
                            "data": "What's in this image?"
                        },
                        {
                            "type": "image",
                            "data": "https://example.com/image.jpg",
                            "mime_type": "image/jpeg",
                            "source_type": "url"
                        }
                    ],
                    "thread_id": "thread_123",
                    "model": "gemini-2.0-flash-exp"
                }
            ]
        }
    }


class ChatStreamRequest(BaseModel):
    content: List[ContentBlock] = Field(
        ...,
        description="Multimodal message content to send to the assistant"
    )
    thread_id: Optional[str] = Field(
        None,
        description="Thread ID for continuing an existing conversation"
    )
    model: Optional[str] = Field(
        "gemini-2.0-flash-exp",
        description="Model to use for the chat completion"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "content": [
                        {
                            "type": "text",
                            "data": "Tell me a story"
                        }
                    ],
                    "thread_id": None,
                    "model": "gemini-2.0-flash-exp"
                }
            ]
        }
    }


class ChatResponse(BaseModel):
    thread_id: str = Field(
        ...,
        description="Thread ID of the conversation"
    )
    message: ChatMessage = Field(
        ...,
        description="The assistant's response message"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp of when the response was created"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "thread_id": "thread_123",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "data": "I can see a beautiful landscape in the image."
                            }
                        ],
                        "timestamp": "2025-10-01T12:00:10"
                    },
                    "created_at": "2025-10-01T12:00:10"
                }
            ]
        }
    }


class ChatHistoryResponse(BaseModel):
    thread_id: str = Field(
        ...,
        description="Thread ID of the conversation"
    )
    messages: List[ChatMessage] = Field(
        ...,
        description="List of all messages in the conversation thread"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "thread_id": "thread_123",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "data": "Hello!"
                                }
                            ],
                            "timestamp": "2025-10-01T12:00:00"
                        },
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "text",
                                    "data": "Hi! How can I help you?"
                                }
                            ],
                            "timestamp": "2025-10-01T12:00:05"
                        }
                    ]
                }
            ]
        }
    }


class ThreadInfo(BaseModel):
    thread_id: str = Field(
        ...,
        description="Unique identifier for the thread"
    )
    title: str = Field(
        ...,
        description="Title or summary of the conversation"
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp of when the thread was created"
    )
    last_message_preview: str = Field(
        ...,
        description="Preview text of the last message in the thread"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "thread_id": "thread_123",
                    "title": "Image Analysis Discussion",
                    "created_at": "2025-10-01T12:00:00",
                    "last_message_preview": "I can see a beautiful landscape in the image."
                }
            ]
        }
    }


class ThreadListResponse(BaseModel):
    threads: List[ThreadInfo] = Field(
        ...,
        description="List of conversation threads"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "threads": [
                        {
                            "thread_id": "thread_123",
                            "title": "Image Analysis Discussion",
                            "created_at": "2025-10-01T12:00:00",
                            "last_message_preview": "I can see a beautiful landscape..."
                        },
                        {
                            "thread_id": "thread_456",
                            "title": "Code Review Help",
                            "created_at": "2025-10-01T11:30:00",
                            "last_message_preview": "The code looks good overall..."
                        }
                    ]
                }
            ]
        }
    }


class RetryRequest(BaseModel):
    message_id: str = Field(
        ...,
        description="Message ID to retry/regenerate from (uses LangGraph's message ID merging)"
    )
    content: Optional[List[ContentBlock]] = Field(
        None,
        description="Optional modified content to replace the message before regenerating"
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "message_id": "run--35d47f25-e63f-46c3-9307-ff7f20cc0a28-0",
                    "content": [
                        {
                            "type": "text",
                            "data": "Can you provide more detail?"
                        }
                    ]
                },
                {
                    "message_id": "ef990c30-bcef-4be5-b7e1-b...",
                    "content": None
                }
            ]
        }
    }
