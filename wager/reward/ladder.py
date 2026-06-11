"""L1 - the degraded-truth ladder (ARCHITECTURE 13-L1).

Production certificate: monotonicity-per-axis + extremes. For the canonical
Slice 1 dummy, the TOTAL order with margins is the scorer acceptance test
(Decision Log v0.10/v0.11). If an order fails, the default is to investigate,
never to retune the degradations.

Convention: `ladder` lists rungs 2..N in canonical order; rung 1 is always
world.py itself, scored through the SAME pipeline as any submission (v0.11),
so its R is 1.0 exactly by construction. The second-to-last rung must be the
naive fit (anchor S_naive) and the last one the null model (anchor S_null).
"""

import time
from typing import Callable

from wager.contracts import (
    Battery,
    LadderReport,
    LadderRung,
    ScoringCost,
    ScoringParams,
)
from wager.reward.sandbox import SandboxedSubmission
from wager.reward.scorer import WorldSide, make_anchors, score_submission, sandboxed_null_sample

RUNG_TRUTH_NAME = "rung_1_truth(world.py)"
DEFAULT_MARGIN = 0.05  # 5% of (S_truth - S_null), Decision Log v0.10


def run_ladder(
    world_sample: Callable,
    world_source: str,
    ladder: list[tuple[str, str]],
    battery: Battery,
    columns: list[str],
    params: ScoringParams,
    margin_required: float = DEFAULT_MARGIN,
    case_id: str = "",
) -> LadderReport:
    t0 = time.perf_counter()
    rung_defs: list[tuple[str, str]] = [(RUNG_TRUTH_NAME, world_source)] + list(ladder)
    null_code = rung_defs[-1][1]  # last rung is the null model (anchors S_null)

    raw_scores: list[tuple[str, float]] = []
    with sandboxed_null_sample(null_code, columns, params.model_call_timeout_s) as null_sample:
        world_side = WorldSide(
            world_sample, battery, columns, params.n_samples, null_sample=null_sample
        )
        for name, code in rung_defs:
            with SandboxedSubmission(code, columns, timeout_s=params.model_call_timeout_s) as sb:
                report = score_submission(code, world_side, params, sandbox=sb)
            raw_scores.append((name, report.raw_score))

    anchors = make_anchors(
        s_truth=raw_scores[0][1],
        s_naive=raw_scores[-2][1],
        s_null=raw_scores[-1][1],
    )
    score_range = anchors.normalization_range  # S_truth - S_naive (Decision Log v0.12)
    if score_range <= 0:
        raise ValueError("S_truth - S_naive <= 0: the world does not discriminate")

    # Anchors by construction (Decision Log v0.12): rung 0 is world.py (=> S_truth,
    # R=1); the second-to-last rung is the naive fit and IS the S_naive anchor of
    # the normalization (rival (a); in production the same derived object, here the
    # bootstrap fixture); the last rung is the null (=> S_null, the D_MAX reference
    # and diagnostic floor). Everything between rung 0 and the naive rung is a
    # genuine measurement.
    last = len(raw_scores) - 1
    naive_idx = last - 1

    def _kind(i: int) -> str:
        if i == 0:
            return "anchor:S_truth"
        if i == naive_idx:
            return "anchor:S_naive"
        if i == last:
            return "reference:S_null"
        return "measurement"

    rungs: list[LadderRung] = []
    margins: list[float] = []
    for i, (name, raw) in enumerate(raw_scores):
        r, r_unclipped = anchors.r_of(raw)
        margin = None
        if i + 1 < len(raw_scores):
            margin = (raw - raw_scores[i + 1][1]) / score_range
            margins.append(margin)
        rungs.append(
            LadderRung(
                name=name,
                raw_score=raw,
                r=r,
                r_unclipped=r_unclipped,
                margin_to_next=margin,
                kind=_kind(i),
            )
        )

    return LadderReport(
        case_id=case_id,
        rungs=rungs,
        anchors=anchors,
        margin_required=margin_required,
        passed=all(m >= margin_required for m in margins),
        cost=ScoringCost(
            k_items=len(battery.items),
            n_samples=params.n_samples,
            m_reps=params.m_reps,
            wall_seconds=time.perf_counter() - t0,
        ),
    )
