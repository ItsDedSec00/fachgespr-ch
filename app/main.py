from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .pdf_loader import corpus_ready
from .routes import auth, chat, progress, questions, quiz, transcribe

load_dotenv(override=True)
init_db()

app = FastAPI(title="Fachgesprächs-Trainer")

app.include_router(auth.router)
app.include_router(questions.router)
app.include_router(quiz.router)
app.include_router(chat.router)
app.include_router(progress.router)
app.include_router(transcribe.router)


@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "corpus_ready": corpus_ready()}


STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
