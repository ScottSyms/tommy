from __future__ import annotations

import os
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4.1-mini")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_base_url: str | None = os.getenv("OPENAI_BASE_URL")
    llm_timeout_seconds: float = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
    sql_result_limit: int = int(os.getenv("SQL_RESULT_LIMIT", "50"))
    piper_command: tuple[str, ...] = tuple(
        shlex.split(os.getenv("PIPER_COMMAND", "uv run piper"))
    )
    piper_binary_path: str | None = (
        os.getenv("PIPER_BINARY_PATH")
        or shutil.which("piper")
        or shutil.which("piper-tts")
    )
    piper_model_path: str | None = os.getenv("PIPER_MODEL_PATH")
    piper_config_path: str | None = os.getenv("PIPER_CONFIG_PATH")
    piper_speaker_id: int | None = (
        int(os.getenv("PIPER_SPEAKER_ID")) if os.getenv("PIPER_SPEAKER_ID") else None
    )
    piper_timeout_seconds: float = float(os.getenv("PIPER_TIMEOUT_SECONDS", "20"))


def get_settings() -> Settings:
    return Settings()
