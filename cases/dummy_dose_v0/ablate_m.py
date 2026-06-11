"""Ablation of m (model-side reps) for dummy_dose_v0 (Decision Log v0.12 item 2).

The L2 decomposition showed the model side contributes ~7% of the reward
variance (std 0.0021 of 0.0079) at m=5 -> m=5 is over-provisioned. This re-runs
the L2 variance protocol for m in {2, 3, 5} and reports CV(R) and wall cost, so
the cheapest m that still clears CV(R) < 5% becomes the v0 default.

Run:  .venv/Scripts/python cases/dummy_dose_v0/ablate_m.py
"""

from pathlib import Path

from wager.factory.case_loader import (
    load_battery,
    load_ladder,
    load_meta,
    load_world_sample,
    load_world_source,
)
from wager.reward.variance import run_variance_protocol

CASE_DIR = Path(__file__).parent
CV_TARGET = 0.05
B_TOTAL = 20
B_MODEL_SIDE = 10


def main() -> None:
    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    world_source = load_world_source(CASE_DIR)
    rungs = dict(load_ladder(CASE_DIR))

    print(f"ablation of m (K={len(battery.items)}, n={meta.scoring.n_samples}, "
          f"B_total={B_TOTAL}); CV target < {CV_TARGET:.0%} on R")
    print(f"  {'m':>3s}{'CV(R)':>9s}{'CV(S_truth)':>13s}{'std_model':>11s}"
          f"{'std_world':>11s}{'wall_s':>9s}")
    for m in (2, 3, 5):
        params = meta.scoring.model_copy(update={"m_reps": m})
        rep = run_variance_protocol(
            world_sample=world_sample,
            world_source=world_source,
            naive_code=rungs["rung_5_naive_fit"],
            null_code=rungs["rung_6_null"],
            rung_code=rungs["rung_3_linearized"],
            rung_name="rung_3_linearized",
            battery=battery,
            columns=meta.column_names,
            params=params,
            b_total=B_TOTAL,
            b_model_side=B_MODEL_SIDE,
            case_id=meta.case_id,
        )
        flag = "PASS" if rep.cv_r < CV_TARGET else "FAIL"
        print(f"  {m:>3d}{rep.cv_r:>9.4f}{rep.cv_s_truth:>13.4f}"
              f"{rep.model_side_std:>11.4f}{rep.world_side_std:>11.4f}"
              f"{rep.cost.wall_seconds:>9.1f}  {flag}")


if __name__ == "__main__":
    main()
