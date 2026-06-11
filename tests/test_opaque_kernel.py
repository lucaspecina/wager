"""Opaque-handle kernel: encoding round-trip (precision 4) + introspection
red-team (precision 3). All OFFLINE (no LLM).

The agent's cells run in a separate process; the world lives in the main process.
These assert the data-only boundary fails closed and that the agent cannot reach
the world by introspection or casual file reads. Declared gaps (absolute-path
reads, gc/closure) are tracked in REDTEAM.md.
"""

from pathlib import Path

import pytest

from wager.harness.case_episode import build_world_server
from wager.harness.kernel_proc import KernelClient

CASE_DIR = Path(__file__).resolve().parents[1] / "cases" / "dummy_dose_v0"


@pytest.fixture
def kernel():
    server = build_world_server(CASE_DIR)
    k = KernelClient(server, cell_timeout_s=20.0)
    yield k
    k.close()


def test_cell_runs_persists_and_uses_env(kernel):
    r1 = kernel.run_cell("df = env.observe('registros_clinicos_2019_2023', 50)\nprint(df.shape)")
    assert r1.ok and "(50, 3)" in r1.stdout
    r2 = kernel.run_cell("print(list(df.columns))")  # var persisted across cells
    assert r2.ok and "dose" in r2.stdout and "outcome" in r2.stdout


def test_unicode_roundtrips_through_subprocess(kernel):
    # the whole bug class, not just the em-dash (precision 4)
    code = "s = 'em-dash — bullet • accent é arrow →'\nprint(s)"
    r = kernel.run_cell(code)
    assert r.ok
    for ch in ("—", "•", "é", "→"):
        assert ch in r.stdout, f"{ch!r} did not round-trip"


def test_full_brief_roundtrips_via_describe(kernel):
    r = kernel.run_cell("print(env.describe()['brief'])")
    assert r.ok and "clinic dose policy" in r.stdout


def test_env_does_not_expose_a_world_handle(kernel):
    code = (
        "print('DICT', dict(env.__dict__))\n"
        "print('DIR', [a for a in dir(env) if not a.startswith('__')])\n"
    )
    r = kernel.run_cell(code)
    assert r.ok
    assert "DICT {}" in r.stdout  # pipe hidden in a closure, not an attribute
    for leak in ("_conn", "server", "world", "battery", "world_sample"):
        assert leak not in r.stdout


def test_cannot_read_world_or_battery_files(kernel):
    code = (
        "import os\n"
        "tried = ['world.py','battery.json','cases/dummy_dose_v0/world.py','meta.json']\n"
        "got = []\n"
        "for p in tried:\n"
        "    try:\n"
        "        open(p).read(); got.append(p)\n"
        "    except Exception as e:\n"
        "        pass\n"
        "print('READABLE', got)\n"
    )
    r = kernel.run_cell(code)
    assert r.ok and "READABLE []" in r.stdout  # cwd isolated: none readable


def test_experiment_with_callable_fails_closed(kernel):
    code = "env.experiment(config={'dose': (lambda x: x)}, n=10)\n"
    r = kernel.run_cell(code)
    assert not r.ok and ("must be plain JSON data" in r.error or "TypeError" in r.error)


def test_experiment_with_bad_value_fails_closed(kernel):
    code = "print(env.experiment(config={'dose': 'huge'}, n=10))\n"
    r = kernel.run_cell(code)
    # server-side validation rejects non-numeric -> RuntimeError surfaced, no leak
    assert not r.ok and "RuntimeError" in r.error


def test_budget_error_surfaces_as_data(kernel):
    code = "env.observe('registros_clinicos_2019_2023', 5000)\nenv.observe('registros_clinicos_2019_2023', 5000)\nenv.observe('registros_clinicos_2019_2023', 5000)\nenv.observe('registros_clinicos_2019_2023', 1)\n"
    r = kernel.run_cell(code)
    assert not r.ok and "budget" in r.error.lower()
