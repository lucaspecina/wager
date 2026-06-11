"""Slice 1 deliverables for dummy_dose_v0 (NORTH_STAR Decision Log v0.10/v0.11).

Produces, end to end through the reward path:
  - the full L1 ladder: R of every rung + adjacent margins (in normalized-R
    units) + pass/fail at the 5% margin;
  - the L2 variance report: CV over R at the mid rung, CV of S_truth, the
    world-side / model-side decomposition, and the K x n x m cost in seconds.

Run:  .venv/Scripts/python cases/dummy_dose_v0/run_slice.py
"""

from pathlib import Path

from wager.factory.case_loader import (
    load_battery,
    load_ladder,
    load_meta,
    load_world_sample,
    load_world_source,
)
from wager.reward.ladder import DEFAULT_MARGIN, run_ladder
from wager.reward.variance import run_variance_protocol

CASE_DIR = Path(__file__).parent


def main() -> None:
    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    world_source = load_world_source(CASE_DIR)
    ladder = load_ladder(CASE_DIR)
    rungs = dict(ladder)
    params = meta.scoring

    print("=" * 70)
    print(f"SLICE 1 DELIVERABLES - {meta.case_id} (suite: {meta.suite})")
    print(f"battery K={len(battery.items)} items, n={params.n_samples}, "
          f"m={params.m_reps}, lambda={params.lambda_mdl:.3e} (provisional)")
    print("=" * 70)

    # ---- L1: full ladder ------------------------------------------------
    l1 = run_ladder(
        world_sample=world_sample,
        world_source=world_source,
        ladder=ladder,
        battery=battery,
        columns=meta.column_names,
        params=params,
        margin_required=DEFAULT_MARGIN,
        case_id=meta.case_id,
    )
    print("\n[L1] DEGRADED-TRUTH LADDER (R of every rung)")
    print(f"  anchors: S_truth={l1.anchors.s_truth:+.5f}  "
          f"S_naive={l1.anchors.s_naive:+.5f}  S_null={l1.anchors.s_null:+.5f}")
    print(f"  normalization range (S_truth - S_naive) = {l1.anchors.normalization_range:.5f}")
    print(f"  null range (diagnostic, S_truth - S_null) = {l1.anchors.null_range:.5f}")
    print(f"  margin required = {l1.margin_required:.0%} of normalization range")
    print("  anchors (R fixed by construction) vs measurements are marked in 'kind'\n")
    print(f"  {'rung':<26s}{'raw':>11s}{'R':>7s}{'R_uncl':>8s}{'margin':>9s}  kind")
    for rung in l1.rungs:
        margin = "-" if rung.margin_to_next is None else f"{rung.margin_to_next:+.4f}"
        flag = ""
        if rung.margin_to_next is not None and rung.margin_to_next < l1.margin_required:
            flag = "  < MARGIN"
        print(f"  {rung.name:<26s}{rung.raw_score:>11.5f}{rung.r:>7.3f}"
              f"{rung.r_unclipped:>8.3f}{margin:>9s}  {rung.kind}{flag}")
    print(f"\n  L1 PASSED = {l1.passed}   "
          f"(wall {l1.cost.wall_seconds:.1f}s, K*n*m = "
          f"{l1.cost.k_items}*{l1.cost.n_samples}*{l1.cost.m_reps})")

    # ---- L2: variance protocol -----------------------------------------
    print("\n[L2] REWARD VARIANCE PROTOCOL (mid rung = rung_3_linearized)")
    l2 = run_variance_protocol(
        world_sample=world_sample,
        world_source=world_source,
        naive_code=rungs["rung_5_naive_fit"],
        null_code=rungs["rung_6_null"],
        rung_code=rungs["rung_3_linearized"],
        rung_name="rung_3_linearized",
        battery=battery,
        columns=meta.column_names,
        params=params,
        b_total=20,
        b_model_side=10,
        case_id=meta.case_id,
    )
    print(f"  R (production seeds)      = {l2.r_production:.4f}")
    print(f"  CV(R) over {l2.b_total} resampled seed-sets = {l2.cv_r:.4f}"
          f"   (target < {DEFAULT_MARGIN:.0%})  "
          f"{'PASS' if l2.cv_r < DEFAULT_MARGIN else 'FAIL'}")
    print(f"  CV(S_truth) (R denominator)            = {l2.cv_s_truth:.4f}")
    print(f"  std(R) total                           = {l2.total_std:.4f}")
    print(f"  std(R) model-side only (world fixed)   = {l2.model_side_std:.4f}")
    print(f"  std(R) world-side remainder            = {l2.world_side_std:.4f}")
    print(f"  L2 cost: wall {l2.cost.wall_seconds:.1f}s for "
          f"{l2.b_total} full + {l2.b_model_side} model-side resamples")
    print("=" * 70)


if __name__ == "__main__":
    main()
