"""C2 acceptance: the scripted naive<->canonical spread through the real game.

Slow (runs both full trajectories incl. experiments and scoring). Investigating
must win by the real path: naive lands near R=0, canonical above 0.7.
"""

import sys
from pathlib import Path

import pytest

CASE_DIR = Path(__file__).resolve().parents[1] / "cases" / "dummy_dose_v0"
sys.path.insert(0, str(CASE_DIR))


@pytest.mark.slow
def test_scripted_spread_investigation_wins():
    from solvers import solver_canonical, solver_naive

    from wager.harness.case_episode import build_world_server
    from wager.harness.env import Env

    sn = build_world_server(CASE_DIR)
    solver_naive(Env(sn))
    sc = build_world_server(CASE_DIR)
    solver_canonical(Env(sc))

    r_naive = sn.result["R"]
    r_canonical = sc.result["R"]
    assert r_naive < 0.2, f"naive should land near 0, got {r_naive}"
    assert r_canonical > 0.7, f"canonical should win by investigating, got {r_canonical}"
    # the canonical solver paid for experiments (it did not just believe the data)
    assert any(ev.verb == "experiment" for ev in sc.trajectory)
