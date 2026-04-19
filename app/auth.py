"""Einfache Cookie-Sessions: uid = user_id als httpOnly-Cookie."""
from __future__ import annotations

from fastapi import Cookie, HTTPException

from .db import get_user

COOKIE_NAME = "uid"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 Tage


def current_user(uid: str | None = Cookie(default=None)) -> dict:
    if not uid or not uid.isdigit():
        raise HTTPException(401, "Nicht angemeldet")
    user = get_user(int(uid))
    if not user:
        raise HTTPException(401, "Nicht angemeldet")
    return user
