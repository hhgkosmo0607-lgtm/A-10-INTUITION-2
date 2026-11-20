"""Keeps the layers honest. A change that breaks a dependency rule fails here, not in review.

Rules (see AGENTS.md):
- domain: standard library only
- ports: domain only
- application: domain and ports only
- adapters: never application or web
- web: only main.py (the composition root) may import adapters
- inner layers (domain, ports, application) import no third-party package
"""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "factlock"
LAYERS = ("domain", "ports", "application", "adapters", "web")
ALLOWED = {
    "domain": {"domain"},
    "ports": {"domain", "ports"},
    "application": {"domain", "ports", "application"},
    "adapters": {"domain", "ports", "adapters"},
    "web": {"domain", "ports", "application", "web"},
}
MAX_LINES = 400  # a file past this size is usually doing more than one job


def modules() -> list[Path]:
    return sorted(p for layer in LAYERS for p in (SRC / layer).rglob("*.py"))


def imported(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


@pytest.mark.parametrize("path", modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_module_only_depends_inward(path: Path) -> None:
    layer = path.relative_to(SRC).parts[0]
    allowed = set(ALLOWED[layer])
    if layer == "web" and path.name == "main.py":
        allowed.add("adapters")  # the composition root wires concrete adapters
    for name in imported(path):
        parts = name.split(".")
        if parts[0] == "factlock":
            target = parts[1] if len(parts) > 1 else ""
            assert target in allowed, f"{layer} must not import factlock.{target}"
        elif layer in ("domain", "ports", "application"):
            assert parts[0] in sys.stdlib_module_names, f"{layer} must not import third-party package {parts[0]}"


@pytest.mark.parametrize("path", modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_module_stays_small(path: Path) -> None:
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines <= MAX_LINES, f"{path.name} has {lines} lines; split it by responsibility"
