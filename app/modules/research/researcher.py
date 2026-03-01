import json
import logging
import re

import httpx
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import Settings
from app.modules.research.models import ResearchContext

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a UX expert. Given a user goal and a website URL, describe how that workflow \
typically works ONLY if you are confident you know this product well.

Rules:
- If you do NOT know the product or are unsure about the exact UI, return an empty steps list: \
{"description": "", "steps": []}
- NEVER RESPOND WITH A SINGLE TOKEN IF YOU ARE NOT CONFIDENT YOU KNOW THE PRODUCT WELL (DO NOT HALLUCINATE)
- Do NOT guess or hallucinate UI elements, button names, or navigation paths.
- Only provide steps if you have real knowledge of the product's interface.
- Steps should use built-in UI navigation (tabs, sidebar, menus) — never search bars or shortcuts.

Respond ONLY with a JSON object — no markdown, no explanation — in this exact shape:
{"description": "...", "steps": ["step 1", "step 2", ...]}\
"""

_MINIMAX_API_URL = "https://api.minimaxi.chat/v1/text/chatcompletion_v2"


def _get_research_llm(settings: Settings):
    logger.info("Initialising research LLM: provider=%r model=%r", settings.RESEARCH_PROVIDER, settings.resolved_research_model)

    if settings.RESEARCH_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.resolved_research_model,
            google_api_key=settings.GEMINI_API_KEY,
        )

    if settings.RESEARCH_PROVIDER == "minimax":
        # Return None — MiniMax is handled via direct HTTP call in
        # research_workflow to work around langchain-community's broken
        # error handling (choices=null on API errors is not caught).
        return None

    raise ValueError(f"Unknown research provider: {settings.RESEARCH_PROVIDER!r}")


async def _minimax_chat(messages: list[dict], settings: Settings) -> str:
    """Call the MiniMax chat API directly, with proper error handling."""
    payload = {
        "model": settings.resolved_research_model,
        "messages": messages,
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

    # MiniMax returns HTTP 200 even on errors; the real status lives in base_resp.
    base_resp = body.get("base_resp", {})
    status_code = base_resp.get("status_code", 0)
    if status_code != 0:
        status_msg = base_resp.get("status_msg", "unknown error")
        raise RuntimeError(
            f"MiniMax API error {status_code}: {status_msg}"
        )

    choices = body.get("choices")
    if not choices:
        raise RuntimeError(f"MiniMax returned no choices. Full response: {body}")

    return choices[0]["message"]["content"]


def _parse_json(text: str) -> dict:
    """Extract and parse the first JSON object from a model response."""
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1)
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError(f"No JSON object found in research response: {text!r}")
    return json.loads(match.group())


async def research_workflow(
    url: str,
    query: str,
    settings: Settings,
    cookies_file: str | None = None,
) -> ResearchContext:
    llm = _get_research_llm(settings)

    user_content = f"Website: {url}\nUser goal: {query}"

    logger.info("Calling research LLM (provider=%r)...", settings.RESEARCH_PROVIDER)
    try:
        if settings.RESEARCH_PROVIDER == "minimax":
            raw = await _minimax_chat(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                settings,
            )
        else:
            messages = [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
            response = await llm.ainvoke(messages)
            raw = response.content
    except Exception:
        logger.exception("research LLM invoke failed")
        raise

    logger.info("Research LLM raw content: %r", raw[:200])
    data = _parse_json(raw)
    logger.info("Parsed research context: description=%r steps=%d", data.get("description", "")[:80], len(data.get("steps", [])))
    return ResearchContext.model_validate(data)
