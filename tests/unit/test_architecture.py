"""Layering rules, checked from the source imports."""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"

# layer -> layers it must never import
FORBIDDEN = {
    "domain": {"application", "infrastructure", "api", "config"},
    "application": {"infrastructure", "api", "config"},
    "infrastructure": {"application", "api"},
}
COMPOSITION_ROOTS = {APP / "api" / "dependencies.py", APP / "main.py"}


def _app_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    layers = set()
    for node in ast.walk(tree):
        names = []
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        for name in names:
            parts = name.split(".")
            if parts[0] == "app" and len(parts) > 1:
                layers.add(parts[1])
    return layers


@pytest.mark.parametrize("layer", sorted(FORBIDDEN))
def test_layer_does_not_import_forbidden_layers(layer):
    violations = []
    for path in (APP / layer).rglob("*.py"):
        bad = _app_imports(path) & FORBIDDEN[layer]
        if bad:
            violations.append(f"{path.relative_to(APP)} imports {sorted(bad)}")
    assert not violations, "\n".join(violations)


def test_only_composition_root_wires_infrastructure_into_api():
    violations = [
        str(p.relative_to(APP))
        for p in (APP / "api").rglob("*.py")
        if p not in COMPOSITION_ROOTS and "infrastructure" in _app_imports(p)
    ]
    assert not violations
