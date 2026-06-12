"""Combined score = energy + Σ c_F·S_F(|F(pred)−F(real)|) (ARCHITECTURE §9.3).

Guards: (P1) identity by construction when no functionals are declared; the
functional penalizes a tail-wrong model; D_MAX is a function of c_F (amendment 4,
Decision Log v0.28).
"""

import numpy as np
import pandas as pd

from wager.contracts import Battery, BatteryItem, FunctionalSpec, Regime, ScoringParams
from wager.reward.scorer import WorldSide, score_callable

COLS = ["x"]
PARAMS = ScoringParams(lambda_mdl=0.0, n_samples=2000, m_reps=2)
HARM = FunctionalSpec(name="exceedance", column="x", threshold=-2.0, direction="below",
                      brief_clause="a value below -2 is harm")


def world(regime, n, seed):  # bimodal +-5: P(x < -2) = 0.5
    rng = np.random.default_rng(seed)
    s = rng.integers(0, 2, n) * 2 - 1
    return pd.DataFrame({"x": s * 5.0 + rng.normal(0.0, 0.5, n)})


def unimodal(regime, n, seed):  # matched mean 0, unimodal: P(x < -2) ~ 0.34 != 0.5
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"x": rng.normal(0.0, 5.0, n)})


def _battery():
    return Battery(items=[BatteryItem(weight=1.0, regime=Regime(), seed_world=42)])


def test_identity_by_construction():
    """No functionals declared -> combined score ≡ energy score (the dummy)."""
    bat = _battery()
    ws_none = WorldSide(world, bat, COLS, PARAMS.n_samples, null_sample=unimodal)
    ws_empty = WorldSide(world, bat, COLS, PARAMS.n_samples, null_sample=unimodal, functionals=[])
    assert ws_none.d_maxes == ws_empty.d_maxes
    for fn in (world, unimodal):
        assert score_callable(fn, ws_none, PARAMS) == score_callable(fn, ws_empty, PARAMS)
    # the functional contribution is exactly zero with no specs
    assert ws_empty.func_scorers[0].extra_distance(world(Regime(), 2000, 1)) == 0.0


def test_functional_penalizes_tail_mismatch():
    """A unimodal model matched in mean but WRONG in the harm tail scores strictly
    worse under the declared exceedance functional than under energy alone."""
    bat = _battery()
    ws_energy = WorldSide(world, bat, COLS, PARAMS.n_samples, null_sample=unimodal)
    ws_comb = WorldSide(world, bat, COLS, PARAMS.n_samples, null_sample=unimodal,
                        functionals=[HARM], c_f=1.0)
    # truth still scores ~0 (F(truth)=F(truth)); the unimodal model scores worse
    assert score_callable(unimodal, ws_comb, PARAMS) < score_callable(unimodal, ws_energy, PARAMS) - 1e-6
    assert abs(score_callable(world, ws_comb, PARAMS)) < 0.05


def test_dmax_is_function_of_cf():
    """D_MAX_item = 1.5×D_combined(truth, null) grows with c_F (amendment 4)."""
    bat = _battery()
    d0 = WorldSide(world, bat, COLS, PARAMS.n_samples, null_sample=unimodal).d_maxes[0]
    d1 = WorldSide(world, bat, COLS, PARAMS.n_samples, null_sample=unimodal,
                   functionals=[HARM], c_f=1.0).d_maxes[0]
    d2 = WorldSide(world, bat, COLS, PARAMS.n_samples, null_sample=unimodal,
                   functionals=[HARM], c_f=2.0).d_maxes[0]
    assert d2 > d1 > d0
