"""Rival (c) prior-evoked: a panel of fresh LLMs compiled to programs (factory).

LLM-first milestone (Decision Log v0.14): the thinnest real path is panel ->
executable program. k fresh LLMs see ONLY brief + schema (NO data), each writes
the mechanism it EXPECTS from domain knowledge; a compilation-repair loop (factory,
so allowed) brings each to pass a schema smoke; the rival is the equal-weight
ensemble of the k compiled members (v0, no consensus machinery -- Decision Log
v0.17). This validates panel->program; it does NOT yet calibrate the prior knob.

LLMs are allowed here (factory): these programs are frozen artifacts produced
before any episode, never in the reward path.
"""

from typing import Callable

import numpy as np
import pandas as pd

from wager.agent.cells import extract_cell
from wager.agent.llm_client import FoundryChat
from wager.contracts.world import Regime
from wager.reward.sandbox import SandboxedSubmission, SandboxError, lint_submission

PANEL_SYSTEM = """You are a domain expert in applied modelling. You will see a brief and an
observable schema -- but NO data. Write the generative mechanism you EXPECT this system to
follow from domain knowledge alone. Reply with ONLY one ```python fenced block defining

    def model(regime, n, seed) -> pandas.DataFrame   # columns exactly as the schema

regime has .config (may fix a knob, e.g. {"dose": 4.0}), .context (e.g. {"cohort": 1.0}),
.horizon. Use numpy/pandas/scipy only; return finite numeric values; no file or network access.
Keep it self-contained. Encode your best prior expectation of how the observables relate."""


def _schema_smoke(code: str, columns: list[str], smoke_regimes: list[Regime], timeout_s: float) -> str | None:
    try:
        lint_submission(code)
    except SandboxError as exc:
        return f"import/lint: {exc}"
    try:
        with SandboxedSubmission(code, columns, timeout_s=timeout_s) as sb:
            for i, regime in enumerate(smoke_regimes):
                try:
                    sb.run(regime, 50, 700 + i)
                except SandboxError as exc:
                    return f"regime {i} ({regime.config}): {exc}"
    except SandboxError as exc:
        return f"load: {exc}. Define model(regime, n, seed)."
    return None


def compile_panel_member(
    brief: str, schema: list[str], smoke_regimes: list[Regime],
    timeout_s: float = 10.0, max_repairs: int = 3, model: str | None = None,
) -> dict:
    chat = FoundryChat(system=PANEL_SYSTEM, model=model)
    prompt = (
        f"Brief:\n\n{brief}\n\nSchema (exact columns): {schema}\n\n"
        "Write your expected mechanism now."
    )
    for attempt in range(max_repairs + 1):
        reply = chat.ask(prompt)
        code = extract_cell(reply.content)
        if code is None:
            prompt = "No ```python block found. Reply with ONLY the code block."
            continue
        err = _schema_smoke(code, schema, smoke_regimes, timeout_s)
        if err is None:
            return {"code": code, "repairs": attempt, "tokens": chat.usage.total_tokens}
        prompt = f"Your program failed validation: {err}\nFix it and resend the FULL program."
    return {"code": None, "repairs": max_repairs, "tokens": chat.usage.total_tokens, "last_error": err}


def ensemble_callable(ensemble: list[tuple[float, str]]) -> Callable:
    """An in-process sample(regime, n, seed) that draws from the k compiled panel
    members by weight (equal weights v0). The members passed lint + schema smoke."""
    fns = []
    for _, code in ensemble:
        ns: dict = {}
        exec(code, ns)  # noqa: S102  (factory artifact, lint+smoke passed)
        fns.append(ns["model"])
    weights = np.array([w for w, _ in ensemble], dtype=float)
    weights = weights / weights.sum()

    def sample(regime, n, seed):
        rng = np.random.default_rng(seed)
        counts = rng.multinomial(n, weights)
        parts = []
        for fn, c in zip(fns, counts):
            if c > 0:
                parts.append(fn(regime, int(c), int(rng.integers(0, 2**31 - 1))))
        return pd.concat(parts, ignore_index=True)

    return sample


def derive_rival_c(
    brief: str, schema: list[str], smoke_regimes: list[Regime],
    k: int = 3, timeout_s: float = 10.0, model: str | None = None,
) -> dict:
    members = [compile_panel_member(brief, schema, smoke_regimes, timeout_s, model=model) for _ in range(k)]
    ok = [m for m in members if m["code"] is not None]
    weight = 1.0 / len(ok) if ok else 0.0
    return {
        "members": members,
        "ensemble": [(weight, m["code"]) for m in ok],
        "k_requested": k,
        "k_compiled": len(ok),
    }
