"""Einmalige Aufbereitung der PDFs in LLM-optimiertes Markdown.

Stufe A1: pypdf -> cache/raw/*.txt
Stufe A2: regelbasierte Bereinigung
Stufe A3: Opus 4.7 (1M Kontext) -> cache/processed/*.md + cache/questions.json
Stufe A4: INDEX.md aus allen H2-Überschriften

Ausführen:   python scripts/preprocess.py
Braucht:     ANTHROPIC_API_KEY in Umgebung oder .env
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
CACHE = ROOT / "cache"
RAW = CACHE / "raw"
PROCESSED = CACHE / "processed"
QUESTIONS_JSON = CACHE / "questions.json"

PREPROCESS_MODEL = "claude-opus-4-7"
BETA_1M = "context-1m-2025-08-07"


def slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")


def extract_raw() -> dict[str, str]:
    RAW.mkdir(parents=True, exist_ok=True)
    results: dict[str, str] = {}
    for pdf_path in sorted(DOCS.glob("*.pdf")):
        out = RAW / (slugify(pdf_path.stem) + ".txt")
        if out.exists():
            results[pdf_path.stem] = out.read_text(encoding="utf-8")
            print(f"  [cache] {pdf_path.name}")
            continue
        try:
            reader = PdfReader(str(pdf_path))
            pages = [p.extract_text() or "" for p in reader.pages]
            text = "\n\n".join(pages)
            out.write_text(text, encoding="utf-8")
            results[pdf_path.stem] = text
            print(f"  [ok]    {pdf_path.name} ({len(text):,} Zeichen, {len(pages)} Seiten)")
            if len(text.strip()) < 100:
                print(f"  [WARN]  {pdf_path.name}: fast leer - evtl. bildbasiert, OCR nötig")
        except Exception as e:
            print(f"  [ERR]   {pdf_path.name}: {e}", file=sys.stderr)
    return results


def clean_text(raw: str) -> str:
    lines = raw.splitlines()

    # Wiederkehrende Zeilen (Kopf/Fuß) entfernen: erscheinen >=3x identisch
    stripped = [ln.strip() for ln in lines]
    counts = Counter(s for s in stripped if s)
    repeated = {s for s, c in counts.items() if c >= 3 and len(s) < 80}

    kept: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s in repeated:
            continue
        if re.fullmatch(r"\d{1,3}", s):  # Seitenzahl
            continue
        kept.append(ln)

    text = "\n".join(kept)
    # Silbentrennung zusammenführen: "Mitar-\nbeiter" -> "Mitarbeiter"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # Einzelne Zeilenumbrüche in Absätzen zu Leerzeichen (nur wenn kein Listen-/Satzende)
    text = re.sub(r"(?<![\.\?\!\:\-\*])\n(?!\n)", " ", text)
    # Mehrfache Leerzeilen
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


PROMPT_PREPROCESS = """Du bekommst den Roh-Textkorpus mehrerer deutscher Lehrunterlagen zur Meisterprüfung Personal (IHK). Jede Quelldatei ist durch `===== FILE: <name> =====` getrennt.

Deine Aufgabe:

1. Wandle jede Datei in sauberes deutsches Markdown um:
   - Erhalte ALLE Fachinhalte 1:1. Keine Paraphrasen, keine Kürzungen, nichts hinzudichten.
   - Ergänze sinnvolle Überschriften (H1 Haupttitel, H2 Kapitel, H3 Unterabschnitte).
   - Aufzählungen/Listen als Markdown-Listen, Tabellen als Markdown-Tabellen wenn erkennbar.
   - Entferne Layout-Artefakte (Seitenzahlen, wiederholte Kopfzeilen).
   - Fachbegriffe/Abkürzungen unverändert lassen.

2. Für Dateien, deren Namen "Übungsfragen" oder "Fachgesprächsfragen" enthalten, extrahiere zusätzlich ALLE Prüfungsfragen strukturiert (Nummer + Kontext + Teilfragen).

Gib deine Antwort in genau diesem Format aus (KEIN JSON für Markdown-Inhalt, damit keine Escape-Probleme entstehen):

====FILE_START: <originalname ohne .pdf>====
# Titel
... (Markdown-Inhalt) ...
====FILE_END====

====FILE_START: <nächste datei>====
...
====FILE_END====

