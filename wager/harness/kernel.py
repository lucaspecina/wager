"""Persistent Python kernel for the agent (C1 minimal version).

Executes the agent's cells in a persistent namespace and captures stdout/stderr
and any traceback. C1 runs in-process (the LLM smoke is plumbing, not the real
opaque episode); the sandboxed, opaque, separate-process kernel arrives in C3
(ARCHITECTURE 14.2). The injected `env` is the only world surface the agent gets.

This mirrors the SREG python_exec persistent-kernel pattern (allowlist) but is
re-written against the WAGER env contract (spec-first).
"""

import contextlib
import io
import traceback
from dataclasses import dataclass


@dataclass
class CellResult:
    ok: bool
    stdout: str
    error: str | None  # traceback text if the cell raised


class Kernel:
    def __init__(self, injected: dict | None = None) -> None:
        self.ns: dict = {"__name__": "__agent__"}
        if injected:
            self.ns.update(injected)

    def run(self, code: str) -> CellResult:
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                exec(compile(code, "<cell>", "exec"), self.ns)  # noqa: S102
            return CellResult(ok=True, stdout=out.getvalue(), error=None)
        except Exception:  # noqa: BLE001
            return CellResult(ok=False, stdout=out.getvalue(), error=traceback.format_exc())
