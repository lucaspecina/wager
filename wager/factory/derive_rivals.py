"""Derive rivals from the declared case (factory side) -- the rival is DERIVED,
not authored (NORTH_STAR §4.4, ARCHITECTURE §5).

Rivals are returned as in-process callables sample(regime_ns, n, seed) for the
battery builder and certificates (scored via score_callable; trusted, no sandbox).
v0 covers:
  (a) naive joint  -- believe the corrupted observational data
  (b) innocent twin -- the mechanism with one operator ABLATED + params refit
  (d) capacity ladder -- {linear, GBM} models of OBSERVABLES only (no latent);
      the best no-latent member anchors the THEORY-GAP certificate.
Rival (c) prior-evoked (LLM panel) lives in rival_c_panel.py (LLM-first).

LLMs are allowed here (factory); these particular rivals use none.
"""

from types import SimpleNamespace
from typing import Callable

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures

COLS = ["dose", "marker", "outcome"]


def _ns(config=None, context=None):
    return SimpleNamespace(config=config or {}, context=context or {}, horizon=None)


def observational_pool(world_sample: Callable, source, n: int, seed: int) -> pd.DataFrame:
    return world_sample(_ns(dict(source.config), dict(source.context)), n, seed)


def experimental_grid(world_sample: Callable, knob: str, levels, cohorts, n: int, seed0: int) -> pd.DataFrame:
    """Clean interventional data do(knob=level) across cohorts -- the access a
    capable rival would buy. Used to fit the no-latent and twin rivals."""
    frames = []
    s = seed0
    for lv in levels:
        for c in cohorts:
            df = world_sample(_ns({knob: float(lv)}, {"cohort": float(c)}), n, s).copy()
            df["cohort"] = c
            frames.append(df)
            s += 1
    return pd.concat(frames, ignore_index=True)


# ---- (a) naive joint -------------------------------------------------------
def rival_naive(pool: pd.DataFrame) -> Callable:
    mu = pool[COLS].mean().to_numpy()
    cov = pool[COLS].cov().to_numpy()

    def sample(regime, n, seed):
        rng = np.random.default_rng(seed)
        if "dose" in regime.config:
            d = float(regime.config["dose"])
            mu_c = mu[1:] + cov[1:, 0] / cov[0, 0] * (d - mu[0])
            cov_c = cov[1:, 1:] - np.outer(cov[1:, 0], cov[0, 1:]) / cov[0, 0]
            draw = rng.multivariate_normal(mu_c, cov_c, n)
            return pd.DataFrame({"dose": np.full(n, d), "marker": draw[:, 0], "outcome": draw[:, 1]})
        draw = rng.multivariate_normal(mu, cov, n)
        return pd.DataFrame({"dose": np.clip(draw[:, 0], 0, 10), "marker": draw[:, 1], "outcome": draw[:, 2]})

    return sample


# ---- (b) innocent twin: ablate one operator, refit to the corrupted pool ----
def rival_twin(mechanism: Callable, base_params: dict, ablation: dict, pool: pd.DataFrame) -> Callable:
    """The mechanism with `ablation` applied (operator off), free params re-fit so
    its observational marginals match the corrupted pool's (the 'didn't see the
    trap' model). v0 refit: scale the outcome/dose params to match pool moments by
    matching the observational mean/variance of outcome and dose."""
    p = dict(base_params)
    p.update(ablation)
    # cheap moment refit: match observational outcome mean & dose mean by shifting
    # effect_dose and dose_base (generic 1-D corrections; declared approximate).
    obs_regime = _ns({}, {"cohort": 0.0})
    sim = mechanism(p, obs_regime, len(pool), 90001)
    if sim["outcome"].std() > 1e-6:
        p["effect_dose"] = p.get("effect_dose", 1.0) * float(pool["outcome"].std() / sim["outcome"].std())
    p["dose_base"] = p.get("dose_base", 0.0) + float(pool["dose"].mean() - sim["dose"].mean())

    def sample(regime, n, seed):
        return mechanism(p, regime, n, seed)

    return sample


