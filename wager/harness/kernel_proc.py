"""Opaque-handle kernel: the agent's cells run in a SEPARATE process.

Decision Log v0.14: the world (WorldServer, world.py, battery) stays in the main
process; the agent's kernel runs in a subprocess whose `env` is a DATA-ONLY proxy
back to the main process. Verb requests are JSON-checked (callables/objects fail
closed); responses are dicts or DataFrames-as-dicts. The proxy hides its pipe in
a closure so dir(env)/env.__dict__ do not expose a world handle. The subprocess
runs in an isolated cwd so casual relative reads of world.py/battery.json fail.

DECLARED GAPS (REDTEAM.md, hardening deferred): absolute-path file reads, and
reaching the pipe via gc/closure introspection, are not yet blocked. The core v0
property holds: the secret artifacts live in another process, never in the
agent's. Full RPC/jail hardening is an open item (ARCHITECTURE 14.2).
"""

import io
import json
import multiprocessing
import os
import tempfile
import traceback
from dataclasses import dataclass

import pandas as pd

from wager.contracts import ExperimentDesign
from wager.harness.world_server import BudgetError, WorldServer

STDOUT_CAP = 3000  # chars returned to the model per cell (Jupyter-style truncation)


@dataclass
class CellResult:
    ok: bool
    stdout: str
    error: str | None
    truncated: bool = False


# ---- subprocess side ------------------------------------------------------
def _make_env_proxy(conn):
    """env whose pipe lives in a closure (not an attribute)."""

    def verb(name, args):
        try:
            json.dumps(args)  # data-only boundary: no callables/objects cross
        except TypeError as exc:
            raise TypeError(f"env.{name} args must be plain JSON data: {exc}") from None
        conn.send({"type": "verb", "name": name, "args": args})
        resp = conn.recv()
        kind = resp["kind"]
        if kind == "error":
            raise RuntimeError(resp["error"])
        if kind == "dataframe":
            return pd.DataFrame(resp["data"])
        if kind == "submit":
            return _SubmitView(resp["accepted"], resp["error"])
        return resp["data"]

    class _Env:
        def describe(self):
            return verb("describe", {})

        def observe(self, source, n):
            return verb("observe", {"source": source, "n": int(n)})

        def experiment(self, config=None, context=None, n=500, horizon=None):
            return verb("experiment", {
                "config": config or {}, "context": context or {},
                "n": int(n), "horizon": horizon,
            })

        def submit(self, code):
            return verb("submit", {"code": code})

    return _Env()


class _SubmitView:
    __slots__ = ("accepted", "error")

    def __init__(self, accepted, error):
        self.accepted = accepted
        self.error = error

    def __repr__(self):
        return f"SubmitResult(accepted={self.accepted}, error={self.error!r})"


def _worker(conn):
    os.chdir(tempfile.mkdtemp(prefix="wager-episode-"))  # isolate cwd from the case
    ns = {"__name__": "__agent__", "env": _make_env_proxy(conn)}
    while True:
        try:
            msg = conn.recv()
        except EOFError:
            return
        if msg is None:
            return
        if msg["type"] == "run_cell":
            out = io.StringIO()
            error = None
            import contextlib

            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                    exec(compile(msg["code"], "<cell>", "exec"), ns)  # noqa: S102
            except Exception:  # noqa: BLE001
                error = traceback.format_exc()
            conn.send({"type": "cell_done", "stdout": out.getvalue(), "error": error})


# ---- main side ------------------------------------------------------------
class KernelClient:
    """Main-side controller of the opaque kernel subprocess. Dispatches the
    agent's verb requests to the WorldServer (which it holds) and returns data."""

    def __init__(self, server: WorldServer, cell_timeout_s: float = 30.0) -> None:
        self.server = server
        self.cell_timeout_s = cell_timeout_s
        ctx = multiprocessing.get_context("spawn")
        self._conn, child = ctx.Pipe()
        self._proc = ctx.Process(target=_worker, args=(child,), daemon=True)
        self._proc.start()
        child.close()

    def run_cell(self, code: str) -> CellResult:
        self._conn.send({"type": "run_cell", "code": code})
        while True:
            if not self._conn.poll(self.cell_timeout_s):
                self.close()
                return CellResult(False, "", f"cell exceeded {self.cell_timeout_s}s and was killed")
            msg = self._conn.recv()
            if msg["type"] == "verb":
                self._conn.send(self._dispatch(msg["name"], msg["args"]))
            elif msg["type"] == "cell_done":
                return self._finish(msg)

    def _finish(self, msg) -> CellResult:
        stdout = msg["stdout"] or ""
        truncated = len(stdout) > STDOUT_CAP
        if truncated:
            stdout = stdout[:STDOUT_CAP] + f"\n... [output truncated: {len(msg['stdout'])} chars total]"
        return CellResult(ok=msg["error"] is None, stdout=stdout, error=msg["error"], truncated=truncated)

    def _dispatch(self, name: str, args: dict) -> dict:
        try:
            if name == "describe":
                return {"type": "verb_result", "kind": "json", "data": self.server.describe()}
            if name == "observe":
                df = self.server.observe(args["source"], args["n"])
                return {"type": "verb_result", "kind": "dataframe", "data": df.to_dict("list")}
            if name == "experiment":
                design = ExperimentDesign(**args)  # server-side validation (data-only)
                df = self.server.experiment(design)
                return {"type": "verb_result", "kind": "dataframe", "data": df.to_dict("list")}
            if name == "submit":
                res = self.server.submit(args["code"])
                return {"type": "verb_result", "kind": "submit", "accepted": res.accepted, "error": res.error}
            return {"type": "verb_result", "kind": "error", "error": f"unknown verb {name!r}"}
        except (BudgetError, KeyError, ValueError, TypeError) as exc:
            return {"type": "verb_result", "kind": "error", "error": f"{type(exc).__name__}: {exc}"}
        except Exception as exc:  # noqa: BLE001  (pydantic ValidationError etc.)
            return {"type": "verb_result", "kind": "error", "error": f"{type(exc).__name__}: {exc}"}

    def close(self) -> None:
        try:
            if self._proc.is_alive():
                self._conn.send(None)
                self._proc.join(timeout=2)
        except (OSError, ValueError):
            pass
        finally:
            if self._proc.is_alive():
                self._proc.terminate()
            self._proc.join(timeout=5)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
