"""LLM-Client via OpenRouter (OpenAI-kompatibel).

Laufzeit-Modell: openai/gpt-oss-120b:free über OpenRouter.
Das PDF-Preprocessing (scripts/preprocess.py) bleibt auf Anthropic Opus 4.7.
"""
from __future__ import annotations

import json
import os
import re
from typing import AsyncIterator

from openai import AsyncOpenAI, OpenAI

from .pdf_loader import load_knowledge_corpus
from .prompts import CHAT_SYSTEM, GRADER_SYSTEM, QUESTION_GEN_SYSTEM, QUIZ_SYSTEM, WEAK_QUIZ_SYSTEM

MODEL = "openai/gpt-oss-120b:free"
BASE_URL = "https://openrouter.ai/api/v1"
MAX_TOKENS = 4096


def _api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY ist nicht gesetzt (in .env eintragen).")
    return key


def _headers() -> dict:
    return {
        "HTTP-Referer": os.environ.get("OPENROUTER_REFERER", "http://localhost:8000"),
        "X-Title": "Fachgespraechs-Trainer",
    }


def _sync_client() -> OpenAI:
    return OpenAI(api_key=_api_key(), base_url=BASE_URL, default_headers=_headers())


def _async_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=_api_key(), base_url=BASE_URL, default_headers=_headers())


def _system_message(role_prompt: str) -> dict:
    corpus = load_knowledge_corpus()
    content = role_prompt
    if corpus:
        content += (
            "\n\n--- LEHRMATERIAL (Quelle: Meisterprüfung Personal) ---\n\n"
            + corpus
        )
    return {"role": "system", "content": content}


def _extract_json(text: str) -> str:
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        return fence.group(1).strip()
    return text.strip()


def _complete(system_prompt: str, user_msg: str) -> str:
    client = _sync_client()
    resp = client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[_system_message(system_prompt), {"role": "user", "content": user_msg}],
    )
    return resp.choices[0].message.content or ""


def grade_answer(question_text: str, user_answer: str) -> dict:
    user_msg = (
        f"PRÜFUNGSFRAGE:\n{question_text}\n\n"
        f"ANTWORT DES PRÜFLINGS:\n{user_answer}\n\n"
        "Bewerte jetzt."
    )
    text = _complete(GRADER_SYSTEM, user_msg)
    return json.loads(_extract_json(text))


def generate_quiz(topic: str, n: int) -> list[dict]:
    user_msg = (
        f"Thema: {topic or 'Querschnitt aus dem gesamten Material'}\n"
        f"Erstelle {n} Multiple-Choice-Fragen."
    )
    text = _complete(QUIZ_SYSTEM, user_msg)
    return json.loads(_extract_json(text))


def generate_weak_quiz(topics: list[str]) -> list[dict]:
    bullets = "\n".join(f"- {t}" for t in topics)
    user_msg = f"Themen:\n{bullets}\n\nErzeuge zu jedem Thema genau eine MC-Frage."
    text = _complete(WEAK_QUIZ_SYSTEM, user_msg)
    return json.loads(_extract_json(text))


def generate_questions(n: int) -> list[dict]:
    text = _complete(QUESTION_GEN_SYSTEM, f"Erzeuge {n} neue Prüfungsfragen.")
    return json.loads(_extract_json(text))


async def chat_stream(history: list[dict]) -> AsyncIterator[str]:
    client = _async_client()
    messages = [_system_message(CHAT_SYSTEM)] + [
        {"role": m["role"], "content": m["content"]} for m in history
    ]
    stream = await client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if delta:
            yield delta
