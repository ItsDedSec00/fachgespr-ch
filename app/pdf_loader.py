"""Lädt aufbereitete Markdown-Dateien und Fragen-Bank zur Laufzeit."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "cache" / "processed"
QUESTIONS_JSON = ROOT / "cache" / "questions.json"
GENERATED_JSON = ROOT / "cache" / "generated_questions.json"


def load_knowledge_corpus() -> str:
    if not PROCESSED.exists():
        return ""
    parts: list[str] = []
    for md in sorted(PROCESSED.glob("*.md")):
        parts.append(f"\n\n===== {md.stem} =====\n\n{md.read_text(encoding='utf-8')}")
    return "".join(parts).strip()


def load_questions() -> list[dict]:
    qs: list[dict] = []
    if QUESTIONS_JSON.exists():
        qs.extend(json.loads(QUESTIONS_JSON.read_text(encoding="utf-8")))
    if GENERATED_JSON.exists():
        qs.extend(json.loads(GENERATED_JSON.read_text(encoding="utf-8")))
    return qs


def append_generated(new: list[dict]) -> None:
    existing: list[dict] = []
    if GENERATED_JSON.exists():
        existing = json.loads(GENERATED_JSON.read_text(encoding="utf-8"))
    existing.extend(new)
    GENERATED_JSON.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_JSON.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def corpus_ready() -> bool:
    return PROCESSED.exists() and any(PROCESSED.glob("*.md"))
