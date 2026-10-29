"""CSS selector candidate builder and browser-use custom action.

Layer 1 of the selector validation pipeline: the LLM never constructs
selectors itself — it calls ``resolve_selector(index=N)`` and our code
builds **all** viable CSS selector candidates from the DOM element's
attributes.  When no CSS selector is viable, we fall back to text-based
element identification (tag + textContent).
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
_HASH_CLASS_RE = re.compile(
    r"-(?=[a-zA-Z0-9]*[0-9])(?=[a-zA-Z0-9]*[a-zA-Z])[a-zA-Z0-9]{4,}$"
)

# Hrefs containing record-specific IDs (Salesforce 15/18-char IDs, UUIDs,
# long hex strings).
_RECORD_ID_RE = re.compile(r"[A-Za-z0-9]{15,18}|[0-9a-f]{8}-[0-9a-f]{4}-|[0-9a-f]{12,}")

# ---------------------------------------------------------------------------
# Tailwind / utility class detection
# ---------------------------------------------------------------------------

# Variant prefixes — stripped before checking the base class name.
# Covers responsive (sm:, md:), state (hover:, focus:, disabled:),
# pseudo-element (before:, after:), and arbitrary variants ([&_svg]:).
_TAILWIND_VARIANT_RE = re.compile(
    r"^(?:"
    r"hover|focus|active|visited|disabled|checked|required|invalid|empty"
    r"|first|last|odd|even|only"
    r"|group-hover|group-focus|peer-hover|peer-focus"
    r"|focus-within|focus-visible|placeholder-shown|placeholder"
    r"|dark|light|print|portrait|landscape"
    r"|sm|md|lg|xl|2xl"
    r"|before|after|file|marker|selection|first-line|first-letter"
    r"|aria-\w+|data-\w+"
    r"|\[[^\]]+\]"  # arbitrary variants like [&_svg]
    r"):"
)

# Prefix-based patterns: catches gap-2, h-10, bg-primary, text-sm,
# border-input, p-4, mx-auto, rounded-xl, etc.
_TAILWIND_PREFIX_RE = re.compile(
    r"^(?:"
    # Spacing: p-4, px-2, m-auto, gap-1.5, space-x-2
    r"[pm][xytblrse]?-|gap-|space-[xy]-"
    # Sizing: w-full, h-10, min-w-0, max-h-screen, size-6
    r"|(?:min-|max-)?[wh]-|size-"
    # Colors / backgrounds: bg-primary, text-muted-foreground, from-blue-500
    r"|bg-|text-|from-|via-|to-"
    # Typography: font-bold, leading-6, tracking-wide
    r"|font-|leading-|tracking-"
    # Borders / rounding / outline / ring
    r"|border-|rounded-|ring-|outline-"
    # Layout positioning: z-10, inset-0, top-4
    r"|z-|inset-|top-|right-|bottom-|left-|start-|end-"
    # Flex / grid: flex-1, basis-0, grid-cols-3, col-span-2, shrink-0, grow-0
    r"|flex-|basis-|order-|shrink-|grow-|grid-cols-|col-span-|row-span-|auto-cols-|auto-rows-"
    # Effects: opacity-50, shadow-md, blur-sm
    r"|opacity-|shadow-|blur-|brightness-|contrast-|backdrop-"
    # Transforms / transitions: duration-200, translate-x-1, transition-colors
    r"|duration-|delay-|ease-|translate-[xy]-|rotate-|scale-|skew-|transition-"
    # Interaction: cursor-pointer, pointer-events-none, scroll-smooth
    r"|cursor-|pointer-events-|select-|scroll-|snap-|touch-"
    # Misc
    r"|aspect-|columns-|divide-[xy]-|place-|accent-|caret-|will-change-"
    r"|decoration-|underline-offset-|line-clamp-"
    r")"
)

# Single-word utility classes that have no prefix-value pattern.
_UTILITY_CLASSES = frozenset(
    {
        # Layout
        "flex",
        "inline-flex",
        "block",
        "inline-block",
        "inline",
        "grid",
        "inline-grid",
        "hidden",
        "relative",
        "absolute",
        "fixed",
        "sticky",
        "static",
        "contents",
        "flow-root",
        "table",
        "inline-table",
        # Flexbox / grid
        "justify-center",
        "justify-between",
        "justify-start",
        "justify-end",
        "justify-around",
        "justify-evenly",
        "items-center",
        "items-start",
        "items-end",
        "items-stretch",
        "items-baseline",
        "self-center",
        "self-start",
        "self-end",
        "self-auto",
        "gap",
        "grow",
        "shrink",
        # Sizing
        "w-full",
        "h-full",
        "w-auto",
        "h-auto",
        "min-w-0",
        "min-h-0",
        "max-w-full",
        "max-h-full",
        "overflow-hidden",
        "overflow-auto",
        "overflow-scroll",
        "overflow-visible",
        # Text
        "truncate",
        "text-left",
        "text-center",
        "text-right",
        "text-justify",
        "uppercase",
        "lowercase",
        "capitalize",
        "normal-case",
        "italic",
        "not-italic",
        "antialiased",
        "subpixel-antialiased",
        "whitespace-nowrap",
        "whitespace-normal",
        "whitespace-pre",
        "break-words",
        "break-all",
        "break-normal",
        # Borders / rounding
        "rounded",
        "rounded-full",
        "rounded-lg",
        "rounded-md",
        "rounded-sm",
        "rounded-xl",
        "rounded-none",
        "border",
        "border-0",
        "border-none",
        "outline-none",
        # Effects (single-word)
        "shadow",
        "ring",
        # Misc Tailwind
        "cursor-pointer",
        "pointer-events-none",
        "pointer-events-auto",
        "select-none",
        "select-all",
        "select-text",
        "transition",
        "transition-all",
        "transition-none",
        "opacity-0",
        "opacity-100",
        "visible",
        "invisible",
        "sr-only",
        "resize",
        "resize-none",
        # SLDS base classes
        "slds-button",
        "slds-input",
        "slds-select",
        "slds-textarea",
        "slds-card",
        "slds-modal",
        "slds-form-element",
        # Generic layout names (not component-specific)
        "container",
        "wrapper",
        "content",
        "inner",
        "outer",
        # shadcn/Radix common
        "peer",
        "group",
    }
)


def _strip_variants(cls: str) -> str:
    """Strip all Tailwind variant prefixes (``hover:``, ``md:``, ``[&_svg]:``…)."""
    while _TAILWIND_VARIANT_RE.match(cls):
        cls = _TAILWIND_VARIANT_RE.sub("", cls, count=1)
    return cls


def _is_utility_class(cls: str) -> bool:
    """Return True if *cls* is a CSS utility / Tailwind class."""
    # Any class containing ":" is a Tailwind variant (hover:, data-[disabled]:, etc.)
    # Standard CSS class names never contain colons.
    if ":" in cls:
        return True

    # Strip variant prefixes: hover:bg-accent → bg-accent
    base = _strip_variants(cls)
    # Strip opacity modifier: bg-accent/50 → bg-accent
    base = base.split("/")[0]

    if base in _UTILITY_CLASSES:
        return True
    if _TAILWIND_PREFIX_RE.match(base):
        return True
    return False


def _has_hash_segment(cls: str) -> bool:
    """Return True if any hyphen-delimited segment looks like a short hash."""
    for seg in cls.split("-"):
        if (
            1 <= len(seg) <= 6
            and any(c.isdigit() for c in seg)
            and any(c.isalpha() for c in seg)
        ):
            return True
    return False


def _is_stable_id(value: str) -> bool:
    """Return True if *value* looks like a hand-written, stable HTML id."""
    if not value:
        return False
    return _DYNAMIC_ID_RE.search(value) is None


def _is_semantic_class(cls: str) -> bool:
    """Return True if *cls* looks like a human-authored semantic class name."""
    if not cls:
        return False
    if _is_utility_class(cls):
        return False
    if _HASH_CLASS_RE.search(cls):
        return False
    if _has_hash_segment(cls):
        return False
    if re.fullmatch(r"[a-f0-9]{6,}", cls):
        return False
    return True


def _css_escape(value: str) -> str:
    """Minimally escape a value for use inside a CSS attribute selector."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# Core builder — multi-candidate
