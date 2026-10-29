"""Selector pipeline rules: layer 1 (candidate filters), layer 2 (Step validator), layer 3 (syntax)."""

import pytest
from pydantic import ValidationError

from app.domain.workflows.models import Step
from app.infrastructure.browser.selector import (
    _is_semantic_class,
    _is_stable_id,
    _is_utility_class,
)
from app.infrastructure.browser.validate import (
    _has_bad_pattern,
    _is_syntactically_valid,
)


@pytest.mark.parametrize("value", ["repository-name-input", "login", "new-issue"])
def test_hand_written_ids_are_stable(value):
    assert _is_stable_id(value)


@pytest.mark.parametrize("value", ["", ":r6:", "_R_5jpb_", "field_abc123"])
def test_generated_ids_are_rejected(value):
    assert not _is_stable_id(value)


@pytest.mark.parametrize("cls", ["flex", "gap-2", "hover:bg-accent", "md:px-4", "bg-primary/50"])
def test_tailwind_utilities_are_detected(cls):
    assert _is_utility_class(cls)


@pytest.mark.parametrize("cls", ["btn-primary", "repo-list", "Header-link"])
def test_semantic_classes_are_kept(cls):
    assert _is_semantic_class(cls)


@pytest.mark.parametrize("cls", ["prc-Button-1CtM6", "css-1a2b3c", "a1b2c3d4", "flex"])
def test_hashed_or_utility_classes_are_dropped(cls):
    assert not _is_semantic_class(cls)


@pytest.mark.parametrize(
    "selector",
    ["button:has-text('Save')", "li:nth-child(2)", "[id=':r6:']", ".prc-Button-1CtM6", "a >> text=New"],
)
def test_step_rejects_unstable_selectors(selector):
    with pytest.raises(ValidationError):
        Step(element=selector, title="t", description="d")
    assert _has_bad_pattern(selector)


def test_step_accepts_attribute_selectors():
    step = Step(element="a[href='/new']", title="t", description="d")
    assert _has_bad_pattern(step.element) is None


@pytest.mark.parametrize("selector,valid", [("a[href='/new']", True), ("a[href='/new'", False), ("a[title=\"x]", False), ("  ", False)])
def test_syntax_check(selector, valid):
    assert _is_syntactically_valid(selector) is valid