# ---- (d) capacity ladder: models of OBSERVABLES only (no latent) ------------
def _fit_no_latent(train: pd.DataFrame, pool: pd.DataFrame, flexible: bool) -> Callable:
    """Best generative model restricted to functions of OBSERVABLES (no latent).

    Models the conditional JOINT P(marker, outcome | dose, cohort): means via a
    SMOOTH regressor (polynomial -- it interpolates the dose-response between grid
    points; a tree/GBM steps and mis-fits off-grid doses, which crippled the
    no-latent and overstated the theory gap, Decision Log v0.18), and the
    marker-outcome dependence via the fitted residual covariance (NOT by chaining
    marker -> outcome, which amplifies variance through the noisy generated
    marker). `flexible`=True uses degree-4 features (the theory-gap anchor);
    False uses linear (a weaker capacity rung)."""
    def _mk():
        return make_pipeline(PolynomialFeatures(4 if flexible else 1), LinearRegression())

    X = train[["dose", "cohort"]].to_numpy()
    m_model = _mk().fit(X, train["marker"].to_numpy())
    o_model = _mk().fit(X, train["outcome"].to_numpy())
    r_marker = train["marker"].to_numpy() - m_model.predict(X)
    r_outcome = train["outcome"].to_numpy() - o_model.predict(X)
    resid_cov = np.cov(np.vstack([r_marker, r_outcome]))  # 2x2 joint of observables
    dose_pool = pool["dose"].to_numpy()

    def sample(regime, n, seed):
        rng = np.random.default_rng(seed)
        cohort = float(regime.context.get("cohort", 0.0))
        if "dose" in regime.config:
            dose = np.full(n, float(regime.config["dose"]))
        else:
            dose = rng.choice(dose_pool, n, replace=True)
        Xq = np.column_stack([dose, np.full(n, cohort)])
        mean_m = m_model.predict(Xq)
        mean_o = o_model.predict(Xq)
        resid = rng.multivariate_normal([0.0, 0.0], resid_cov, n)
        return pd.DataFrame({
            "dose": dose,
            "marker": mean_m + resid[:, 0],
            "outcome": mean_o + resid[:, 1],
        })

    return sample


def capacity_ladder(train: pd.DataFrame, pool: pd.DataFrame) -> list[tuple[str, Callable]]:
    return [
        ("linear_no_latent", _fit_no_latent(train, pool, flexible=False)),
        ("gbm_no_latent", _fit_no_latent(train, pool, flexible=True)),
    ]


def best_no_latent(train: pd.DataFrame, pool: pd.DataFrame) -> Callable:
    """The best model restricted to functions of observables -- the THEORY-GAP
    reference (Decision Log v0.17). GBM conditioning outcome on observed marker."""
    return _fit_no_latent(train, pool, flexible=True)


def build_standard_rivals(case_dir, world_sample: Callable, meta, n_pool=4000, n_train=300):
    """The disagreement rival set the battery_builder weighs (Decision Log v0.24):
    naive (a) + the FULL capacity ladder (d: linear + GBM, not just the best) +
    an innocent twin (b) per declared mechanism operator. The full ladder is the
    direct mitigation of rival-coverage blind spots (#13/#14) -- the battery then
    weighs regions where brute-force-no-mechanism of ANY capacity fails.
    Returns (rivals, pool, train)."""
    from wager.factory.case_loader import load_world_module

    source = list(meta.episode.observe_sources.values())[0]
    pool = observational_pool(world_sample, source, n_pool, 50001)
    train = experimental_grid(world_sample, "dose", list(range(0, 11)), [-1.5, 0.0, 1.5], n_train, 60001)
    wmod = load_world_module(case_dir)
    rivals = [rival_naive(pool)]
    rivals += [fn for _, fn in capacity_ladder(train, pool)]  # linear + GBM (full d)
    for op in meta.operators:
        if op.layer == "mechanism" and op.ablation:
            rivals.append(rival_twin(wmod.mechanism, wmod.PARAMS, dict(op.ablation), pool))
    return rivals, pool, train
