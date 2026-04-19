from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import current_user
from ..db import all_weak_topics, list_answers, list_quiz_attempts, stats

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("")
def get_progress(user: dict = Depends(current_user)) -> dict:
    uid = user["id"]
    return {
        "stats": stats(uid),
        "answers": list_answers(uid, 20),
        "quiz": list_quiz_attempts(uid, 20),
        "topics": all_weak_topics(uid),
    }
