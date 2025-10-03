"""Chat Content module."""

import base64
import re
from enum import Enum
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class ContentType(str, Enum):
    """ContentType class."""

    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"


class SourceType(str, Enum):
    """SourceType class."""

    BASE64 = "base64"
    URL = "url"


class TextContent(BaseModel):
    """TextContent class."""

    type: Literal[ContentType.TEXT] = ContentType.TEXT
    data: str = Field(..., description="Text content")

    def to_langchain_format(self) -> dict[str, Any]:
        """To Langchain Format.


        Returns:
            Description of return value.
        """

        return {"type": "text", "text": self.data}


class ImageContent(BaseModel):
    """ImageContent class."""

    type: Literal[ContentType.IMAGE] = ContentType.IMAGE
    data: str = Field(..., description="Image data as base64 string or URL")
    mime_type: str = Field(..., description="MIME type of the image (e.g., image/png, image/jpeg)")
    source_type: SourceType = Field(..., description="Whether data is base64 encoded or a URL")

    @field_validator("mime_type")
    @classmethod
    def validate_image_mime_type(cls, v: str) -> str:
        """Validate Image Mime Type.

        Args:
            cls: Description of cls.
            v: Description of v.

        Returns:
            Description of return value.
        """

        valid_image_types = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp", "image/svg+xml", "image/bmp"]
        if v.lower() not in valid_image_types:
            raise ValueError(f"Invalid image MIME type: {v}. Must be one of {valid_image_types}")
        return v.lower()

    @field_validator("data")
    @classmethod
    def validate_data_format(cls, v: str, info) -> str:
        """Validate Data Format.

        Args:
            cls: Description of cls.
            v: Description of v.
            info: Description of info.

        Returns:
            Description of return value.
        """

        source_type = info.data.get("source_type")
        if source_type == SourceType.BASE64:
            try:
                base64.b64decode(v, validate=True)
            except Exception as e:
                raise ValueError(f"Invalid base64 format: {str(e)}") from e
        elif source_type == SourceType.URL:
            url_pattern = re.compile(
                r"^https?://"
                r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
                r"localhost|"
                r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
                r"(?::\d+)?"
                r"(?:/?|[/?]\S+)$",
                re.IGNORECASE,
            )
            if not url_pattern.match(v):
                raise ValueError(f"Invalid URL format: {v}")
        return v

    def to_langchain_format(self) -> dict[str, Any]:
        """To Langchain Format.


        Returns:
            Description of return value.
        """

        if self.source_type == SourceType.URL:
            return {"type": "image_url", "image_url": {"url": self.data}}
        else:
            return {"type": "image_url", "image_url": {"url": f"data:{self.mime_type};base64,{self.data}"}}


class FileContent(BaseModel):
    """FileContent class."""

    type: Literal[ContentType.FILE] = ContentType.FILE
    data: str = Field(..., description="File data as base64 string or URL")
    mime_type: str = Field(..., description="MIME type of the file")
    source_type: SourceType = Field(..., description="Whether data is base64 encoded or a URL")
    filename: Optional[str] = Field(None, description="Original filename if available")

    @field_validator("mime_type")
    @classmethod
    def validate_file_mime_type(cls, v: str) -> str:
        """Validate File Mime Type.

        Args:
            cls: Description of cls.
            v: Description of v.

        Returns:
            Description of return value.
        """

        mime_pattern = re.compile(r"^[a-z]+/[a-z0-9\-\+\.]+$", re.IGNORECASE)
        if not mime_pattern.match(v):
            raise ValueError(f"Invalid MIME type format: {v}")
        return v.lower()

    @field_validator("data")
    @classmethod
    def validate_data_format(cls, v: str, info) -> str:
        """Validate Data Format.

        Args:
            cls: Description of cls.
            v: Description of v.
            info: Description of info.

        Returns:
            Description of return value.
        """

        source_type = info.data.get("source_type")
        if source_type == SourceType.BASE64:
            try:
                base64.b64decode(v, validate=True)
            except Exception as e:
                raise ValueError(f"Invalid base64 format: {str(e)}") from e
        elif source_type == SourceType.URL:
            url_pattern = re.compile(
                r"^https?://"
                r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
                r"localhost|"
                r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
                r"(?::\d+)?"
                r"(?:/?|[/?]\S+)$",
                re.IGNORECASE,
            )
            if not url_pattern.match(v):
                raise ValueError(f"Invalid URL format: {v}")
        return v

    def to_langchain_format(self) -> dict[str, Any]:
        """To Langchain Format.


        Returns:
            Description of return value.
        """

        result: dict[str, Any] = {"type": "file", "mime_type": self.mime_type}

        if self.source_type == SourceType.URL:
            result["file_url"] = {"url": self.data}
        else:
            result["file_url"] = {"url": f"data:{self.mime_type};base64,{self.data}"}

        if self.filename:
            result["filename"] = self.filename

        return result


