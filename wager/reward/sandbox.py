"""Sandboxed execution of submissions (v0).

THREAT MODEL (Slice 1, Decision Log v0.11): submissions are our own committed
fixtures; this sandbox must stop the accidental and the obvious, not a
motivated adversary. Real hardening (RPC / filesystem jail) arrives with the
interactive harness (ARCHITECTURE 14.2). Known gaps are tracked in REDTEAM.md
and every new escape idea becomes a test in tests/test_sandbox_redteam.py.

Defenses (in depth):
- AST lint: positive import allowlist, forbidden builtin names, no dunder
  attribute access, no relative imports. Run in parent AND in child.
- Child process (spawn) with restricted builtins for the submission namespace,
  guarded __import__, network disabled (socket patched after pre-imports),
  cwd moved to an empty temp dir so relative paths resolve to nothing.
- Per-call timeout enforced by the parent; a timed-out worker is killed and
  the submission is marked broken (remaining calls fail fast -> D_MAX caps).
- Output validated parent-side: exact columns in order, exact n, finite values.

Network is disabled in PRODUCTION scoring always, not only in CI
(NORTH_STAR Decision Log v0.10).
"""

import ast
import multiprocessing
from types import SimpleNamespace

import pandas as pd

from wager.contracts import Regime

ALLOWED_SUBMISSION_IMPORTS = {
    "numpy",
    "pandas",
    "scipy",
    "sklearn",
    "math",
    "statistics",
    "itertools",
    "functools",
    "collections",
}

_FORBIDDEN_NAMES = {
    "eval",
    "exec",
    "compile",
    "open",
    "__import__",
    "globals",
    "locals",
    "vars",
    "breakpoint",
    "input",
    "getattr",
    "setattr",
    "delattr",
    "type",
    "memoryview",
}

_SAFE_BUILTIN_NAMES = [
    "abs", "all", "any", "bool", "bytes", "callable", "complex", "dict",
    "divmod", "enumerate", "filter", "float", "format", "frozenset", "hash",
    "hasattr",  # safe (returns bool); submissions duck-type the regime (E0 friction)
    "int", "isinstance", "issubclass", "iter", "len", "list", "map", "max",
    "min", "next", "object", "pow", "print", "range", "repr", "reversed",
    "round", "set", "slice", "sorted", "str", "sum", "tuple", "zip",
    "Exception", "BaseException", "ValueError", "TypeError", "KeyError",
    "IndexError", "AttributeError", "RuntimeError", "ZeroDivisionError",
    "ArithmeticError", "OverflowError", "StopIteration", "NotImplementedError",
]


class SandboxError(Exception):
    """Any failure of a sandboxed call: the scorer caps the rep at D_MAX."""


class SubmissionLintError(SandboxError):
    pass


