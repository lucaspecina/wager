"""mendel_subtypes_v0 - latent subtype heterogeneity with opposite dose effects.

The truth of the case. Server-side only: the agent never sees this file.

Suite Mendel (latent constructs). CONTRAST with dummy_dose_v0: the dummy is a
CONFOUNDING trap (a no-latent model with interventional data recovers R~=0.94 --
the latent severity only biases assignment). Mendel is a LATENT-HETEROGENEITY
trap: two subtypes whose dose effect has OPPOSITE SIGN, so the correct policy
depends on the subtype composition of the population, and a model restricted to
unimodal generation over observables cannot reproduce the two-cluster joint.

Mechanism (all mechanism layer):

    Z        ~ Bernoulli(sigmoid(mix_logit))      # latent subtype, never observed
    marker   := marker_sep * Z + Normal(0, marker_noise)   # bimodal: REVEALS Z
    dose     := clip(dose_base + sub_coef_dose*Z + Normal(0,dose_noise), 0, 10)
                (replaced by the constant regime.config["dose"] under do())
    effect   := effect_responder if Z==0 else effect_paradox   # OPPOSITE SIGNS
    base     := base_responder   if Z==0 else base_paradox
    outcome  := base + effect * dose + Normal(0, outcome_noise)

Two operators (declared in meta.json with their ablation = "off" value):
  - heterogeneidad_latente: the sign flip (effect_paradox<0). Ablated -> both
    subtypes share the responder slope (homogeneous world; the innocent twin
    that "never saw the heterogeneity").
  - confounding_por_subtipo: Z drives the observational dose assignment (the
    paradoxical subtype, looking sicker via the marker, historically got MORE
    dose). Ablated -> assignment independent of Z.

The investigative insight rewarded: discover that the biomarker is BIMODAL, that
it indexes two subtypes with opposite dose-response, and condition the policy on
it. A clinician who averages over subtypes (no-latent) misprices the dose badly.

sample() = mechanism(PARAMS, ...): the S_truth anchor (R(world.py) == 1 by
construction -- it runs through the same pipeline as any submission).
"""

import numpy as np
import pandas as pd

COLUMNS = ["dose", "marker", "outcome"]

# Structured mechanism (Decision Log v0.18 pattern): truth = mechanism(PARAMS,...);
# the factory derives ladder rungs / innocent twins by perturbing or ablating
# these params (operator -> param mapping in meta.json), without reading this file.
# Constants chosen so the heterogeneity is IRREDUCIBLE to a unimodal model (the
# theory-gap probe's symmetric reading, Decision Log v0.25, showed an earlier
# draft -- base_paradox=3 + slopes +-1 -- made the two subtypes CROSS near dose 2,
# collapsing the separation; the residual gap was then dominated by HETEROSCEDAS-
# TICITY, which a stronger no-latent rival could fix = a weak-rival artifact, the
# v0.18 trap). Fix: base_paradox=base_responder=0 + strong opposite slopes + tight
# noise, so at any dose>0 the two outcome clusters are cleanly SEPARATED (two
# modes a unimodal model cannot make, however well it fits mean+variance), and the
# biomarker is cleanly bimodal at all doses. The decisive control is a moment-
# matched Gaussian oracle (theory_gap_probe.py): if it fails, the gap is the modes.
PARAMS = {
    "marker_sep": 5.0,        # heterogeneidad_latente: subtype separation in the biomarker
    "marker_noise": 1.0,      # within-subtype marker spread (5-sigma clusters: clean, discoverable)
    "effect_responder": 1.5,  # heterogeneidad_latente: responder dose slope (+)
    "effect_paradox": -1.5,   # heterogeneidad_latente: paradoxical dose slope (-); ablation -> +1.5
    "base_responder": 0.0,
    "base_paradox": 0.0,      # no baseline offset -> no mid-dose cross-over; separation grows with dose
    "outcome_noise": 0.5,
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
    base = np.where(z > 0.5, p["base_paradox"], p["base_responder"])
    outcome = base + effect * dose + rng.normal(0.0, p["outcome_noise"], n)

    return pd.DataFrame({"dose": dose, "marker": marker, "outcome": outcome})


def sample(regime, n, seed):
    return mechanism(PARAMS, regime, n, seed)


model = sample
