"""mendel_subtypes_v1 - latent subtype heterogeneity, GENUINE latent (v0.27 Q5).

The truth of the case. Server-side only: the agent never sees this file.

Contrast with mendel_subtypes_v0 (the negative control): v0's biomarker was CLEAN
(5-sigma separated) -> the subtype was fully proxied by an observable, so a
flexible conditional learner P(outcome|dose,marker) recovers everything and the
theory gap is small EVEN with functionals (Decision Log v0.27). v1 makes the
latent genuine on three axes:
  (a) the biomarker is NOISY with overlap (marker_sep 2.2 / noise 1.5 ~ 1.5-sigma):
      the subtype must be INFERRED from the mixture, not read off one row;
  (b) the biomarker is ABSENT from the cheap observational source -- it must be
      bought (buy_instrument, declared in meta); and
  (c) the history lives at a SINGLE population mix (mix_logit=0); the battery
      probes mix shifts OUTSIDE that support, where a conditional-on-observables
      learner (fit at the historical mix) extrapolates wrong, but a model that
      POSITS the invariant subtype laws + a varying mixing weight survives.
The theory gap of v1 thus measures REPRESENTATION (positing the mixture), not
multimodality. The v0/v1 pair is the control (pre-reg replacing P2, v0.27).

Mechanism (all mechanism layer):

    Z      ~ Bernoulli(sigmoid(mix_logit))          # latent subtype (never observed directly)
    marker := marker_sep * Z + Normal(0, marker_noise)   # NOISY proxy (overlap); bought, not free
    dose   := clip(dose_base + sub_coef_dose*Z + Normal(0,dose_noise), 0, 10)
              (replaced by the constant regime.config["dose"] under do())
    effect := effect_responder if Z==0 else effect_paradox   # OPPOSITE SIGNS
    outcome:= effect * dose + Normal(0, outcome_noise)

Two operators (declared in meta.json with their ablation = "off" value):
  - heterogeneidad_latente: the sign flip (effect_paradox<0). Ablated -> both
    subtypes share the responder slope (homogeneous; the innocent twin).
  - confounding_por_subtipo: Z drives the observational dose assignment. Ablated
    -> assignment independent of Z.

sample() = mechanism(PARAMS, ...): the S_truth anchor (R(world.py)==1).
"""

import numpy as np
import pandas as pd

COLUMNS = ["dose", "marker", "outcome"]

PARAMS = {
    "marker_sep": 2.2,        # heterogeneidad_latente: subtype separation in the biomarker
    "marker_noise": 1.5,      # OVERLAP (~1.5-sigma): infer the subtype, don't read it
    "effect_responder": 1.5,  # heterogeneidad_latente: responder dose slope (+)
    "effect_paradox": -1.5,   # heterogeneidad_latente: paradoxical slope (-); ablation -> +1.5
    "outcome_noise": 0.6,
    "dose_base": 4.0,         # confounding_por_subtipo: natural assignment center
    "dose_noise": 1.2,
    "sub_coef_dose": 2.5,     # confounding_por_subtipo: Z -> dose; ablation -> 0.0
}
DOSE_MIN, DOSE_MAX = 0.0, 10.0


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def mechanism(params, regime, n, seed):
    p = params
    rng = np.random.default_rng(seed)
    mix_logit = float(regime.context.get("mix_logit", 0.0))
    z = rng.binomial(1, _sigmoid(mix_logit), n).astype(float)  # latent subtype

    marker = p["marker_sep"] * z + rng.normal(0.0, p["marker_noise"], n)

    if "dose" in regime.config:
        dose = np.full(n, float(regime.config["dose"]))
    else:
        raw = p["dose_base"] + p["sub_coef_dose"] * z + rng.normal(0.0, p["dose_noise"], n)
        dose = np.clip(raw, DOSE_MIN, DOSE_MAX)

    effect = np.where(z > 0.5, p["effect_paradox"], p["effect_responder"])
    outcome = effect * dose + rng.normal(0.0, p["outcome_noise"], n)

    return pd.DataFrame({"dose": dose, "marker": marker, "outcome": outcome})


def sample(regime, n, seed):
    return mechanism(PARAMS, regime, n, seed)


model = sample