(... für jede Quelldatei eine FILE-Sektion ...)

====QUESTIONS_START====
[
  {"id": "uebung-1", "quelle": "Übungsfragen Fachgespräch Personal", "kontext": "...", "teilfragen": ["...", "..."]},
  {"id": "uebung-2", ...}
]
====QUESTIONS_END====

Wichtig:
- Zwischen FILE_START und FILE_END steht roher Markdown. Keinerlei Escaping nötig.
- Der QUESTIONS-Block enthält ein JSON-Array. Stellen Sicher, dass es valides JSON ist (innere Anführungszeichen in Strings mit \\" escapen).
- Kein einleitender Text, keine Code-Fences, keine Kommentare außerhalb der Blöcke."""


def call_opus(corpus: str) -> dict:
    from anthropic import Anthropic

    client = Anthropic()

    print(f"\n[Opus 4.7] Sende Korpus ({len(corpus):,} Zeichen) …")
    parts: list[str] = []
    with client.messages.stream(
        model=PREPROCESS_MODEL,
        max_tokens=64000,
        system=PROMPT_PREPROCESS,
        messages=[{"role": "user", "content": corpus}],
    ) as stream:
        for delta in stream.text_stream:
            parts.append(delta)
            print(".", end="", flush=True)
        final = stream.get_final_message()
    print()
    usage = final.usage
    print(f"[Opus 4.7] Input tokens: {usage.input_tokens:,}, Output tokens: {usage.output_tokens:,}, stop: {final.stop_reason}")
    text = "".join(parts)
    (CACHE / "opus_raw.txt").write_text(text, encoding="utf-8")
    return parse_delimited(text)


def parse_delimited(text: str) -> dict:
    files = []
    for m in re.finditer(
        r"====FILE_START:\s*(.*?)====\s*\n([\s\S]*?)\n====FILE_END====",
        text,
    ):
        files.append({"filename": m.group(1).strip(), "markdown": m.group(2).strip()})

    questions: list = []
    qm = re.search(r"====QUESTIONS_START====\s*([\s\S]*?)\s*====QUESTIONS_END====", text)
    if qm:
        raw = qm.group(1).strip()
        try:
            questions = json.loads(raw)
        except json.JSONDecodeError:
            try:
                import json_repair  # type: ignore
                questions = json_repair.loads(raw)
            except Exception as e:
                print(f"  [WARN] questions JSON konnte nicht geparst werden: {e}")
    return {"files": files, "questions": questions}


def write_processed(result: dict) -> None:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    for f in result.get("files", []):
        name = slugify(f["filename"]) + ".md"
        (PROCESSED / name).write_text(f["markdown"], encoding="utf-8")
        print(f"  [md]    {name} ({len(f['markdown']):,} Zeichen)")

    # INDEX.md aus H2-Überschriften
    index_lines = ["# Inhaltsverzeichnis\n"]
    for md_file in sorted(PROCESSED.glob("*.md")):
        if md_file.name == "INDEX.md":
            continue
        index_lines.append(f"\n## {md_file.stem}\n")
        for line in md_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                index_lines.append(f"- {line[3:].strip()}")
    (PROCESSED / "INDEX.md").write_text("\n".join(index_lines), encoding="utf-8")
    print(f"  [md]    INDEX.md")

    questions = result.get("questions", [])
    QUESTIONS_JSON.write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [json]  questions.json ({len(questions)} Fragen)")


def main() -> int:
    load_dotenv(ROOT / ".env", override=True)
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY fehlt (in .env oder Umgebung setzen)", file=sys.stderr)
        return 1

    print("\n=== Stufe 1: Raw-Extraktion ===")
    raws = extract_raw()

    print("\n=== Stufe 2: Bereinigung ===")
    cleaned = {name: clean_text(t) for name, t in raws.items()}
    for name, t in cleaned.items():
        print(f"  {name}: {len(t):,} Zeichen")

    print("\n=== Stufe 3: Opus 4.7 Aufbereitung ===")
    corpus = "\n\n".join(
        f"===== FILE: {name} =====\n{t}" for name, t in cleaned.items()
    )
    result = call_opus(corpus)

    print("\n=== Stufe 4: Schreiben ===")
    write_processed(result)

    print("\nFertig. Ergebnis in cache/processed/ und cache/questions.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
