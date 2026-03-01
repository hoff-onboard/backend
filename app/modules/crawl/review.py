"""Post-extraction selector review.

Uses the research LLM to classify each step's selector as structural
(same for all users) or dynamic (contains instance-specific data like
a person's name or record ID). Dynamic steps get flagged so the frontend
can present them differently (e.g. "Select any lead from the list").
"""

import json
import logging
import re

from app.config import Settings
from app.modules.crawl.models import Step, Workflow

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a CSS selector analyst. You will receive a list of workflow steps, each \
with a CSS selector. Your job is to classify each selector as either:

- "structural": The selector targets a UI element that is the same for every user \
(buttons, tabs, menu items, form fields). Examples: `button[name="Convert"]`, \
`a[href="/lightning/o/Lead/home"]`, `#repository-name-input`.
- "dynamic": The selector contains user-specific or instance-specific data that \
would differ for other users (person names, record IDs, specific data values). \
Examples: `a[title="Jean Dow"]`, `a[href="/lightning/r/00QWV000009uxGM2AY/view"]`, \
`#combobox-button-487`.

For dynamic selectors, provide a `generic_description` that describes what the user \
should do in general terms (e.g. "Select a lead from the list").

Respond ONLY with a JSON array — no markdown, no explanation. Each item:
{"index": 0, "classification": "structural" | "dynamic", "generic_description": "..." | null}\
"""


def _parse_json_array(text: str) -> list[dict]:
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1)
    match = re.search(r"\[[\s\S]*\]", text)
    if not match:
        raise ValueError(f"No JSON array found in review response: {text!r}")
    return json.loads(match.group())


async def review_selectors(
    workflow: Workflow,
    settings: Settings,
) -> Workflow:
    """Classify each step's selector and flag dynamic ones."""
    steps_payload = [
        {"index": i, "selector": s.element, "title": s.title, "description": s.description}
        for i, s in enumerate(workflow.steps)
    ]

    user_content = (
        f"Workflow: {workflow.name}\n\n"
        f"Steps:\n{json.dumps(steps_payload, indent=2)}"
    )

    logger.info("Reviewing %d selectors for workflow=%r", len(workflow.steps), workflow.name)

    try:
        raw = await _call_research_llm(settings, user_content)
        classifications = _parse_json_array(raw)
    except Exception:
        logger.exception("Selector review failed — keeping all steps as-is")
        return workflow

    # Build a lookup: index -> classification info
    review_map: dict[int, dict] = {c["index"]: c for c in classifications}

    updated_steps: list[Step] = []
    for i, step in enumerate(workflow.steps):
        review = review_map.get(i)
        if review and review.get("classification") == "dynamic":
            generic_desc = review.get("generic_description") or step.description
            updated_steps.append(step.model_copy(update={
                "dynamic": True,
                "description": generic_desc,
            }))
            logger.info(
                "Flagged step %d %r as dynamic (selector=%r)",
                i, step.title, step.element,
            )
        else:
            updated_steps.append(step)

    return workflow.model_copy(update={"steps": updated_steps})


async def _call_research_llm(settings: Settings, user_content: str) -> str:
    if settings.RESEARCH_PROVIDER == "minimax":
        from app.modules.research.researcher import _minimax_chat

        return await _minimax_chat(
            [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            settings,
        )

    if settings.RESEARCH_PROVIDER == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatGoogleGenerativeAI(
            model=settings.resolved_research_model,
            google_api_key=settings.GEMINI_API_KEY,
        )
        response = await llm.ainvoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        return response.content

    raise ValueError(f"Unknown research provider: {settings.RESEARCH_PROVIDER!r}")
