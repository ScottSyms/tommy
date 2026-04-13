from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Any

from faster_whisper import WhisperModel


MODEL_NAME = "small.en"
INITIAL_PROMPT = (
    "This is a maritime common operating picture discussion about AIS vessels, "
    "MMSI, Halifax, destinations, latitude, longitude, knots, headings, and courses."
)
_MODEL: WhisperModel | None = None
_MODEL_LOCK = Lock()


class TranscriptionError(RuntimeError):
    pass


def _get_model() -> WhisperModel:
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                _MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
    return _MODEL


def transcribe_audio(audio_bytes: bytes, suffix: str = ".webm") -> dict[str, Any]:
    if not audio_bytes:
        return {"transcript": "", "language": "unknown", "confidence": 0.0}

    model = _get_model()

    try:
        with NamedTemporaryFile(suffix=suffix, delete=False) as temp_audio:
            temp_audio.write(audio_bytes)
            temp_path = Path(temp_audio.name)

        segments, info = model.transcribe(
            str(temp_path),
            vad_filter=True,
            language="en",
            beam_size=5,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=INITIAL_PROMPT,
        )
        transcript_parts: list[str] = []
        segment_scores: list[float] = []

        for segment in segments:
            transcript_parts.append(segment.text.strip())
            avg_log_prob = getattr(segment, "avg_logprob", None)
            if avg_log_prob is not None:
                segment_scores.append(
                    max(0.0, min(1.0, float(pow(2.718281828, avg_log_prob))))
                )

        transcript = " ".join(part for part in transcript_parts if part).strip()
        confidence = (
            round(sum(segment_scores) / len(segment_scores), 3)
            if segment_scores
            else 0.0
        )
        return {
            "transcript": transcript,
            "language": getattr(info, "language", "unknown"),
            "confidence": confidence,
        }
    except Exception as exc:  # pragma: no cover - external decoder/model failures
        raise TranscriptionError("Unable to transcribe the provided audio.") from exc
    finally:
        temp_path = locals().get("temp_path")
        if temp_path and temp_path.exists():
            temp_path.unlink()
