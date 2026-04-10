from __future__ import annotations

from backend.config import get_settings
from backend.llm.base import BaseLLMProvider
from backend.llm.openai_provider import OpenAIProvider


def get_llm_provider() -> BaseLLMProvider:
    settings = get_settings()
    provider_name = settings.llm_provider.lower()

    if provider_name == "openai":
        return OpenAIProvider(settings)

    raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")
