"""SQLite-Persistenz für Antworten, Quiz-Versuche und Nutzer."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "app.db"


def _conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


def init_db() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          pin TEXT NOT NULL,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS answers (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER,
          question_id TEXT,
          question_text TEXT NOT NULL,
          user_answer TEXT NOT NULL,
          score INTEGER,
          feedback_json TEXT,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS quiz_attempts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER,
          frage TEXT NOT NULL,
          optionen_json TEXT NOT NULL,
          korrekt INTEGER NOT NULL,
          gewaehlt INTEGER,
          erklaerung TEXT,
          topic_id INTEGER,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS weak_topics (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER,
          topic_key TEXT NOT NULL,
          topic TEXT NOT NULL,
          mastery INTEGER NOT NULL DEFAULT 0,
          right_count INTEGER NOT NULL DEFAULT 0,
          wrong_count INTEGER NOT NULL DEFAULT 0,
          archived_at TIMESTAMP,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
          last_reviewed_at TIMESTAMP,
          UNIQUE(user_id, topic_key)
        );
        """)
        # Migration: topic_id in quiz_attempts
        qa_cols = {r[1] for r in c.execute("PRAGMA table_info(quiz_attempts)").fetchall()}
        if "topic_id" not in qa_cols:
            c.execute("ALTER TABLE quiz_attempts ADD COLUMN topic_id INTEGER")
        if "user_id" not in qa_cols:
            c.execute("ALTER TABLE quiz_attempts ADD COLUMN user_id INTEGER")

        # Migration: user_id in answers
        a_cols = {r[1] for r in c.execute("PRAGMA table_info(answers)").fetchall()}
        if "user_id" not in a_cols:
            c.execute("ALTER TABLE answers ADD COLUMN user_id INTEGER")

        # Migration: user_id in weak_topics (benötigt Tabellen-Rebuild, da UNIQUE-Constraint
        # von topic_key auf (user_id, topic_key) wechselt).
        wt_cols = {r[1] for r in c.execute("PRAGMA table_info(weak_topics)").fetchall()}
        if "user_id" not in wt_cols:
            c.executescript("""
            ALTER TABLE weak_topics RENAME TO _weak_topics_old;
            CREATE TABLE weak_topics (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER,
              topic_key TEXT NOT NULL,
              topic TEXT NOT NULL,
              mastery INTEGER NOT NULL DEFAULT 0,
              right_count INTEGER NOT NULL DEFAULT 0,
              wrong_count INTEGER NOT NULL DEFAULT 0,
              archived_at TIMESTAMP,
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              last_reviewed_at TIMESTAMP,
              UNIQUE(user_id, topic_key)
            );
            INSERT INTO weak_topics(id, user_id, topic_key, topic, mastery,
                                    right_count, wrong_count, archived_at,
                                    created_at, last_reviewed_at)
              SELECT id, NULL, topic_key, topic, mastery,
                     right_count, wrong_count, archived_at,
                     created_at, last_reviewed_at
              FROM _weak_topics_old;
            DROP TABLE _weak_topics_old;
            """)


# --- Nutzer ---

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\- ]{2,32}$")
_PIN_RE = re.compile(r"^\d{6}$")


def validate_username(username: str) -> str:
    u = (username or "").strip()
    if not _USERNAME_RE.match(u):
        raise ValueError("Benutzername muss 2–32 Zeichen lang sein (Buchstaben, Ziffern, _ . - Leerzeichen).")
    return u


def validate_pin(pin: str) -> str:
    p = (pin or "").strip()
    if not _PIN_RE.match(p):
        raise ValueError("PIN muss aus genau 6 Ziffern bestehen.")
    return p


def login_or_create(username: str, pin: str) -> dict:
    """Legt Nutzer an, falls es ihn nicht gibt. Sonst prüft PIN.
    Gibt {id, username} zurück oder wirft ValueError bei falscher PIN.
    """
    u = validate_username(username)
    p = validate_pin(pin)
    with _conn() as c:
        row = c.execute("SELECT id, username, pin FROM users WHERE username=?", (u,)).fetchone()
        if row is None:
            cur = c.execute("INSERT INTO users(username, pin) VALUES (?,?)", (u, p))
            return {"id": cur.lastrowid, "username": u}
        if row["pin"] != p:
            raise ValueError("Falsche PIN.")
        return {"id": row["id"], "username": row["username"]}


