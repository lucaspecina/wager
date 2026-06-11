"""Wiring tests for the WorldServer (verbs, budget, channel, submit smoke)."""

from pathlib import Path

import pytest

from wager.contracts import ExperimentDesign
from wager.harness.case_episode import build_world_server
from wager.harness.world_server import BudgetError

CASE_DIR = Path(__file__).resolve().parents[1] / "cases" / "dummy_dose_v0"
SOURCE = "registros_clinicos_2019_2023"


@pytest.fixture
def server():
    return build_world_server(CASE_DIR)


def test_describe_is_free_and_shows_surface(server):
    rem0 = server.budget_remaining
    d = server.describe()
    assert d["schema"] == ["dose", "marker", "outcome"]
    assert "settable" in d["control_surface"]
    assert server.budget_remaining == rem0  # describe is free


def test_observe_debits_budget(server):
    rem0 = server.budget_remaining
    df = server.observe(SOURCE, 300)
    assert list(df.columns) == ["dose", "marker", "outcome"] and len(df) == 300
    assert server.budget_remaining == rem0 - 300.0


def test_budget_error_when_overspending(server):
    server.experiment(ExperimentDesign(config={"dose": 1.0}, n=5000))  # cost 100 + 10000
    with pytest.raises(BudgetError):
        server.experiment(ExperimentDesign(config={"dose": 1.0}, n=5000))  # > remaining


def test_experiment_respects_measurement_channel(server):
    """Decision Log v0.14, precision 1: experiment runs the mechanism fresh
    (bypasses the dose assignment) but NEVER the measurement channel -- same
    schema, marker still a noisy proxy."""
    obs = server.observe(SOURCE, 3000)
    exp = server.experiment(ExperimentDesign(config={"dose": 3.0}, context={"cohort": 0.0}, n=3000))
    assert list(obs.columns) == list(exp.columns) == ["dose", "marker", "outcome"]
    # marker noise (severity ~ N(0,1) in both) is the same channel
    assert abs(obs["marker"].std() - exp["marker"].std()) < 0.3
    # but the assignment is bypassed: experiment fixes dose, observe varies it
    assert exp["dose"].std() < 1e-6
    assert obs["dose"].std() > 0.5


def test_submit_bad_columns_gives_actionable_error(server):
    bad = (
        "import pandas as pd\n"
        "def model(regime, n, seed):\n"
        " return pd.DataFrame({'dose':[0.0]*n,'outcome':[0.0]*n})\n"  # missing 'marker'
    )
    res = server.submit(bad)
    assert res.accepted is False
    assert "marker" in res.error or "columns" in res.error
    assert not server.terminal  # episode stays open after a failed submit


def test_submit_truth_is_accepted_and_scores_high(server):
    res = server.submit(server.scoring.world_source)
    assert res.accepted is True
    assert server.terminal
    assert server.result["R"] == pytest.approx(1.0, abs=1e-6)  # world.py -> R=1
