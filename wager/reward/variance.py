"""L2 - reward variance protocol (ARCHITECTURE 13-L2, Decision Log v0.10).

With fixed production seeds the score is deterministic; the relevant noise is
how much the score depends on the luck of the chosen seeds. Protocol: re-score
the mid-ladder rung with B resampled seed-sets (world + model side) and report
CV of normalized R, CV of S_truth (the denominator of R), and the
decomposition into model-side-only noise (world fixed, reps shifted) vs the
world-side remainder.
"""

import math
import time
from typing import Callable

import numpy as np

from wager.contracts import Battery, BatteryItem, ScoringCost, ScoringParams, VarianceReport
from wager.reward.sandbox import SandboxedSubmission
from wager.reward.scorer import WorldSide, sandboxed_null_sample, score_submission
from wager.reward.seeds import derive_world_seed

_REP_BLOCK = 1000  # rep offset stride per resample; >> m_reps so blocks never overlap


def _resampled_battery(battery: Battery, resample: int) -> Battery:
    items = [
        BatteryItem(
            weight=item.weight,
            regime=item.regime,
            seed_world=derive_world_seed(item.seed_world, idx, resample),
        )
        for idx, item in enumerate(battery.items)
    ]
    return Battery(items=items)


def run_variance_protocol(
    world_sample: Callable,
    world_source: str,
    naive_code: str,
    null_code: str,
    rung_code: str,
    rung_name: str,
    battery: Battery,
    columns: list[str],
    params: ScoringParams,
    b_total: int = 20,
    b_model_side: int = 10,
    case_id: str = "",
) -> VarianceReport:
    t0 = time.perf_counter()

    with (
        SandboxedSubmission(world_source, columns, timeout_s=params.model_call_timeout_s) as sb_truth,
        SandboxedSubmission(naive_code, columns, timeout_s=params.model_call_timeout_s) as sb_naive,
        SandboxedSubmission(rung_code, columns, timeout_s=params.model_call_timeout_s) as sb_mid,
        sandboxed_null_sample(null_code, columns, params.model_call_timeout_s) as null_sample,
    ):

        def world_side_of(bat: Battery) -> WorldSide:
            return WorldSide(world_sample, bat, columns, params.n_samples, null_sample=null_sample)

        def anchored_r(world_side: WorldSide, rep_offset: int) -> tuple[float, float]:
            s_truth = score_submission(
                world_source, world_side, params, sandbox=sb_truth, rep_offset=rep_offset
            ).raw_score
            s_naive = score_submission(
                naive_code, world_side, params, sandbox=sb_naive, rep_offset=rep_offset
            ).raw_score
            s_mid = score_submission(
                rung_code, world_side, params, sandbox=sb_mid, rep_offset=rep_offset
            ).raw_score
            denom = s_truth - s_naive
            if denom <= 0:
                raise ValueError("s_truth - s_naive <= 0 under resampled seeds")
            r = min(max((s_mid - s_naive) / denom, 0.0), 1.0)
            return r, s_truth

        world_side_prod = world_side_of(battery)
        r_production, _ = anchored_r(world_side_prod, rep_offset=0)

        # Full resamples: world-side seeds AND model-side reps both redrawn.
        r_values: list[float] = []
        s_truth_values: list[float] = []
        for b in range(1, b_total + 1):
            world_side_b = world_side_of(_resampled_battery(battery, b))
            r_b, s_truth_b = anchored_r(world_side_b, rep_offset=b * _REP_BLOCK)
            r_values.append(r_b)
            s_truth_values.append(s_truth_b)

        # Model-side only: world side fixed at production, reps shifted.
        r_values_model: list[float] = []
        for b in range(1, b_model_side + 1):
            r_b, _ = anchored_r(world_side_prod, rep_offset=b * _REP_BLOCK)
            r_values_model.append(r_b)

    r_arr = np.array(r_values)
    s_truth_arr = np.array(s_truth_values)
    r_model_arr = np.array(r_values_model)
    total_std = float(r_arr.std(ddof=1))
    model_side_std = float(r_model_arr.std(ddof=1))
    world_side_std = math.sqrt(max(total_std**2 - model_side_std**2, 0.0))

    return VarianceReport(
        case_id=case_id,
        rung_name=rung_name,
        r_production=r_production,
        b_total=b_total,
        r_values=[float(v) for v in r_values],
        cv_r=float(r_arr.std(ddof=1) / abs(r_arr.mean())),
        s_truth_values=[float(v) for v in s_truth_values],
        cv_s_truth=float(s_truth_arr.std(ddof=1) / abs(s_truth_arr.mean())),
        b_model_side=b_model_side,
        r_values_model_side=[float(v) for v in r_values_model],
        total_std=total_std,
        model_side_std=model_side_std,
        world_side_std=world_side_std,
        cost=ScoringCost(
            k_items=len(battery.items),
            n_samples=params.n_samples,
            m_reps=params.m_reps,
            wall_seconds=time.perf_counter() - t0,
        ),
    )