class AudioContent(BaseModel):
    """AudioContent class."""

    type: Literal[ContentType.AUDIO] = ContentType.AUDIO
    data: str = Field(..., description="Audio data as base64 string or URL")
    mime_type: str = Field(..., description="MIME type of the audio (e.g., audio/mpeg, audio/wav)")
    source_type: SourceType = Field(..., description="Whether data is base64 encoded or a URL")

    @field_validator("mime_type")
    @classmethod
    def validate_audio_mime_type(cls, v: str) -> str:
        """Validate Audio Mime Type.

        Args:
            cls: Description of cls.
            v: Description of v.

        Returns:
            Description of return value.
        """

        valid_audio_types = ["audio/mpeg", "audio/mp3", "audio/wav", "audio/ogg", "audio/webm", "audio/aac", "audio/flac", "audio/m4a"]
        if v.lower() not in valid_audio_types:
            raise ValueError(f"Invalid audio MIME type: {v}. Must be one of {valid_audio_types}")
        return v.lower()

    @field_validator("data")
    @classmethod
    def validate_data_format(cls, v: str, info) -> str:
        """Validate Data Format.

        Args:
            cls: Description of cls.
            v: Description of v.
            info: Description of info.

        Returns:
            Description of return value.
        """

        source_type = info.data.get("source_type")
        if source_type == SourceType.BASE64:
            try:
                base64.b64decode(v, validate=True)
            except Exception as e:
                raise ValueError(f"Invalid base64 format: {str(e)}") from e
        elif source_type == SourceType.URL:
            url_pattern = re.compile(
                r"^https?://"
                r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
                r"localhost|"
                r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
                r"(?::\d+)?"
                r"(?:/?|[/?]\S+)$",
                re.IGNORECASE,
            )
            if not url_pattern.match(v):
                raise ValueError(f"Invalid URL format: {v}")
        return v

    def to_langchain_format(self) -> dict[str, Any]:
        """To Langchain Format.


        Returns:
            Description of return value.
        """

        if self.source_type == SourceType.URL:
            return {"type": "audio_url", "audio_url": {"url": self.data}}
        else:
            return {"type": "audio_url", "audio_url": {"url": f"data:{self.mime_type};base64,{self.data}"}}


ContentBlock = Union[TextContent, ImageContent, FileContent, AudioContent]


class MultimodalContent(BaseModel):
    """MultimodalContent class."""

    content: list[ContentBlock] = Field(..., description="Array of content blocks, each with a type discriminator")

    @field_validator("content")
    @classmethod
    def validate_content_not_empty(cls, v: list[ContentBlock]) -> list[ContentBlock]:
        """Validate Content Not Empty.

        Args:
            cls: Description of cls.
            v: Description of v.

        Returns:
            Description of return value.
        """

        if not v:
            raise ValueError("Content array must not be empty")
        return v

    def to_langchain_format(self) -> list[dict[str, Any]]:
        """To Langchain Format.


        Returns:
            Description of return value.
        """

        return [block.to_langchain_format() for block in self.content]

    @classmethod
    def from_text(cls, text: str) -> "MultimodalContent":
        """From Text.

        Args:
            cls: Description of cls.
            text: Description of text.

        Returns:
            Description of return value.
        """

        return cls(content=[TextContent(data=text)])

    @classmethod
    def from_blocks(cls, blocks: list[ContentBlock]) -> "MultimodalContent":
        """From Blocks.

        Args:
            cls: Description of cls.
            blocks: Description of blocks.

        Returns:
            Description of return value.
        """

        return cls(content=blocks)
