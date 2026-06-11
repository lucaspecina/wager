"""dummy_dose_v0 - SCM with confounding-by-indication + saturating dose response.

The truth of the case. Server-side only: the agent never sees this file.

Mechanism (all three structural equations are mechanism layer; the confounded
dose assignment is the world's own assignment process, which do(dose)
replaces - Decision Log v0.11):

    severity ~ Normal(cohort, 1)                   # latent, never observed
    dose     := clip(2.0 + 1.5*severity + eta, 0, 10)   # natural assignment
                (replaced by the constant regime.config["dose"] under do())
    outcome  := 1.0 * sat(dose) - 2.0 * severity + eps
    marker   := severity + nu                       # noisy severity proxy
    sat(d)   = 10*d / (d + 4)                       # saturating response

Canonical knobs chosen so the trap bites: severity drives BOTH dose and
(negatively) outcome, so the naive observational dose-outcome association is
strongly biased downward versus the causal effect.

This file is also a valid submission (model = sample): the S_truth anchor is
computed by running it through the exact same pipeline as any submission, so
R(world.py) == 1.0 holds exactly by construction (Decision Log v0.11).
"""

import numpy as np
import pandas as pd

COLUMNS = ["dose", "marker", "outcome"]

# Structured mechanism (Decision Log v0.18): the truth is mechanism(PARAMS, ...);
# the factory derives ladder rungs and innocent twins by perturbing or ablating
# these params (operator -> param mapping declared in meta.json). meta declares,
# per operator, the param keys it controls and their "off" values, so the
# derivation can render the world with one operator ablated WITHOUT introspecting
# this file by hand. sample() = mechanism(PARAMS, ...) (the S_truth anchor).
PARAMS = {
    "sev_coef_dose": 1.5,   # confounding_por_indicacion: severity -> dose
    "dose_base": 2.0,
    "dose_noise": 1.0,
    "sat_scale": 10.0,      # umbral_no_lineal: saturating response shape
    "sat_half": 4.0,
    "effect_dose": 1.0,
    "effect_sev": -2.0,
    "outcome_noise": 0.5,
    "marker_noise": 1.5,
}
DOSE_MIN, DOSE_MAX = 0.0, 10.0


def _response(dose, p):
    # Hill/saturating; sat_half -> large makes it ~linear (the operator's "off")
    return p["sat_scale"] * dose / (dose + p["sat_half"])


def mechanism(params, regime, n, seed):
    p = params
    rng = np.random.default_rng(seed)
    cohort = regime.context.get("cohort", 0.0)
    severity = rng.normal(cohort, 1.0, n)
    if "dose" in regime.config:
        dose = np.full(n, float(regime.config["dose"]))
    else:
        raw = p["dose_base"] + p["sev_coef_dose"] * severity + rng.normal(0.0, p["dose_noise"], n)
        dose = np.clip(raw, DOSE_MIN, DOSE_MAX)
    outcome = (
        p["effect_dose"] * _response(dose, p)
        + p["effect_sev"] * severity
        + rng.normal(0.0, p["outcome_noise"], n)
    )
    marker = severity + rng.normal(0.0, p["marker_noise"], n)
    return pd.DataFrame({"dose": dose, "marker": marker, "outcome": outcome})


def sample(regime, n, seed):
    return mechanism(PARAMS, regime, n, seed)


model = sample
