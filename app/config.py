from typing import Literal

from pydantic_settings import BaseSettings
from functools import lru_cache


_DEFAULT_MODELS = {
    "browser-use": "browser-use/browser-use-default",
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-0",
    "gemini": "gemini-flash-latest",
}

_DEFAULT_RESEARCH_MODELS = {
    "gemini": "gemini-2.0-flash",
    "minimax": "MiniMax-Text-01",
}


class Settings(BaseSettings):
    LLM_PROVIDER: Literal["browser-use", "openai", "anthropic", "gemini"] = (
        "browser-use"
    )
    LLM_MODEL: str | None = None

    RESEARCH_PROVIDER: Literal["gemini", "minimax"] = "gemini"
    RESEARCH_MODEL: str | None = None

    BROWSER_USE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    MONGODB_URI: str = ""
    MINIMAX_API_KEY: str = ""
    MINIMAX_GROUP_ID: str = ""

    model_config = {"env_file": ".env"}

    @property
    def resolved_model(self) -> str:
        return self.LLM_MODEL or _DEFAULT_MODELS[self.LLM_PROVIDER]

    @property
    def resolved_research_model(self) -> str:
        return self.RESEARCH_MODEL or _DEFAULT_RESEARCH_MODELS[self.RESEARCH_PROVIDER]


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    return settings
