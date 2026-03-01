from typing import Literal

from pydantic_settings import BaseSettings
from functools import lru_cache


_DEFAULT_MODELS = {
    "browser-use": "browser-use/browser-use-default",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-0",
}


class Settings(BaseSettings):
    LLM_PROVIDER: Literal["browser-use", "openai", "anthropic"] = "browser-use"
    LLM_MODEL: str | None = None

    BROWSER_USE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    model_config = {"env_file": ".env"}

    @property
    def resolved_model(self) -> str:
        return self.LLM_MODEL or _DEFAULT_MODELS[self.LLM_PROVIDER]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
