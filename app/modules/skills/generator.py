"""Generate a SKILLS.md playbook per workflow using an LLM.

Takes already-extracted workflow data (no recrawling) and asks the LLM to
produce a rich, agent-friendly Markdown guide for each workflow.
"""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from app.modules.branding.models import Brand
from app.modules.crawl.models import Workflow

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a technical writer that produces concise SKILLS.md files for browser \
automation agents. Given a structured workflow extracted from a website, you \
generate a Markdown playbook that another browser agent can follow to complete \
the workflow autonomously.

Rules:
- Output ONLY the Markdown content, no preamble or wrapping fences.
- Start with a level-1 heading using the workflow name.
- Include a short "Goal" section (1-2 sentences) explaining what the skill achieves.
- Include a "Prerequisites" section listing anything the agent needs before starting \
(e.g. being on a specific page, being logged in).
- Include a numbered "Steps" section. For each step:
  - State the action clearly as an instruction to a browser agent.
  - Include the CSS selector the agent should target in a `Selector:` line.
  - Note whether the step triggers a navigation in a `Navigates:` line.
- Include a "Brand Context" section with the product's visual tokens so the agent \
can recognise UI elements by style if selectors fail.
- Keep the language direct and imperative — this is a runbook, not documentation.\
"""


def _build_user_prompt(url: str, brand: Brand, workflow: Workflow) -> str:
    domain = urlparse(url).hostname or url

    steps_block = ""
    for i, step in enumerate(workflow.steps, 1):
        steps_block += (
            f"  Step {i}:\n"
            f"    title: {step.title}\n"
            f"    description: {step.description}\n"
            f"    selector: {step.element}\n"
            f"    tooltip_side: {step.side}\n"
            f"    navigates: {step.navigates}\n"
        )

    return (
        f"Website: {url} ({domain})\n\n"
        f"Workflow name: {workflow.name}\n"
        f"Workflow description: {workflow.description}\n\n"
        f"Steps:\n{steps_block}\n"
        f"Brand tokens:\n"
        f"  primary_color: {brand.primary}\n"
        f"  background: {brand.background}\n"
        f"  text_color: {brand.text}\n"
        f"  font_family: {brand.fontFamily}\n"
        f"  border_radius: {brand.borderRadius}\n"
    )


async def generate_skill_md(
    llm: BaseChatModel,
    url: str,
    brand: Brand,
    workflow: Workflow,
) -> str:
    """Use the LLM to generate a SKILLS.md for a single workflow."""
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=_build_user_prompt(url, brand, workflow)),
    ]

    response = await llm.ainvoke(messages)
    return response.content.strip() + "\n"


async def generate_all_skills_md(
    llm: BaseChatModel,
    url: str,
    brand: Brand,
    workflows: list[Workflow],
) -> dict[str, str]:
    """Generate a SKILLS.md for each workflow in parallel.

    Returns a dict mapping workflow name → Markdown content.
    """
    tasks = [
        generate_skill_md(llm, url, brand, wf)
        for wf in workflows
    ]
    results = await asyncio.gather(*tasks)
    return {wf.name: md for wf, md in zip(workflows, results)}
