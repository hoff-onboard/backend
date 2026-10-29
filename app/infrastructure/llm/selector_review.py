"""Post-extraction selector review.

Uses the research LLM to classify each step's selector as structural
(same for all users) or dynamic (contains instance-specific data like
a person's name or record ID). Dynamic steps get flagged so the frontend
can present them differently (e.g. "Select any lead from the list").
"""

import json
import logging

from app.config import Settings
from app.domain.workflows.models import Step, Workflow
from app.infrastructure.llm.factory import parse_json_reply, research_chat

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


class LLMSelectorReviewer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def review(self, workflow: Workflow) -> Workflow:
        """Classify each step's selector and flag dynamic ones; on failure keep the workflow unchanged."""
        steps_payload = [
            {"index": i, "selector": s.element, "title": s.title, "description": s.description}
            for i, s in enumerate(workflow.steps)
        ]
        user_content = f"Workflow: {workflow.name}\n\nSteps:\n{json.dumps(steps_payload, indent=2)}"
        logger.info("Reviewing %d selectors for workflow=%r", len(workflow.steps), workflow.name)

        try:
            raw = await research_chat(self._settings, _SYSTEM_PROMPT, user_content)
            classifications = parse_json_reply(raw)
            review_map: dict[int, dict] = {c["index"]: c for c in classifications}
        except Exception:
            logger.exception("Selector review failed — keeping all steps as-is")
            return workflow

        updated_steps: list[Step] = []
        for i, step in enumerate(workflow.steps):
            review = review_map.get(i)
            if review and review.get("classification") == "dynamic":
                generic_desc = review.get("generic_description") or step.description
                updated_steps.append(step.model_copy(update={"dynamic": True, "description": generic_desc}))
                logger.info("Flagged step %d %r as dynamic (selector=%r)", i, step.title, step.element)
            else:
                updated_steps.append(step)

        return workflow.model_copy(update={"steps": updated_steps})
