from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SQLGenerationResult:
    sql: str
    provider: str
    model: str
    raw_response: str


class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_sql(self, system_prompt: str, user_prompt: str) -> SQLGenerationResult:
        raise NotImplementedError
