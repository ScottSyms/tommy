from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

from backend.config import ROOT_DIR, get_settings


class SpeechSynthesisError(RuntimeError):
    pass


def synthesize_speech(text: str) -> bytes:
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        raise SpeechSynthesisError("No reply text was provided for speech synthesis.")

    settings = get_settings()
    model_path = settings.piper_model_path
    command = list(settings.piper_command)
    if not command:
        binary_path = settings.piper_binary_path
        if not binary_path:
            raise SpeechSynthesisError(
                "Piper is not installed and no Piper command is configured."
            )
        command = [binary_path]

    if not model_path:
        raise SpeechSynthesisError("PIPER_MODEL_PATH is not configured.")

    model = Path(model_path)
    if not model.is_absolute():
        model = ROOT_DIR / model
    if not model.exists():
        raise SpeechSynthesisError(f"Piper model was not found at {model}.")

    config = Path(settings.piper_config_path) if settings.piper_config_path else None
    if config and not config.is_absolute():
        config = ROOT_DIR / config
    if config and not config.exists():
        raise SpeechSynthesisError(f"Piper config was not found at {config}.")

    with NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav:
        output_path = Path(temp_wav.name)

    try:
        command.extend(
            [
                "--model",
                str(model),
                "--output_file",
                str(output_path),
            ]
        )
        if config:
            command.extend(["--config", str(config)])
        if settings.piper_speaker_id is not None:
            command.extend(["--speaker", str(settings.piper_speaker_id)])

        completed = subprocess.run(
            command,
            input=cleaned,
            capture_output=True,
            text=True,
            timeout=settings.piper_timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip() or "Unknown Piper error."
            raise SpeechSynthesisError(f"Piper synthesis failed: {stderr}")

        if not output_path.exists():
            raise SpeechSynthesisError("Piper did not produce an output WAV file.")

        return output_path.read_bytes()
    except subprocess.TimeoutExpired as exc:
        raise SpeechSynthesisError("Piper synthesis timed out.") from exc
    finally:
        if output_path.exists():
            output_path.unlink()
