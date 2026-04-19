from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..llm_client import generate_quiz, generate_weak_quiz
from ..auth import current_user
from ..db import active_weak_topics, save_quiz_attempt, update_topic_mastery

router = APIRouter(prefix="/api/quiz", tags=["quiz"])


class QuizRequest(BaseModel):
    topic: str = ""
    n: int = 5


@router.post("/generate")
def generate(req: QuizRequest, user: dict = Depends(current_user)) -> list[dict]:
    n = max(1, min(10, req.n))
    try:
        return generate_quiz(req.topic, n)
    except Exception as e:
        raise HTTPException(500, f"Claude-Fehler: {e}")


PER_TOPIC = 3


@router.post("/from_weak")
def from_weak(req: QuizRequest, user: dict = Depends(current_user)) -> dict:
    n = max(1, min(15, req.n))
    # Anzahl Themen aus Gesamt-Fragen ableiten (PER_TOPIC Fragen je Thema)
    num_topics = max(1, (n + PER_TOPIC - 1) // PER_TOPIC)
    topics = active_weak_topics(user["id"], limit=num_topics)
    if not topics:
        return {"questions": [], "message": "Keine Schwachstellen vorhanden — erst offene Fragen beantworten und bewerten lassen."}
    try:
        raw = generate_weak_quiz([t["topic"] for t in topics], per_topic=PER_TOPIC)
    except Exception as e:
        raise HTTPException(500, f"Claude-Fehler: {e}")
    by_topic = {t["topic"]: t["id"] for t in topics}
    questions = []
    for q in raw:
        topic_name = q.get("topic") or ""
        topic_id = by_topic.get(topic_name)
        if not topic_id and topics:
            topic_id = topics[0]["id"]
            topic_name = topics[0]["topic"]
        questions.append({
            "frage": q["frage"],
            "optionen": q["optionen"],
            "korrekt": q["korrekt"],
            "erklaerung": q.get("erklaerung", ""),
            "topic_id": topic_id,
            "topic": topic_name,
        })
    # auf n Fragen trimmen (falls das Modell etwas mehr geliefert hat)
    questions = questions[:n]
    return {"questions": questions}


class AnswerRequest(BaseModel):
    frage: str
    optionen: list[str]
    korrekt: int
    gewaehlt: int
    erklaerung: str
    topic_id: int | None = None


@router.post("/answer")
def answer(req: AnswerRequest, user: dict = Depends(current_user)) -> dict:
    save_quiz_attempt(user["id"], req.frage, json.dumps(req.optionen, ensure_ascii=False),
                      req.korrekt, req.gewaehlt, req.erklaerung, req.topic_id)
    correct = req.korrekt == req.gewaehlt
    topic_state = None
    if req.topic_id:
        topic_state = update_topic_mastery(user["id"], req.topic_id, correct)
    return {"richtig": correct, "topic": topic_state}
