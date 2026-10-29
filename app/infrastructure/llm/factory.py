"""Model clients chosen by settings: the browser agent's LLM and the research LLM."""

import json
import logging
import re
from typing import Any

import httpx
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings

logger = logging.getLogger(__name__)

_MINIMAX_API_URL = "https://api.minimaxi.chat/v1/text/chatcompletion_v2"


def get_llm(settings: Settings) -> BaseChatModel:
    provider = settings.LLM_PROVIDER
    model = settings.resolved_model

    if provider == "browser-use":
        from browser_use import ChatBrowserUse

        return ChatBrowserUse()

    if provider == "openai":
        from browser_use import ChatOpenAI

        return ChatOpenAI(model=model, api_key=settings.OPENAI_API_KEY)

    if provider == "anthropic":
        from browser_use import ChatAnthropic

        return ChatAnthropic(model=model)

    if provider == "gemini":
        from browser_use import ChatGoogle

        return ChatGoogle(model=model)

    raise ValueError(f"Unknown LLM provider: {provider}")


async def research_chat(settings: Settings, system_prompt: str, user_content: str) -> str:
    """One system + user exchange with the research LLM; returns the reply text."""
    logger.info(
        "Calling research LLM: provider=%r model=%r",
        settings.RESEARCH_PROVIDER,
        settings.resolved_research_model,
    )
    if settings.RESEARCH_PROVIDER == "minimax":
        return await _minimax_chat(settings, system_prompt, user_content)

    response = await _langchain_research_llm(settings).ainvoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
    )
    raw = response.content
    if isinstance(raw, list):  # newer langchain returns content blocks
        raw = "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in raw)
    return raw


def parse_json_reply(text: str) -> Any:
    """First JSON object or array in a model reply, tolerating markdown fences and prose."""
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1)
    match = re.search(r"[\{\[][\s\S]*[\}\]]", text)
    if not match:
        raise ValueError(f"No JSON found in model reply: {text!r}")
    return json.loads(match.group())


def _langchain_research_llm(settings: Settings) -> BaseChatModel:
    if settings.RESEARCH_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.resolved_research_model,
            google_api_key=settings.GEMINI_API_KEY,
        )

    if settings.RESEARCH_PROVIDER == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=settings.resolved_research_model,
            api_key=settings.OPENAI_API_KEY,
        )

    raise ValueError(f"Unknown research provider: {settings.RESEARCH_PROVIDER!r}")


async def _minimax_chat(settings: Settings, system_prompt: str, user_content: str) -> str:
    """Direct HTTP call: langchain-community's MiniMax wrapper doesn't surface API errors."""
    payload = {
        "model": settings.resolved_research_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 1024,
        "temperature": 0.7,
        "top_p": 0.95,
    }
    headers = {
        "Authorization": f"Bearer {settings.MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(_MINIMAX_API_URL, json=payload, headers=headers)
        resp.raise_for_status()

    body = resp.json()
    logger.debug("MiniMax raw response: %s", json.dumps(body, ensure_ascii=False)[:500])

    # MiniMax returns HTTP 200 even on errors; the real status lives in base_resp
    base_resp = body.get("base_resp", {})
    if base_resp.get("status_code", 0) != 0:
        raise RuntimeError(
            f"MiniMax API error {base_resp['status_code']}: {base_resp.get('status_msg', 'unknown error')}"
        )
    choices = body.get("choices")
    if not choices:
        raise RuntimeError(f"MiniMax returned no choices. Full response: {body}")
    return choices[0]["message"]["content"]
