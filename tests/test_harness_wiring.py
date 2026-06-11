"""Wiring tests for the C1 harness (kernel + cells + env). All OFFLINE.

The real-LLM smoke is a script (cases/dummy_dose_v0/c1_smoke.py) and the opt-in
test below (skipped unless RUN_LLM_TESTS=1) -- the default suite never calls the
API, so CI stays free and offline.
"""

import os

import pytest

from wager.agent.cells import extract_cell
from wager.harness.c1_env import BudgetError, C1Env
from wager.harness.kernel import Kernel


def test_kernel_persists_namespace_and_captures_stdout():
    k = Kernel()
    r1 = k.run("x = 40\nprint('set x')")
    assert r1.ok and "set x" in r1.stdout
    r2 = k.run("print(x + 2)")
    assert r2.ok and r2.stdout.strip() == "42"  # variable persisted


def test_kernel_captures_error_without_crashing():
    k = Kernel()
    r = k.run("raise ValueError('boom')")
    assert not r.ok
    assert "ValueError: boom" in r.error
    # kernel still usable after an error
    assert k.run("print('alive')").stdout.strip() == "alive"


def test_extract_cell_prefers_python_fence():
    text = "Plan: do a thing.\n```python\nprint(1)\n```\ntrailing"
    assert extract_cell(text) == "print(1)"
    assert extract_cell("no code here") is None


def test_c1_env_describe_and_observe_debits_budget(world_sample, meta):
    env = C1Env(
        world_sample=world_sample,
        brief="brief text",
        schema=meta.column_names,
        sources={"src": 1.0},
        budget=1000.0,
    )
    sheet = env.describe()
    assert sheet["schema"] == ["dose", "marker", "outcome"]
    assert env.budget_remaining == 1000.0  # describe is free

    df = env.observe("src", 300)
    assert list(df.columns) == ["dose", "marker", "outcome"]
    assert len(df) == 300
    assert env.budget_remaining == 700.0  # debited 300 * 1.0


def test_c1_env_blocks_overspend(world_sample, meta):
    env = C1Env(world_sample, "b", meta.column_names, {"src": 1.0}, budget=100.0)
    with pytest.raises(BudgetError):
        env.observe("src", 200)
    assert env.budget_remaining == 100.0  # nothing debited on the failed call


def test_c1_env_unknown_source(world_sample, meta):
    env = C1Env(world_sample, "b", meta.column_names, {"src": 1.0}, budget=100.0)
    with pytest.raises(KeyError):
        env.observe("nope", 10)


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_TESTS") != "1",
    reason="real-LLM smoke; set RUN_LLM_TESTS=1 to run (needs Foundry creds, costs tokens)",
)
def test_llm_one_call_smoke():
    from wager.agent.llm_client import FoundryChat

    chat = FoundryChat(system="Reply tersely.", max_completion_tokens=2000)
    turn = chat.ask("Reply with exactly: ok")
    assert "ok" in turn.content.lower()
    assert chat.usage.total_tokens > 0


@pytest.mark.skipif(
    os.environ.get("RUN_LLM_TESTS") != "1",
    reason="real-LLM panel smoke; set RUN_LLM_TESTS=1 to run",
)
def test_rival_c_panel_compiles_to_program(meta):
    # LLM-first milestone: a fresh LLM, given brief+schema only, compiles to an
    # executable model(regime, n, seed) that passes the schema smoke.
    from wager.factory.rival_c_panel import compile_panel_member

    brief = "Observables: dose (mg), marker, outcome. A dose-response system."
    member = compile_panel_member(brief, meta.column_names, meta.episode.smoke_regimes)
    assert member["code"] is not None, f"panel member did not compile: {member.get('last_error')}"
