from __future__ import annotations

import json
import random
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..llm_client import generate_questions, grade_answer
from ..auth import current_user
from ..db import add_weak_topics, last_answered_map, save_answer
from ..pdf_loader import append_generated, load_questions

router = APIRouter(prefix="/api", tags=["questions"])


@router.get("/questions")
def list_questions(user: dict = Depends(current_user)) -> list[dict]:
    return load_questions()


@router.get("/questions/next")
def next_question(user: dict = Depends(current_user)) -> dict:
    pool = load_questions()
    if not pool:
        raise HTTPException(404, "Keine Fragen vorhanden")
    last = last_answered_map(user["id"])
    far_past = "0000"

    def key(q: dict) -> str:
        return last.get(q.get("id", ""), far_past)

    min_ts = min(key(q) for q in pool)
    candidates = [q for q in pool if key(q) == min_ts]
    chosen = random.choice(candidates)
    return {
        "question": chosen,
        "pool_size": len(pool),
        "unanswered_count": sum(1 for q in pool if q.get("id", "") not in last),
    }


class GenerateRequest(BaseModel):
    n: int = 5


@router.post("/questions/generate")
def generate(req: GenerateRequest, user: dict = Depends(current_user)) -> dict:
    n = max(1, min(10, req.n))
    try:
        raw = generate_questions(n)
    except Exception as e:
        raise HTTPException(500, f"Claude-Fehler: {e}")
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%S")
    new = []
    for i, q in enumerate(raw):
        new.append({
            "id": f"gen-{now}-{i}-{uuid4().hex[:6]}",
            "quelle": "KI-generiert",
            "kontext": q.get("kontext", ""),
            "teilfragen": q.get("teilfragen", []),
        })
    append_generated(new)
    return {"added": len(new), "total": len(load_questions())}


class GradeRequest(BaseModel):
    question_id: str | None = None
    question_text: str
    user_answer: str


@router.post("/grade")
def grade(req: GradeRequest, user: dict = Depends(current_user)) -> dict:
    if not req.user_answer.strip():
        raise HTTPException(400, "Antwort ist leer")
    try:
        result = grade_answer(req.question_text, req.user_answer)
    except Exception as e:
        raise HTTPException(500, f"Claude-Fehler: {e}")
    score = int(result.get("score", 0))
    save_answer(user["id"], req.question_id, req.question_text, req.user_answer,
                score, json.dumps(result, ensure_ascii=False))
    topics = result.get("uebungsthemen") or []
    added = add_weak_topics(user["id"], [t for t in topics if isinstance(t, str)])
    result["_weak_topics_added"] = added
    return result
