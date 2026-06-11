"""Wiring tests for the scorer: R(world.py)==1, MDL, distance, network-off."""

import numpy as np
import pandas as pd
import pytest

from wager.contracts import ScoringParams
from wager.reward.distance import TruthSide, energy_distance
from wager.reward.mdl import ast_minify, mdl_bytes
from wager.reward.scorer import WorldSide, make_anchors, score_submission
from wager.reward.seeds import derive_seed


def test_derive_seed_never_equals_world_seed():
    # The core invariant of Decision Log v0.10: model side != world side.
    for sw in (0, 1, 11005, 2**31):
        for j in range(8):
            assert derive_seed(sw, j) != sw


def test_derived_seeds_fit_legacy_numpy_range():
    # Decision Log v0.16: seeds must be in [0, 2**32-1] so they work with BOTH
    # np.random.default_rng(seed) AND the legacy np.random.seed(seed). A 64-bit
    # seed silently crashed legacy-API submissions on every battery item.
    from wager.reward.seeds import derive_null_seed, derive_world_seed

    for sw in (0, 11001, 2**31, 2**32 - 1):
        for j in range(6):
            assert 0 <= derive_seed(sw, j) < 2**32
    assert 0 <= derive_null_seed(11001) < 2**32
    assert 0 <= derive_world_seed(11001, 0, 1) < 2**32


def test_legacy_numpy_rng_submission_does_not_crash(world_sample, battery, meta):
    # Regression for the E0.5 DeepSeek artifact: a submission using the legacy
    # np.random.seed(seed) API must score WITHOUT crashing on the battery.
    from wager.contracts import Battery

    code = (
        "import numpy as np, pandas as pd\n"
        "def model(regime, n, seed):\n"
        " np.random.seed(seed)\n"  # legacy API: requires seed < 2**32
        " dose = np.full(n, float(regime.config.get('dose', 3.0)))\n"
        " return pd.DataFrame({'dose': dose, 'marker': np.random.normal(0, 1, n),\n"
        "                      'outcome': np.random.normal(0, 1, n)})\n"
    )
    small = Battery(items=list(battery.items[:5]))
    params = ScoringParams(lambda_mdl=0.0, n_samples=300, m_reps=2)
    ws = WorldSide(world_sample, small, meta.column_names, params.n_samples)
    rep = score_submission(code, ws, params)
    assert all(it.sandbox_errors == 0 for it in rep.items), "legacy-RNG submission crashed (seed range)"


def test_energy_distance_zero_for_identical_samples():
    x = np.random.default_rng(0).normal(size=(200, 3))
    assert energy_distance(x, x) == pytest.approx(0.0, abs=1e-9)


def test_truth_side_distance_nonnegative(world_sample):
    from types import SimpleNamespace

    real = world_sample(SimpleNamespace(config={"dose": 3.0}, context={}, horizon=None), 500, 7)
    ts = TruthSide(real, ["dose", "marker", "outcome"])
    other = world_sample(SimpleNamespace(config={"dose": 8.0}, context={}, horizon=None), 500, 9)
    assert ts.distance_to(other) > 0.0


def test_mdl_minify_strips_docstrings_and_comments():
    a = "def f():\n '''doc'''\n # comment\n return 1\n"
    b = "def f():\n return 1\n"
    assert ast_minify(a) == ast_minify(b)


def test_mdl_ensemble_variants_pay_about_one_member():
    base = "def model(regime, n, seed):\n return seed + {k}\n"
    single = mdl_bytes(base.format(k=0))
    variants = [(0.5, base.format(k=0)), (0.5, base.format(k=1))]
    junk = "def model(regime, n, seed):\n x = [i*i for i in range(n)]\n return sum(x) + {k}\n"
    unrelated = [(0.5, base.format(k=0)), (0.5, junk.format(k=2))]
    # honest variants compress to ~one member; unrelated programs cost more
    assert mdl_bytes(variants) < single * 1.6
    assert mdl_bytes(unrelated) > mdl_bytes(variants)


def test_r_of_world_py_is_exactly_one(world_sample, world_source, battery, meta, ladder):
    """S_truth via the SAME pipeline as any submission => R(world.py)==1 exactly
    (Decision Log v0.11). Computed on a small battery slice for speed."""
    from wager.contracts import Battery

    small = Battery(items=list(battery.items[:4]))
    params = ScoringParams(lambda_mdl=meta.scoring.lambda_mdl, n_samples=400, m_reps=2)
    ws = WorldSide(world_sample, small, meta.column_names, params.n_samples)
    rungs = dict(ladder)
    s_truth = score_submission(world_source, ws, params).raw_score
    s_naive = score_submission(rungs["rung_5_naive_fit"], ws, params).raw_score
    s_null = score_submission(rungs["rung_6_null"], ws, params).raw_score
    anchors = make_anchors(s_truth, s_naive, s_null)
    r_truth, r_unclipped = anchors.r_of(s_truth)
    assert r_truth == 1.0
    assert r_unclipped == pytest.approx(1.0)


def test_scoring_runs_with_network_disabled(world_sample, battery, meta, world_source):
    """Dynamic half of the zero-LLM gate AND a production guarantee: the
    sandbox disables sockets; scoring must still complete."""
    from wager.contracts import Battery

    small = Battery(items=list(battery.items[:3]))
    params = ScoringParams(lambda_mdl=meta.scoring.lambda_mdl, n_samples=300, m_reps=2)
    ws = WorldSide(world_sample, small, meta.column_names, params.n_samples)
    report = score_submission(world_source, ws, params)
    assert report.cost.wall_seconds > 0
    assert len(report.items) == 3
