"""Env -- the agent-facing facade over a WorldServer backend.

Ergonomic verbs (experiment takes plain kwargs and builds the validated
ExperimentDesign). The backend is a WorldServer directly (scripted solvers,
in-process) or a data-only proxy across a process boundary (the LLM, C3); both
expose describe/observe/experiment(design)/submit.
"""

from wager.contracts import ExperimentDesign


class Env:
    def __init__(self, backend) -> None:
        self._backend = backend

    def describe(self) -> dict:
        return self._backend.describe()

    def observe(self, source: str, n: int):
        return self._backend.observe(source, n)

    def experiment(self, config=None, context=None, n: int = 500, horizon=None):
        design = ExperimentDesign(
            config=config or {}, context=context or {}, n=n, horizon=horizon
        )
        return self._backend.experiment(design)

    def submit(self, code: str):
        return self._backend.submit(code)
