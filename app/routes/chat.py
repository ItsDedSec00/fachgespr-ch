from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..llm_client import chat_stream
from ..auth import current_user

router = APIRouter(prefix="/api", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


@router.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(current_user)):
    history = [{"role": m.role, "content": m.content} for m in req.messages]

    async def gen():
        async for chunk in chat_stream(history):
            yield chunk

    return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
