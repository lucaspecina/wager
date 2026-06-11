"""Scripted solver pair for dummy_dose_v0 (C2 -- permanent fixtures).

Two FULL trajectories through the interactive game (Decision Log v0.14):

- solver_naive: observe, fit the raw observational joint as-is, submit. Believes
  the data; inherits the confounding. Expected R ~ 0 (it lands near the S_naive
  anchor by the real path).
- solver_canonical: observe, notice dose<->marker coupling, PAY do(dose)
  experiments across the dose range, read the causal dose-response and the
  severity effect off the experiments (marker is a noisy severity proxy), fit a
  saturating form, submit a structural model. Expected R > 0.7.

The naive<->canonical spread through the game is the harness's degraded-truth
ladder: it shows that investigating wins by the real path, before any LLM. If
the canonical solver cannot land high, the rule is to investigate the GAME
(budget, costs, contract), not to tune the script.

These are OUR fixtures; the submission code is built from estimates with no
oracle access. Numbers are baked into the submitted program as literals.
"""

import numpy as np

SOURCE = "registros_clinicos_2019_2023"

_NAIVE_TEMPLATE = '''import numpy as np
import pandas as pd

MU = np.array({mu!r})
COV = np.array({cov!r})


def model(regime, n, seed):
    rng = np.random.default_rng(seed)
    if "dose" in regime.config:
        d = float(regime.config["dose"])
        mu_cond = MU[1:] + COV[1:, 0] / COV[0, 0] * (d - MU[0])
        cov_cond = COV[1:, 1:] - np.outer(COV[1:, 0], COV[0, 1:]) / COV[0, 0]
        draw = rng.multivariate_normal(mu_cond, cov_cond, n)
        dose = np.full(n, d)
        marker = draw[:, 0]
        outcome = draw[:, 1]
    else:
        draw = rng.multivariate_normal(MU, COV, n)
        dose = np.clip(draw[:, 0], 0.0, 10.0)
        marker = draw[:, 1]
        outcome = draw[:, 2]
    return pd.DataFrame({{"dose": dose, "marker": marker, "outcome": outcome}})
'''

_CANONICAL_TEMPLATE = '''import numpy as np
import pandas as pd

A = {A!r}      # saturating dose response: A*d/(d+B)
B = {B!r}
HS = {HS!r}    # severity effect on outcome (severity is a posited latent)
SO = {SO!r}    # outcome noise sd
SM = {SM!r}    # marker measurement-noise sd (marker = severity + noise)
AA = {AA!r}    # observational dose assignment: dose = AA + BB*severity + noise
BB = {BB!r}
DE = {DE!r}


def _response(d):
    return A * d / (d + B)


def model(regime, n, seed):
    rng = np.random.default_rng(seed)
    cohort = regime.context.get("cohort", 0.0)
    severity = rng.normal(cohort, 1.0, n)
    marker = severity + rng.normal(0.0, SM, n)
    if "dose" in regime.config:
        dose = np.full(n, float(regime.config["dose"]))
    else:
        dose = np.clip(AA + BB * severity + rng.normal(0.0, DE, n), 0.0, 10.0)
    outcome = _response(dose) + HS * severity + rng.normal(0.0, SO, n)
    return pd.DataFrame({{"dose": dose, "marker": marker, "outcome": outcome}})
'''


def solver_naive(env):
    """Believe the data: fit the observational joint, submit it."""
    obs = env.observe(SOURCE, 2000)
    mu = obs[["dose", "marker", "outcome"]].mean().to_numpy()
    cov = obs[["dose", "marker", "outcome"]].cov().to_numpy()
    code = _NAIVE_TEMPLATE.format(
        mu=[float(x) for x in mu],
        cov=[[float(v) for v in row] for row in cov],
    )
    return env.submit(code)


def solver_canonical(env):
    """Investigate: separate causal dose-response from confounding via do(dose)."""
    from scipy.optimize import curve_fit

    obs = env.observe(SOURCE, 1500)
    var_marker = float(obs["marker"].var())
    sm = float(np.sqrt(max(var_marker - 1.0, 0.01)))  # var(severity) posited = 1

    # observational dose assignment, recovered with marker as severity proxy:
    # cov(dose, marker) = b * var(severity) = b  (no attenuation in the cov)
    bb = float(np.cov(obs["dose"], obs["marker"])[0, 1])
    aa = float(obs["dose"].mean() - bb * obs["marker"].mean())
    de = float(np.sqrt(max(obs["dose"].var() - bb**2, 0.01)))

    # experiments: do(dose=d) breaks the assignment; read causal response + hs
    doses = [1.0, 3.0, 5.0, 7.0, 9.0]
    g_points, hs_list, so_list = [], [], []
    for d in doses:
        ex = env.experiment(config={"dose": d}, context={"cohort": 0.0}, n=600)
        g_points.append(float(ex["outcome"].mean()))  # cohort 0 -> mean = response(d)
        hs_list.append(float(np.cov(ex["marker"], ex["outcome"])[0, 1]))  # = hs*var(sev)
        so_list.append(float(ex["outcome"].var()))
    hs = float(np.mean(hs_list))
    so = float(np.sqrt(max(np.mean(so_list) - hs**2, 0.01)))

    # fit the saturating response A*d/(d+B) to the experiment means
    def hill(d, a, b):
        return a * d / (d + b)

    try:
        popt, _ = curve_fit(hill, np.array(doses), np.array(g_points), p0=[10.0, 4.0], maxfev=10000)
        A, Bp = float(popt[0]), float(popt[1])
    except Exception:  # noqa: BLE001
        A, Bp = float(max(g_points)), 4.0

    code = _CANONICAL_TEMPLATE.format(A=A, B=Bp, HS=hs, SO=so, SM=sm, AA=aa, BB=bb, DE=de)
    return env.submit(code)
