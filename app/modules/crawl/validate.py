"""Post-processing validation for workflow selectors.

Layer 3 of the selector validation pipeline: after the agent returns its
``WorkflowsResponse``, we validate each selector's CSS syntax and
(best-effort) check DOM presence via the still-open browser session.
"""

from __future__ import annotations

import logging
import re

from browser_use import BrowserSession

from app.modules.crawl.models import Step, Workflow, WorkflowsResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CSS selector syntax validation
# ---------------------------------------------------------------------------

# Patterns that are always invalid in a standard CSS selector
_BAD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Playwright pseudo-selector", re.compile(r":has-text\(|:text\(|>>|:visible", re.IGNORECASE)),
    ("Positional selector", re.compile(r":nth-child\(|:nth-of-type\(|:first-child|:last-child", re.IGNORECASE)),
    ("Dynamic ID", re.compile(r"\[id=['\"]?[:_]?[A-Za-z0-9_]*[:_][A-Za-z0-9_]{3,}['\"]?\]")),
    ("React-style ID", re.compile(r"\[id=['\"]?:r\d+:['\"]?\]")),
    ("Hash class name", re.compile(r"\.[a-zA-Z][\w]*-[a-zA-Z][\w]*-[a-zA-Z0-9]{4,}")),
]


def _has_bad_pattern(selector: str) -> str | None:
    """Return a description of the first bad pattern found, or None."""
    for label, pattern in _BAD_PATTERNS:
        if pattern.search(selector):
            return label
    return None


def _is_syntactically_valid(selector: str) -> bool:
    """Best-effort CSS selector syntax check.

    We try to catch obvious garbage without pulling in a full CSS parser.
    The real validation happens when we run ``document.querySelector`` in the
    browser.
    """
    if not selector or not selector.strip():
        return False

    # Must not contain unmatched quotes or brackets
    if selector.count('"') % 2 != 0:
        return False
    if selector.count("'") % 2 != 0:
        return False
    if selector.count("[") != selector.count("]"):
        return False
    if selector.count("(") != selector.count(")"):
        return False

    return True


# ---------------------------------------------------------------------------
# DOM presence check
# ---------------------------------------------------------------------------


async def _selector_exists_in_dom(
    browser_session: BrowserSession,
    selector: str,
) -> bool | None:
    """Check if *selector* matches at least one element in the current page.

    Returns ``True``/``False``, or ``None`` if the check itself failed
    (e.g. the page navigated away).
    """
    try:
        page = await browser_session.get_current_page()
        result = await page.evaluate(
            "(sel) => document.querySelector(sel) !== null",
            selector,
        )
        return bool(result)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def validate_workflows(
    response: WorkflowsResponse,
    browser_session: BrowserSession | None = None,
) -> WorkflowsResponse:
    """Validate every selector in *response* and drop bad steps/workflows.

    1. Reject selectors that contain known bad patterns.
    2. Reject selectors with obviously broken syntax.
    3. If *browser_session* is available, run ``document.querySelector`` for
       each remaining selector.  Steps whose selector has valid syntax but
       no DOM match are **kept** (the page state may have changed).  Steps
       with a selector that throws a JS error are dropped.
    4. Workflows with zero remaining steps are dropped entirely.
    """
    validated_workflows: list[Workflow] = []

    for wf in response.workflows:
        valid_steps: list[Step] = []

        for step in wf.steps:
            selector = step.element

            # --- bad pattern check ---
            bad = _has_bad_pattern(selector)
            if bad:
                logger.warning(
                    "Dropping step %r: %s in selector %r",
                    step.title,
                    bad,
                    selector,
                )
                continue

            # --- basic syntax check ---
            if not _is_syntactically_valid(selector):
                logger.warning(
                    "Dropping step %r: invalid CSS syntax in %r",
                    step.title,
                    selector,
                )
                continue

            # --- DOM presence check (best-effort) ---
            if browser_session is not None:
                exists = await _selector_exists_in_dom(browser_session, selector)
                if exists is None:
                    logger.warning(
                        "Could not verify DOM presence for step %r selector %r "
                        "(page may have navigated away); keeping step",
                        step.title,
                        selector,
                    )
                elif exists is False:
                    logger.info(
                        "Step %r selector %r not found in current DOM; "
                        "keeping step (page state may have changed)",
                        step.title,
                        selector,
                    )
                # exists is True — great, keep it

            valid_steps.append(step)

        if not valid_steps:
            logger.warning(
                "Dropping workflow %r: no valid steps remaining",
                wf.name,
            )
            continue

        validated_workflows.append(
            Workflow(
                name=wf.name,
                description=wf.description,
                steps=valid_steps,
            )
        )

    if not validated_workflows:
        logger.error(
            "All workflows dropped during validation! "
            "Returning original response to avoid empty result."
        )
        return response

    return WorkflowsResponse(workflows=validated_workflows)
