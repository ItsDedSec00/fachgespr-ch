from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from ..auth import current_user

router = APIRouter(prefix="/api", tags=["transcribe"])

_MODEL = None
_MODEL_SIZE = "small"  # "tiny" / "base" / "small" / "medium"


def _get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        cache_dir = Path("/app/cache/whisper")
        cache_dir.mkdir(parents=True, exist_ok=True)
        _MODEL = WhisperModel(
            _MODEL_SIZE,
            device="cpu",
            compute_type="int8",
            download_root=str(cache_dir),
        )
    return _MODEL


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    user: dict = Depends(current_user),
) -> dict:
    data = await audio.read()
    if not data:
        raise HTTPException(400, "Leere Audiodatei")
    suffix = Path(audio.filename or "").suffix or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        model = _get_model()
        segments, info = model.transcribe(
            tmp_path,
            language="de",
            vad_filter=True,
            beam_size=1,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "duration": getattr(info, "duration", None)}
    except Exception as e:
        raise HTTPException(500, f"Transkriptionsfehler: {e}")
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass
