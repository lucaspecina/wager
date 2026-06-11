"""Minimal `env` for the C1 LLM smoke (describe + observe + budget ledger).

C1 scope only: enough world surface for the model to read the brief and pull
observational data, so the smoke exercises the real contract shape. experiment()
and submit(), the opaque separate-process handle, and data-only IPC come in C3.
The world runs in-process here; observe() returns the natural (config-empty)
observational regime, which for dummy_dose_v0 already carries the mechanism-level
confounding.
"""

from typing import Callable

import pandas as pd


class BudgetError(RuntimeError):
    pass


class C1Env:
    def __init__(
        self,
        world_sample: Callable,
        brief: str,
        schema: list[str],
        sources: dict[str, float],  # name -> cost per row
        budget: float,
        context: dict[str, float] | None = None,
    ) -> None:
        self._world_sample = world_sample
        self._brief = brief
        self._schema = list(schema)
        self._sources = dict(sources)
        self._budget = float(budget)
        self._spent = 0.0
        self._context = dict(context or {})
        self._observe_calls = 0

    # --- verbs ---------------------------------------------------------
    def describe(self) -> dict:
        return {
            "brief": self._brief,
            "schema": self._schema,
            "sources": {k: {"cost_per_row": v} for k, v in self._sources.items()},
            "budget_total": self._budget,
            "budget_remaining": self.budget_remaining,
        }

    def observe(self, source: str, n: int) -> pd.DataFrame:
        if source not in self._sources:
            raise KeyError(f"unknown source {source!r}; available: {list(self._sources)}")
        cost = self._sources[source] * n
        if self._spent + cost > self._budget:
            raise BudgetError(
                f"observe({source!r}, {n}) costs {cost}, but only "
                f"{self.budget_remaining} budget remains"
            )
        self._spent += cost
        seed = 700000 + self._observe_calls  # distinct world seeds per observe
        self._observe_calls += 1
        regime = _Regime(config={}, context=self._context)
        return self._world_sample(regime, n, seed)

    # --- ledger --------------------------------------------------------
    @property
    def budget_remaining(self) -> float:
        return self._budget - self._spent

    @property
    def spent(self) -> float:
        return self._spent


class _Regime:
    """Plain regime view passed to world.sample (config/context/horizon)."""

    def __init__(self, config: dict, context: dict, horizon: int | None = None) -> None:
        self.config = config
        self.context = context
        self.horizon = horizon
