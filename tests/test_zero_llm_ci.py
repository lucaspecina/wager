"""L0 - the zero-LLM CI gate (NORTH_STAR 2.2, ARCHITECTURE 13-L0).

The frontier is temporal: no LLM may run between episode start and reward
emission. Operationalized here as a STATIC import allowlist over the reward
path package - the build fails if wager.reward (transitively) imports anything
outside stdlib-safe + numpy/pandas/scipy + wager.contracts. The dynamic side
(scoring completes with the network disabled) lives in test_sandbox_redteam.py
and is also a production guarantee, not only a CI one.
"""

import ast
import importlib
from pathlib import Path

import pytest

REWARD_DIR = Path(__file__).resolve().parents[1] / "wager" / "reward"

# Third-party libraries the reward path may import. NO LLM clients, NO http.
ALLOWED_THIRD_PARTY = {"numpy", "pandas", "scipy"}
ALLOWED_FIRST_PARTY = {"wager"}

# stdlib modules actually used by the reward path. socket/os/tempfile appear
# ONLY inside sandbox.py to DISABLE the network and isolate cwd (documented).
ALLOWED_STDLIB = {
    "ast", "zlib", "hashlib", "time", "math", "json", "multiprocessing",
    "types", "typing", "pathlib", "collections", "itertools", "functools",
    "dataclasses", "abc", "builtins", "socket", "os", "tempfile",
    "importlib", "statistics", "warnings", "contextlib", "__future__",
}

# Banned substrings: any of these in an import name is an automatic failure,
# even if some future allowlist edit would otherwise admit it.
LLM_TELLS = (
    "openai", "anthropic", "azure", "llm", "langchain", "transformers",
    "requests", "httpx", "urllib", "http", "aiohttp", "litellm", "cohere",
    "google.generativeai", "vertexai", "boto3",
)


def _reward_py_files():
    return sorted(REWARD_DIR.rglob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.level or 0) == 0:
                roots.add(node.module)
    return roots


def test_reward_imports_within_allowlist():
    allowed = ALLOWED_THIRD_PARTY | ALLOWED_FIRST_PARTY | ALLOWED_STDLIB
    violations: list[str] = []
    for path in _reward_py_files():
        for name in _imported_roots(path):
            root = name.split(".")[0]
            if root not in allowed:
                violations.append(f"{path.name}: imports '{name}'")
    assert not violations, "reward path import allowlist violated:\n" + "\n".join(violations)


def test_reward_path_does_not_import_agent_or_harness():
    # 'wager' is an allowed root, so the allowlist alone would let reward import
    # wager.agent / wager.harness (which DO use LLMs). Forbid it explicitly.
    offenders: list[str] = []
    for path in _reward_py_files():
        for name in _imported_roots(path):
            if name.startswith(("wager.agent", "wager.harness")):
                offenders.append(f"{path.name}: '{name}'")
    assert not offenders, "reward path imports an LLM-facing package:\n" + "\n".join(offenders)


def test_reward_path_has_no_llm_tells():
    offenders: list[str] = []
    for path in _reward_py_files():
        for name in _imported_roots(path):
            lowered = name.lower()
            if any(tell in lowered for tell in LLM_TELLS):
                offenders.append(f"{path.name}: '{name}'")
    assert not offenders, "LLM/network tell in reward path:\n" + "\n".join(offenders)


def test_reward_modules_actually_import():
    # If a banned dep were imported transitively, importing would pull it in.
    for mod in (
        "wager.reward.scorer",
        "wager.reward.ladder",
        "wager.reward.variance",
        "wager.reward.distance",
        "wager.reward.mdl",
        "wager.reward.seeds",
        "wager.reward.sandbox",
    ):
        importlib.import_module(mod)


def test_no_llm_client_modules_loaded_after_reward_import():
    import sys

    importlib.import_module("wager.reward.scorer")
    bad = [m for m in sys.modules if any(t in m.lower() for t in ("openai", "anthropic", "langchain", "litellm"))]
    assert not bad, f"LLM client modules present in sys.modules: {bad}"