def get_user(user_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT id, username FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


# --- Antworten ---

def save_answer(user_id: int, question_id: str | None, question_text: str,
                user_answer: str, score: int, feedback_json: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO answers(user_id, question_id, question_text, user_answer, score, feedback_json) "
            "VALUES (?,?,?,?,?,?)",
            (user_id, question_id, question_text, user_answer, score, feedback_json),
        )
        return cur.lastrowid


def save_quiz_attempt(user_id: int, frage: str, optionen_json: str, korrekt: int,
                      gewaehlt: int, erklaerung: str,
                      topic_id: int | None = None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO quiz_attempts(user_id, frage, optionen_json, korrekt, gewaehlt, erklaerung, topic_id) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, frage, optionen_json, korrekt, gewaehlt, erklaerung, topic_id),
        )
        return cur.lastrowid


# --- Schwachstellen ---

MASTERY_THRESHOLD = 3


def _norm(topic: str) -> str:
    return " ".join(topic.lower().split())


def add_weak_topics(user_id: int, topics: list[str]) -> int:
    added = 0
    with _conn() as c:
        for t in topics:
            t = (t or "").strip()
            if not t:
                continue
            key = _norm(t)
            try:
                c.execute(
                    "INSERT INTO weak_topics(user_id, topic_key, topic) VALUES (?,?,?)",
                    (user_id, key, t),
                )
                added += 1
            except sqlite3.IntegrityError:
                c.execute(
                    "UPDATE weak_topics SET archived_at=NULL, "
                    "mastery = MAX(0, mastery - 1) "
                    "WHERE user_id=? AND topic_key=?",
                    (user_id, key),
                )
    return added


def active_weak_topics(user_id: int, limit: int = 20) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM weak_topics WHERE user_id=? AND archived_at IS NULL "
            "ORDER BY mastery ASC, last_reviewed_at IS NULL DESC, last_reviewed_at ASC "
            "LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def all_weak_topics(user_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM weak_topics WHERE user_id=? "
            "ORDER BY archived_at IS NOT NULL, mastery ASC, id DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_topic_mastery(user_id: int, topic_id: int, correct: bool) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM weak_topics WHERE id=? AND user_id=?",
            (topic_id, user_id),
        ).fetchone()
        if not row:
            return None
        mastery = row["mastery"]
        if correct:
            mastery = min(MASTERY_THRESHOLD, mastery + 1)
            c.execute(
                "UPDATE weak_topics SET mastery=?, right_count=right_count+1, "
                "last_reviewed_at=CURRENT_TIMESTAMP, "
                "archived_at=CASE WHEN ?>=? THEN CURRENT_TIMESTAMP ELSE NULL END "
                "WHERE id=?",
                (mastery, mastery, MASTERY_THRESHOLD, topic_id),
            )
        else:
            mastery = max(0, mastery - 1)
            c.execute(
                "UPDATE weak_topics SET mastery=?, wrong_count=wrong_count+1, "
                "last_reviewed_at=CURRENT_TIMESTAMP, archived_at=NULL "
                "WHERE id=?",
                (mastery, topic_id),
            )
        row = c.execute("SELECT * FROM weak_topics WHERE id=?", (topic_id,)).fetchone()
        return dict(row)


# --- Fortschritt ---

def list_answers(user_id: int, limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, question_id, question_text, score, created_at "
            "FROM answers WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def list_quiz_attempts(user_id: int, limit: int = 50) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, frage, korrekt, gewaehlt, created_at "
            "FROM quiz_attempts WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def last_answered_map(user_id: int) -> dict[str, str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT question_id, MAX(created_at) AS last "
            "FROM answers WHERE user_id=? AND question_id IS NOT NULL "
            "GROUP BY question_id",
            (user_id,),
        ).fetchall()
        return {r["question_id"]: r["last"] for r in rows}


def stats(user_id: int) -> dict:
    with _conn() as c:
        avg = c.execute(
            "SELECT AVG(score) AS a, COUNT(*) AS n FROM answers WHERE user_id=?",
            (user_id,),
        ).fetchone()
        q = c.execute(
            "SELECT COUNT(*) AS n, SUM(CASE WHEN korrekt=gewaehlt THEN 1 ELSE 0 END) AS ok "
            "FROM quiz_attempts WHERE user_id=? AND gewaehlt IS NOT NULL",
            (user_id,),
        ).fetchone()
        t = c.execute(
            "SELECT COUNT(*) AS total, "
            "SUM(CASE WHEN archived_at IS NULL THEN 1 ELSE 0 END) AS active, "
            "SUM(CASE WHEN archived_at IS NOT NULL THEN 1 ELSE 0 END) AS mastered "
            "FROM weak_topics WHERE user_id=?",
            (user_id,),
        ).fetchone()
        return {
            "answers_count": avg["n"] or 0,
            "answers_avg_score": round(avg["a"], 1) if avg["a"] is not None else None,
            "quiz_count": q["n"] or 0,
            "quiz_correct": q["ok"] or 0,
            "topics_active": t["active"] or 0,
            "topics_mastered": t["mastered"] or 0,
        }
