"""Computable per-case certificates (ARCHITECTURE §7, factory side).

All in FIDELITY space (no MDL -- rivals are callables), normalized to R units by
the rival anchors so they compare across worlds:
    R(x) = (S_x - S_naive) / (S_truth - S_naive)

- theory_gap  = S_truth - S(best no-latent rival d)  -> in R: 1 - R(no_latent).
  The pressure to invent latent constructs (Decision Log v0.17). Prediction:
  dummy small (~0.1), Mendel large.
- mechanistic_gap = S_truth - S(best no-mechanism associational rival) -> in R:
  1 - max R over {naive, capacity ladder}. The pressure to investigate (curve
  fitting loses).
"""

from typing import Callable

import numpy as np

from wager.contracts import ScoringParams
from wager.reward.scorer import WorldSide, regime_to_namespace, score_callable
from wager.reward.seeds import derive_seed


def _r(s: float, s_truth: float, s_naive: float) -> float:
    denom = s_truth - s_naive
    if denom <= 0:
        return 0.0
    return (s_truth - s) / denom  # = 1 - R(s); the "gap to truth" in R units


def compute_certificates(
    world_sample: Callable,
    naive_rival: Callable,
    no_latent_rival: Callable,
    associational_rivals: list[tuple[str, Callable]],
    world_side: WorldSide,
    params: ScoringParams,
    prior_rival: Callable | None = None,
) -> dict:
    """theory_gap: truth vs the best NO-LATENT model (fit with full data access,
    incl. interventions). mechanistic_gap: truth vs the best ASSOCIATIONAL model
    (OBSERVATIONAL data only -- 'what curve-fitting the data gives'; ARCHITECTURE
    §7). prior_gap: truth vs the prior-evoked rival (c) -- low => the prior already
    knows the world (contamination, attack #16). The references differ in DATA
    ACCESS, not just structure.

    Note (Decision Log v0.19): in R units mechanistic_gap == R(mechanistic
    reference) because naive is the 0 anchor; the substantive 'does this world
    discriminate' measurement is the RAW denominator s_truth - s_naive vs the
    reward noise floor (report `denom_raw`, compare to the L2 CV)."""
    s_truth = score_callable(world_sample, world_side, params)
    s_naive = score_callable(naive_rival, world_side, params)
    s_no_latent = score_callable(no_latent_rival, world_side, params)
    assoc_scores = {name: score_callable(fn, world_side, params) for name, fn in associational_rivals}

    def R(s):  # noqa: N802
        denom = s_truth - s_naive
        return (s - s_naive) / denom if denom > 0 else 0.0

    assoc = {"naive": s_naive, **assoc_scores}
    best_assoc_name = max(assoc, key=lambda k: assoc[k])
    out = {
        "s_truth": s_truth,
        "s_naive": s_naive,
        "denom_raw": s_truth - s_naive,  # substantive discrimination scale
        "s_no_latent": s_no_latent,
        "R_no_latent": R(s_no_latent),
        "R_naive": R(s_naive),
        "R_associational": {k: R(v) for k, v in assoc_scores.items()},
        "theory_gap": _r(s_no_latent, s_truth, s_naive),
        "mechanistic_gap": _r(assoc[best_assoc_name], s_truth, s_naive),
        "best_associational": best_assoc_name,
    }
    if prior_rival is not None:
        s_prior = score_callable(prior_rival, world_side, params)
        out["s_prior"] = s_prior
        out["R_prior"] = R(s_prior)
        out["prior_gap"] = _r(s_prior, s_truth, s_naive)
    return out


def per_regime_reading(
    rival_fn: Callable, world_sample: Callable, world_side: WorldSide, params: ScoringParams
) -> list[dict]:
    """Per-item truth-vs-rival reading (means/std/corr + distance + crash flag).
    Applied SYMMETRICALLY to confirmatory and anomalous certificate values
    (Decision Log v0.19): investigating only contradictions is confirmation bias."""
    rows = []
    for idx, item in enumerate(world_side.battery.items):
        ns = regime_to_namespace(item.regime)
        truth_side = world_side.truth_sides[idx]
        d_max = world_side.d_maxes[idx]
        try:
            pred = rival_fn(ns, params.n_samples, derive_seed(item.seed_world, 0))
            dist = truth_side.distance_to(pred)
            crashed = False
        except Exception:  # noqa: BLE001
            pred, dist, crashed = None, d_max, True
        real = world_sample(ns, params.n_samples, item.seed_world)
        row = {
            "idx": idx,
            "weight": item.weight,
            "dose": item.regime.config.get("dose"),
            "cohort": item.regime.context.get("cohort", 0.0),
            "distance": float(dist),
            "d_max": float(d_max),
            "crashed": crashed,
        }
        if not crashed:
            for col in world_side.columns:
                row[f"truth_{col}_mean"] = float(real[col].mean())
                row[f"rival_{col}_mean"] = float(pred[col].mean())
        rows.append(row)
    return rows
