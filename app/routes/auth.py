from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..auth import COOKIE_MAX_AGE, COOKIE_NAME, current_user
from ..db import login_or_create

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    pin: str


@router.post("/login")
def login(req: LoginRequest, response: Response) -> dict:
    try:
        user = login_or_create(req.username, req.pin)
    except ValueError as e:
        raise HTTPException(400, str(e))
    response.set_cookie(
        key=COOKIE_NAME,
        value=str(user["id"]),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
    )
    return {"user": user}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(current_user)) -> dict:
    return {"user": user}
