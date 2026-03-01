from langchain_core.language_models.chat_models import BaseChatModel

from app.config import Settings


def get_llm(settings: Settings) -> BaseChatModel:
    provider = settings.LLM_PROVIDER
    model = settings.resolved_model

    if provider == "browser-use":
        from browser_use import ChatBrowserUse

        return ChatBrowserUse()

    if provider == "openai":
        from browser_use import ChatOpenAI

        return ChatOpenAI(model=model)

    if provider == "anthropic":
        from browser_use import ChatAnthropic

        return ChatAnthropic(model=model)

    raise ValueError(f"Unknown LLM provider: {provider}")