# ---------------------------------------------------------------------------


def build_selector_candidates(
    element: EnhancedDOMTreeNode,
) -> list[tuple[str, str]]:
    """Build ALL viable CSS selector candidates for *element*.

    Returns a list of ``(label, selector)`` tuples, ordered from most
    reliable to least reliable.  An empty list means no safe CSS selector
    could be derived from the element's attributes.
    """
    candidates: list[tuple[str, str]] = []
    attrs = element.attributes or {}
    tag = element.tag_name

    # 1. Stable #id
    el_id = attrs.get("id", "")
    if el_id and _is_stable_id(el_id):
        candidates.append(("Stable ID", f"#{_css_escape(el_id)}"))

    # 2. data-testid
    testid = attrs.get("data-testid", "")
    if testid:
        candidates.append(("data-testid", f'[data-testid="{_css_escape(testid)}"]'))

    # 3. aria-label
    aria_label = attrs.get("aria-label", "")
    if aria_label:
        candidates.append(("aria-label", f'[aria-label="{_css_escape(aria_label)}"]'))

    # 4. Links — a[href="…"]
    href = attrs.get("href", "")
    if tag == "a" and href and href != "#" and not href.startswith("javascript:"):
        if not _RECORD_ID_RE.search(href):
            candidates.append(("Link href", f'a[href="{_css_escape(href)}"]'))

    # 5. Inputs — input[name="…"]
    name = attrs.get("name", "")
    if tag == "input" and name:
        candidates.append(("Input name", f'input[name="{_css_escape(name)}"]'))

    # 6. Named buttons — button[name="…"]
    if tag == "button" and name:
        candidates.append(("Button name", f'button[name="{_css_escape(name)}"]'))

    # 7. Submit buttons
    if tag == "button" and attrs.get("type", "").lower() == "submit":
        candidates.append(("Submit button", 'button[type="submit"]'))

    # 8. Title attribute
    title = attrs.get("title", "")
    if title:
        candidates.append(("Title attribute", f'{tag}[title="{_css_escape(title)}"]'))

    # 9. role + aria-label combo
    role = attrs.get("role", "")
    if role and aria_label:
        candidates.append(
            (
                "Role + aria-label",
                f'[role="{_css_escape(role)}"][aria-label="{_css_escape(aria_label)}"]',
            )
        )

    # 10. Semantic class names — include ALL that pass the filter
    classes = attrs.get("class", "").split()
    for cls in classes:
        if _is_semantic_class(cls):
            candidates.append(("Semantic class", f"{tag}.{cls}"))

    return candidates


