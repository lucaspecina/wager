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

from wager.contracts import ScoringParams
from wager.reward.scorer import WorldSide, score_callable


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
) -> dict:
    """theory_gap: truth vs the best NO-LATENT model (fit with full data access,
    incl. interventions). mechanistic_gap: truth vs the best ASSOCIATIONAL model
    (OBSERVATIONAL data only -- 'what curve-fitting the data gives'; ARCHITECTURE
    §7). The two references differ in DATA ACCESS, not just structure."""
    s_truth = score_callable(world_sample, world_side, params)
    s_naive = score_callable(naive_rival, world_side, params)
    s_no_latent = score_callable(no_latent_rival, world_side, params)
    assoc_scores = {name: score_callable(fn, world_side, params) for name, fn in associational_rivals}

    def R(s):  # noqa: N802
        denom = s_truth - s_naive
        return (s - s_naive) / denom if denom > 0 else 0.0

    assoc = {"naive": s_naive, **assoc_scores}
    best_assoc_name = max(assoc, key=lambda k: assoc[k])

    return {
        "s_truth": s_truth,
        "s_naive": s_naive,
        "s_no_latent": s_no_latent,
        "R_no_latent": R(s_no_latent),
        "R_naive": R(s_naive),
        "R_associational": {k: R(v) for k, v in assoc_scores.items()},
        # certificates (R units = fraction of the truth-naive range)
        "theory_gap": _r(s_no_latent, s_truth, s_naive),
        "mechanistic_gap": _r(assoc[best_assoc_name], s_truth, s_naive),
        "best_associational": best_assoc_name,
    }
