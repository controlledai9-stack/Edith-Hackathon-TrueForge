from typing import Literal, Optional
from pydantic import BaseModel, Field

from config import MAX_MESSAGE_LENGTH


class TextAttachment(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    # Research documents may arrive as a base64 data URL and are extracted on
    # the server before entering the token-bounded source pipeline.
    content: str = Field(..., min_length=1, max_length=24_000_000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)
    session_id: Optional[str] = None
    tts: bool = False
    imgbase64: Optional[str] = None
    imgbase64s: list[str] = Field(default_factory=list, max_length=8)
    text_attachments: list[TextAttachment] = Field(default_factory=list, max_length=8)
    mode: Literal["edit", "work", "research"] = "edit"
    research_branch: Literal["research", "homework"] = "research"
    homework_output: Literal["board", "chat"] = "board"
    auto_approve_safe_work: bool = True
    model_preference: str = Field(default="auto", min_length=1, max_length=200)


class ChatResponse(BaseModel):
    session_id: str
    reply: str


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)


class HealthResponse(BaseModel):
    status: str
    groq: bool = True
    tavily: bool = True
    vector_store: bool = True
