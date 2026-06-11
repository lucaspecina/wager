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

SEV_COEF_DOSE = 1.5
DOSE_BASE = 2.0
DOSE_NOISE = 1.0
DOSE_MIN = 0.0
DOSE_MAX = 10.0
SAT_SCALE = 10.0
SAT_HALF = 4.0
EFFECT_DOSE = 1.0
EFFECT_SEV = -2.0
OUTCOME_NOISE = 0.5
MARKER_NOISE = 1.5


def _saturating(dose):
    return SAT_SCALE * dose / (dose + SAT_HALF)


def sample(regime, n, seed):
    rng = np.random.default_rng(seed)
    cohort = regime.context.get("cohort", 0.0)
    severity = rng.normal(cohort, 1.0, n)
    if "dose" in regime.config:
        dose = np.full(n, float(regime.config["dose"]))
    else:
        raw = DOSE_BASE + SEV_COEF_DOSE * severity + rng.normal(0.0, DOSE_NOISE, n)
        dose = np.clip(raw, DOSE_MIN, DOSE_MAX)
    outcome = (
        EFFECT_DOSE * _saturating(dose)
        + EFFECT_SEV * severity
        + rng.normal(0.0, OUTCOME_NOISE, n)
    )
    marker = severity + rng.normal(0.0, MARKER_NOISE, n)
    return pd.DataFrame({"dose": dose, "marker": marker, "outcome": outcome})


model = sample
