from __future__ import annotations

import re

from openai import OpenAI

from backend.config import Settings
from backend.llm.base import BaseLLMProvider, SQLGenerationResult


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, settings: Settings) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")

        client_kwargs: dict[str, str] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url

        self._client = OpenAI(**client_kwargs)
        self._model = settings.llm_model
        self._timeout = settings.llm_timeout_seconds

    def generate_sql(self, system_prompt: str, user_prompt: str) -> SQLGenerationResult:
        response = self._client.chat.completions.create(
            model=self._model,
            timeout=self._timeout,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content or ""
        return SQLGenerationResult(
            sql=extract_sql(content),
            provider="openai",
            model=self._model,
            raw_response=content,
        )


def extract_sql(content: str) -> str:
    code_block = re.search(r"```sql\s*(.*?)```", content, re.IGNORECASE | re.DOTALL)
    if code_block:
        return code_block.group(1).strip()

    select_match = re.search(
        r"((?:WITH|SELECT)\b.*)$", content, re.IGNORECASE | re.DOTALL
    )
    if select_match:
        return select_match.group(1).strip()

    raise ValueError("Model did not return SQL in the expected format.")
