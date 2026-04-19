# Fachgesprächs-Trainer

Lokale Webanwendung zum Üben für die Meisterprüfung Personal (IHK).
Claude Sonnet 4.6 stellt Fragen aus den PDFs, bewertet offene Antworten, generiert Multiple-Choice-Quizzes und beantwortet freie Fragen zum Stoff.

## Erststart (einmalig)

1. **`.env` anlegen** (Kopie von `.env.example`) und Anthropic-API-Key eintragen:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```

2. **PDFs aufbereiten** (einmalig, nutzt Opus 4.7 mit 1M-Kontext):
   ```bash
   python -m venv .venv
   source .venv/Scripts/activate     # Windows Git Bash; sonst .venv\Scripts\activate bzw. .venv/bin/activate
   pip install -r requirements.txt
   python scripts/preprocess.py
   ```
   Ergebnis: `cache/processed/*.md` + `cache/questions.json`. Stichprobenartig eine `.md` im Editor öffnen und prüfen.

## App starten (Docker Desktop)

```bash
docker compose up --build
```

Öffnen: http://localhost:8000

## Tabs

- **Fragen üben** — Prüfungsfrage auswählen, offen antworten, Claude bewertet mit Score + Musterantwort
- **Quiz** — Multiple-Choice-Fragen zu gewünschtem Thema generieren lassen
- **Chat** — Freie Fragen zum Lehrmaterial, Antwort streamt
- **Fortschritt** — Score-Historie aus SQLite (Volume `data/`)

## Wichtige Pfade

| Pfad | Inhalt |
|---|---|
| `docs/` | Original-PDFs (read-only im Container) |
| `cache/processed/*.md` | aufbereitetes Lehrmaterial |
| `cache/questions.json` | strukturierte Prüfungsfragen |
| `data/app.db` | SQLite mit Antworten & Quiz-Versuchen |

## Notizen

- Der gesamte Wissenskorpus wird per Prompt Caching an Sonnet 4.6 gesendet. Nach dem ersten Call kommen weitere Requests aus dem Cache (~90 % günstiger).
- Preprocessing ist einmalig — `cache/processed/` kann committed werden.
- Ohne `data/`-Verzeichnis legt der Container es an; Fortschritt überlebt Neustarts.
