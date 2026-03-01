"""Deterministic CSS selector builder and browser-use custom action.

Layer 1 of the selector validation pipeline: the LLM never constructs
selectors itself — it calls ``resolve_selector(index=N)`` and our code
builds a stable CSS selector from the DOM element's attributes.
"""

from __future__ import annotations

import logging
import re

from browser_use import ActionResult, Tools
from browser_use.dom.views import EnhancedDOMTreeNode
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Patterns used to reject unstable attribute values
# ---------------------------------------------------------------------------

# IDs that look auto-generated: leading underscore/colon followed by short
# random-looking alphanumeric runs, or React-style `:r6:` IDs.
_DYNAMIC_ID_RE = re.compile(r"(^[:_]|[:_][A-Za-z0-9_]{3,}|^:r\d+:$)")

# Class names with a hash/random suffix (e.g. `prc-Button-1CtM6`, `css-1a2b3c`).
# Matches a trailing segment that mixes letters AND digits (indicating a hash).
_HASH_CLASS_RE = re.compile(r"-(?=[a-zA-Z0-9]*[0-9])(?=[a-zA-Z0-9]*[a-zA-Z])[a-zA-Z0-9]{4,}$")


def _is_stable_id(value: str) -> bool:
    """Return True if *value* looks like a hand-written, stable HTML id."""
    if not value:
        return False
    return _DYNAMIC_ID_RE.search(value) is None


def _is_semantic_class(cls: str) -> bool:
    """Return True if *cls* looks like a human-authored semantic class name."""
    if not cls:
        return False
    # Reject classes that end with a hash-like suffix (mixed letters + digits)
    if _HASH_CLASS_RE.search(cls):
        return False
    # Reject classes that are entirely hex/random (e.g. `a1b2c3d4`)
    if re.fullmatch(r"[a-f0-9]{6,}", cls):
        return False
    return True


def _css_escape(value: str) -> str:
    """Minimally escape a value for use inside a CSS attribute selector."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------


def build_stable_selector(element: EnhancedDOMTreeNode) -> str | None:
    """Build a deterministic CSS selector for *element*.

    Uses a strict priority cascade — returns the first match:

    1. ``#id``                       (stable IDs only)
    2. ``[data-testid="…"]``
    3. ``[aria-label="…"]``
    4. ``a[href="…"]``               (for links)
    5. ``input[name="…"]``           (for inputs)
    6. ``button[type="submit"]``     (for submit buttons)
    7. ``[role="…"][aria-label="…"]`` (combo)
    8. ``tag.semantic-class``        (semantic classes only)
    9. ``None``                      (no safe selector found)
    """
    attrs = element.attributes or {}
    tag = element.tag_name  # lowercase

    # 1. Stable #id
    el_id = attrs.get("id", "")
    if el_id and _is_stable_id(el_id):
        return f"#{_css_escape(el_id)}"

    # 2. data-testid
    testid = attrs.get("data-testid", "")
    if testid:
        return f'[data-testid="{_css_escape(testid)}"]'

    # 3. aria-label
    aria_label = attrs.get("aria-label", "")
    if aria_label:
        return f'[aria-label="{_css_escape(aria_label)}"]'

    # 4. Links — a[href="…"]
    href = attrs.get("href", "")
    if tag == "a" and href and href != "#":
        return f'a[href="{_css_escape(href)}"]'

    # 5. Inputs — input[name="…"]
    name = attrs.get("name", "")
    if tag == "input" and name:
        return f'input[name="{_css_escape(name)}"]'

    # 6. Submit buttons
    if tag == "button" and attrs.get("type", "").lower() == "submit":
        return 'button[type="submit"]'

    # 7. role + aria-label combo (aria-label checked again with role)
    role = attrs.get("role", "")
    if role and aria_label:
        return f'[role="{_css_escape(role)}"][aria-label="{_css_escape(aria_label)}"]'

    # 8. Semantic class name
    classes = attrs.get("class", "").split()
    for cls in classes:
        if _is_semantic_class(cls):
            return f"{tag}.{cls}"

    # 9. No safe selector
    return None


# ---------------------------------------------------------------------------
# browser-use custom action
# ---------------------------------------------------------------------------


class ResolveSelectorParams(BaseModel):
    index: int = Field(description="Element index from the browser state (the [N] prefix)")
    workflow_name: str = Field(description="Name of the workflow this step belongs to")
    title: str = Field(description="Short title for this step (2-5 words)")
    description: str = Field(description="One sentence describing what the user should do")
    side: str = Field(
        default="bottom",
        description='Tooltip placement: "top", "bottom", "left", or "right"',
    )


def register_resolve_selector(tools: Tools) -> None:
    """Register the ``resolve_selector`` action on *tools*."""

    @tools.action(
        "Look up the element at the given browser-state index and return a "
        "stable CSS selector for it. You MUST call this for every workflow "
        "step instead of writing selectors yourself.",
        param_model=ResolveSelectorParams,
    )
    async def resolve_selector(
        params: ResolveSelectorParams,
        browser_session,
    ) -> ActionResult:
        element = await browser_session.get_dom_element_by_index(params.index)
        if element is None:
            return ActionResult(
                error=(
                    f"No element found at index {params.index}. "
                    "Check the browser state and pick a valid index."
                ),
            )

        selector = build_stable_selector(element)
        if selector is None:
            return ActionResult(
                error=(
                    f"Could not build a stable selector for element at index "
                    f"{params.index} ({element.tag_name}). The element lacks "
                    "a usable id, data-testid, aria-label, href, or semantic "
                    "class. Pick a different element."
                ),
            )

        logger.info(
            "resolve_selector index=%d → %s (workflow=%r, title=%r)",
            params.index,
            selector,
            params.workflow_name,
            params.title,
        )

        return ActionResult(
            extracted_content=(
                f"Resolved selector for index {params.index}: {selector}\n"
                f"Use this as the `element` value in your output JSON.\n"
                f"workflow_name={params.workflow_name!r}, "
                f"title={params.title!r}, "
                f"description={params.description!r}, "
                f"side={params.side!r}"
            ),
        )
