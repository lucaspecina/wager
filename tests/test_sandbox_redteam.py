"""L0 - sandbox red-team (ARCHITECTURE 13-L0).

THREAT MODEL (Slice 1, Decision Log v0.11): submissions are our own committed
fixtures; this proves the sandbox stops the accidental and the obvious and that
escapes degrade to D_MAX rather than leaking. Real hardening arrives with the
interactive harness. Every new escape idea is appended here and to REDTEAM.md.

Each escape must FAIL CLOSED: a SandboxError (capped at D_MAX by the scorer),
never a value and never a leak.
"""

import numpy as np
import pandas as pd
import pytest

from wager.contracts import Battery, BatteryItem, Regime, ScoringParams
from wager.reward.sandbox import SandboxError, SandboxedSubmission, lint_submission
from wager.reward.scorer import WorldSide, score_submission

COLUMNS = ["dose", "marker", "outcome"]

# (id, code) - each must be rejected by lint or fail closed at runtime.
ESCAPES = [
    ("read_world_py", "import os\ndef model(regime,n,seed):\n open('world.py').read()\n"),
    ("read_battery_json", "def model(regime,n,seed):\n return open('../battery.json').read()\n"),
    ("subprocess", "import subprocess\ndef model(regime,n,seed):\n subprocess.run(['ls'])\n"),
    ("os_system", "import os\ndef model(regime,n,seed):\n os.system('echo hi')\n"),
    ("network_socket", "import socket\ndef model(regime,n,seed):\n socket.socket()\n"),
    ("eval_builtin", "def model(regime,n,seed):\n return eval('1+1')\n"),
    ("exec_builtin", "def model(regime,n,seed):\n exec('x=1')\n"),
    ("dunder_globals", "def model(regime,n,seed):\n return model.__globals__\n"),
    ("import_via_dunder", "def model(regime,n,seed):\n return ().__class__.__bases__\n"),
    ("open_write", "def model(regime,n,seed):\n open('pwned.txt','w').write('x')\n"),
    ("relative_import", "from . import secrets\ndef model(regime,n,seed):\n pass\n"),
]


@pytest.mark.parametrize("escape_id,code", ESCAPES, ids=[e[0] for e in ESCAPES])
def test_escape_fails_closed(escape_id, code):
    regime = Regime(config={"dose": 3.0})
    try:
        with SandboxedSubmission(code, COLUMNS, timeout_s=5.0) as sb:
            with pytest.raises(SandboxError):
                sb.run(regime, 50, 123)
    except SandboxError:
        pass  # rejected at lint/init time - also fail-closed


def test_lint_blocks_disallowed_import():
    with pytest.raises(SandboxError):
        lint_submission("import requests\ndef model(r,n,s):\n pass\n")


def test_timeout_fails_closed():
    code = "def model(regime,n,seed):\n while True:\n  pass\n"
    with SandboxedSubmission(code, COLUMNS, timeout_s=1.5) as sb:
        with pytest.raises(SandboxError):
            sb.run(Regime(config={"dose": 1.0}), 10, 1)


def test_wrong_columns_fails_closed():
    code = (
        "import pandas as pd\n"
        "def model(regime,n,seed):\n"
        " return pd.DataFrame({'dose':[0.0]*n,'wrong':[0.0]*n,'outcome':[0.0]*n})\n"
    )
    with SandboxedSubmission(code, COLUMNS, timeout_s=5.0) as sb:
        with pytest.raises(SandboxError):
            sb.run(Regime(config={"dose": 1.0}), 10, 1)


def test_nan_output_fails_closed():
    code = (
        "import numpy as np, pandas as pd\n"
        "def model(regime,n,seed):\n"
        " return pd.DataFrame({'dose':[np.nan]*n,'marker':[0.0]*n,'outcome':[0.0]*n})\n"
    )
    with SandboxedSubmission(code, COLUMNS, timeout_s=5.0) as sb:
        with pytest.raises(SandboxError):
            sb.run(Regime(config={"dose": 1.0}), 10, 1)


def test_crash_caps_at_d_max(world_sample):
    """A submission that always crashes scores exactly D_MAX on every item:
    crashing pays strictly worse than the null (D_MAX = 1.5 x D(truth,null))."""
    crash = "def model(regime,n,seed):\n raise RuntimeError('boom')\n"
    items = [BatteryItem(weight=1.0, regime=Regime(config={"dose": 3.0}), seed_world=99)]
    battery = Battery(items=items)
    params = ScoringParams(lambda_mdl=0.0, n_samples=300, m_reps=2)
    ws = WorldSide(world_sample, battery, COLUMNS, params.n_samples)
    report = score_submission(crash, ws, params)
    item = report.items[0]
    assert item.sandbox_errors == params.m_reps
    assert item.mean_distance == pytest.approx(item.d_max)