def lint_submission(code: str, allowlist: set[str] | None = None) -> None:
    """Static checks; raises SubmissionLintError. Also used (with the world
    allowlist) by the factory validator for world.py."""
    allowed = ALLOWED_SUBMISSION_IMPORTS if allowlist is None else allowlist
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SubmissionLintError(f"syntax error: {exc}") from exc
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in allowed:
                    raise SubmissionLintError(f"import not allowed: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                raise SubmissionLintError("relative imports not allowed")
            root = (node.module or "").split(".")[0]
            if root not in allowed:
                raise SubmissionLintError(f"import not allowed: {node.module}")
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            raise SubmissionLintError(f"forbidden name: {node.id}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") and node.attr.endswith("__"):
                raise SubmissionLintError(f"dunder attribute access: {node.attr}")


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split(".")[0]
    if level > 0 or root not in ALLOWED_SUBMISSION_IMPORTS:
        raise ImportError(f"import not allowed in sandbox: {name}")
    return __import__(name, globals, locals, fromlist, level)


def _safe_builtins() -> dict:
    import builtins

    safe = {n: getattr(builtins, n) for n in _SAFE_BUILTIN_NAMES if hasattr(builtins, n)}
    safe["__import__"] = _guarded_import
    safe["True"], safe["False"], safe["None"] = True, False, None
    return safe


def _disable_network() -> None:
    # imported solely to disable it; CI grants this file a documented exception
    import socket

    def _blocked(*args, **kwargs):
        raise RuntimeError("network is disabled inside the WAGER sandbox")

    socket.socket = _blocked
    socket.create_connection = _blocked
    socket.getaddrinfo = _blocked


def _isolate_cwd() -> None:
    # os/tempfile imported solely to point cwd at an empty disposable dir,
    # so relative paths inside the submission resolve to nothing
    import os
    import tempfile

    os.chdir(tempfile.mkdtemp(prefix="wager-sandbox-"))


def _worker_main(code: str, conn) -> None:
    # Pre-import heavy libs with full builtins (they need them), THEN lock down.
    import numpy  # noqa: F401

    _disable_network()
    _isolate_cwd()
    namespace = {"__builtins__": _safe_builtins()}
    try:
        lint_submission(code)  # defense in depth: parent linted already
        exec(compile(code, "<submission>", "exec"), namespace)  # noqa: S102
        model = namespace["model"]
    except Exception as exc:  # noqa: BLE001
        conn.send(("init_error", repr(exc)))
        return
    conn.send(("ready", None))
    while True:
        try:
            msg = conn.recv()
        except EOFError:
            return
        if msg is None:
            return
        regime_dict, n, seed = msg
        try:
            regime = SimpleNamespace(**regime_dict)
            result = model(regime, n, seed)
            conn.send(("ok", result))
        except Exception as exc:  # noqa: BLE001
            conn.send(("error", repr(exc)))


class SandboxedSubmission:
    """Persistent sandbox worker for one submission program.

    One spawn per submission (not per call): the scorer makes K x m calls
    against the same worker. Use as a context manager.
    """

    def __init__(
        self,
        code: str,
        columns: list[str],
        timeout_s: float = 10.0,
        init_timeout_s: float = 120.0,
    ) -> None:
        lint_submission(code)
        self.columns = list(columns)
        self.timeout_s = timeout_s
        self._broken: str | None = None
        ctx = multiprocessing.get_context("spawn")
        self._conn, child_conn = ctx.Pipe()
        self._proc = ctx.Process(target=_worker_main, args=(code, child_conn), daemon=True)
        self._proc.start()
        child_conn.close()
        if not self._conn.poll(init_timeout_s):
            self._kill()
            raise SandboxError("sandbox init timeout")
        status, payload = self._conn.recv()
        if status != "ready":
            self._kill()
            raise SandboxError(f"sandbox init failed: {payload}")

    def run(self, regime: Regime, n: int, seed: int) -> pd.DataFrame:
        if self._broken is not None:
            raise SandboxError(f"sandbox is broken: {self._broken}")
        regime_dict = {
            "config": dict(regime.config),
            "context": dict(regime.context),
            "horizon": regime.horizon,
        }
        try:
            self._conn.send((regime_dict, n, seed))
        except (OSError, ValueError) as exc:
            self._broken = f"worker died: {exc!r}"
            raise SandboxError(self._broken) from exc
        if not self._conn.poll(self.timeout_s):
            self._broken = f"model() call exceeded {self.timeout_s}s"
            self._kill()
            raise SandboxError(self._broken)
        status, payload = self._conn.recv()
        if status != "ok":
            raise SandboxError(f"submission raised: {payload}")
        return self._validate(payload, n)

    def _validate(self, df, n: int) -> pd.DataFrame:
        import numpy as np

        if not isinstance(df, pd.DataFrame):
            raise SandboxError(f"model() must return a DataFrame, got {type(df).__name__}")
        if list(df.columns) != self.columns:
            raise SandboxError(
                f"columns mismatch: expected {self.columns}, got {list(df.columns)}"
            )
        if len(df) != n:
            raise SandboxError(f"row count mismatch: expected {n}, got {len(df)}")
        values = df.to_numpy(dtype=float)
        if not np.isfinite(values).all():
            raise SandboxError("non-finite values in output (NaN/inf)")
        return df

    def _kill(self) -> None:
        if self._proc.is_alive():
            self._proc.terminate()
        self._proc.join(timeout=5)

    def close(self) -> None:
        try:
            if self._broken is None and self._proc.is_alive():
                self._conn.send(None)
                self._proc.join(timeout=2)
        except (OSError, ValueError):
            pass
        finally:
            self._kill()
            self._conn.close()

    def __enter__(self) -> "SandboxedSubmission":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