def build_stable_selector(element: EnhancedDOMTreeNode) -> str | None:
    """Return the single best selector for *element* (top candidate).

    Convenience wrapper over :func:`build_selector_candidates` for code
    that only needs one selector.
    """
    candidates = build_selector_candidates(element)
    return candidates[0][1] if candidates else None


# ---------------------------------------------------------------------------
# browser-use custom action
# ---------------------------------------------------------------------------


class ResolveSelectorParams(BaseModel):
    index: int = Field(
        description="Element index from the browser state (the [N] prefix)"
    )
    workflow_name: str = Field(description="Name of the workflow this step belongs to")
    title: str = Field(description="Short title for this step (2-5 words)")
    description: str = Field(
        description="One sentence describing what the user should do"
    )
    side: str = Field(
        default="bottom",
        description='Tooltip placement: "top", "bottom", "left", or "right"',
    )


def register_resolve_selector(tools: Tools) -> None:
    """Register the ``resolve_selector`` action on *tools*."""

    @tools.action(
        "Look up the element at the given browser-state index and return one "
        "or more CSS selector candidates.  If no CSS selector is viable, a "
        "text-based fallback is returned instead.  You MUST call this for "
        "every workflow step instead of writing selectors yourself.",
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

        candidates = build_selector_candidates(element)
        tag = element.tag_name
        meta = (
            f"workflow_name={params.workflow_name!r}, "
            f"title={params.title!r}, "
            f"description={params.description!r}, "
            f"side={params.side!r}"
        )

        # --- CSS candidates available ---
        if candidates:
            if len(candidates) == 1:
                label, selector = candidates[0]
                logger.info(
                    "resolve_selector index=%d → %s [%s] (workflow=%r, title=%r)",
                    params.index,
                    selector,
                    label,
                    params.workflow_name,
                    params.title,
                )
                return ActionResult(
                    extracted_content=(
                        f"Resolved selector for index {params.index}: "
                        f"{selector}\n"
                        f"Use this as the `element` value in your output "
                        f"JSON.\n{meta}"
                    ),
                )

            # Multiple candidates
            lines = [
                f"Selector candidates for element at index {params.index} (best first):"
            ]
            for i, (label, selector) in enumerate(candidates, 1):
                marker = " ← RECOMMENDED" if i == 1 else ""
                lines.append(f"  {i}. {selector}  ({label}){marker}")
            lines.append("")
            lines.append(
                "Pick the most specific and meaningful selector. "
                "Prefer attribute-based selectors (aria-label, data-testid, "
                "name, title, href) over class-based ones. "
                "Use your chosen selector as the `element` value in your "
                "output JSON."
            )
            lines.append(meta)

            logger.info(
                "resolve_selector index=%d → %d candidates: %s (workflow=%r, title=%r)",
                params.index,
                len(candidates),
                [s for _, s in candidates],
                params.workflow_name,
                params.title,
            )
            return ActionResult(extracted_content="\n".join(lines))

        # --- No CSS candidates — try text-based fallback ---
        raw_text = element.get_all_children_text()
        # Use only the first line — child nodes are joined with \n,
        # and multi-line text won't match reliably via textContent.includes().
        text = raw_text.split("\n")[0].strip() if raw_text else ""
        if text and len(text) <= 80:
            logger.info(
                "resolve_selector index=%d → text fallback: "
                "tag=%r text=%r (workflow=%r, title=%r)",
                params.index,
                tag,
                text,
                params.workflow_name,
                params.title,
            )
            return ActionResult(
                extracted_content=(
                    f"No CSS selector available for element at index "
                    f"{params.index}.\n"
                    f'Text-based fallback: set `element` to "{tag}" '
                    f'and `text` to "{text}" in your output JSON.\n'
                    f"The frontend will locate the element by matching "
                    f"the tag and text content.\n{meta}"
                ),
            )

        # --- Nothing works ---
        return ActionResult(
            error=(
                f"Could not identify element at index {params.index} "
                f"({tag}). It has no usable attributes, semantic classes, "
                f"or text content. Pick a different element."
            ),
        )
