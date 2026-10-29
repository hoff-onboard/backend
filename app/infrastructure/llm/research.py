import logging

from app.config import Settings
from app.domain.research.models import ResearchContext
from app.infrastructure.llm.factory import parse_json_reply, research_chat

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


class LLMResearchProvider:
    """Asks the research LLM how a workflow usually goes, from its knowledge of the product."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def research(self, url: str, query: str, cookies_file: str | None = None) -> ResearchContext:
        raw = await research_chat(self._settings, _SYSTEM_PROMPT, f"Website: {url}\nUser goal: {query}")
        logger.info("Research LLM raw content: %r", raw[:200])
        context = ResearchContext.model_validate(parse_json_reply(raw))
        logger.info(
            "Parsed research context: description=%r steps=%d",
            context.description[:80],
            len(context.steps),
        )
        return context
