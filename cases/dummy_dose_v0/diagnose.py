"""Diagnostic dump for the L1 ladder of dummy_dose_v0 (investigate, not retune).

Prints, per rung: raw score, R, and the per-item mean distance, so we can see
WHERE each rung wins or loses and why an ordering holds or breaks.
"""

from pathlib import Path

import numpy as np

from wager.contracts import ScoringParams
from wager.factory.case_loader import (
    load_battery,
    load_ladder,
    load_meta,
    load_world_sample,
    load_world_source,
)
from wager.reward.scorer import WorldSide, make_anchors, sandboxed_null_sample, score_submission

CASE_DIR = Path(__file__).parent


def main() -> None:
    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    world_source = load_world_source(CASE_DIR)
    ladder = dict(load_ladder(CASE_DIR))
    params = ScoringParams(
        lambda_mdl=meta.scoring.lambda_mdl, n_samples=1000, m_reps=5,
    )
    null_code = ladder["rung_6_null"]
    with sandboxed_null_sample(null_code, meta.column_names, params.model_call_timeout_s) as null_sample:
        ws = WorldSide(
            world_sample, battery, meta.column_names, params.n_samples, null_sample=null_sample
        )

        rungs = {
            "1_truth": world_source,
            "2_perturbed": ladder["rung_2_perturbed"],
            "3_linearized": ladder["rung_3_linearized"],
            "4_twin": ladder["rung_4_innocent_twin"],
            "5_naive": ladder["rung_5_naive_fit"],
            "6_null": ladder["rung_6_null"],
        }
        reports = {name: score_submission(code, ws, params) for name, code in rungs.items()}
    anchors = make_anchors(
        reports["1_truth"].raw_score,
        reports["5_naive"].raw_score,
        reports["6_null"].raw_score,
    )

    print("per-item regime summary:")
    for i, item in enumerate(battery.items):
        cfg = item.regime.config.get("dose", "obs")
        ctx = item.regime.context.get("cohort", 0.0)
        print(f"  [{i:2d}] w={item.weight:.1f} dose={cfg} sev_mean={ctx} dmax={ws.d_maxes[i]:.4f}")

    print("\nraw scores and R:")
    for name, rep in reports.items():
        r, ru = anchors.r_of(rep.raw_score)
        print(f"  {name:14s} raw={rep.raw_score:+.5f}  R={r:.3f}  R_unclipped={ru:+.3f}")

    print("\nper-item mean distance (rows=item, cols=rung):")
    header = "  item  " + "".join(f"{n.split('_')[1]:>11s}" for n in rungs)
    print(header)
    for i in range(len(battery.items)):
        row = "".join(f"{reports[n].items[i].mean_distance:11.4f}" for n in rungs)
        cfg = battery.items[i].regime.config.get("dose", "obs")
        print(f"  {i:2d} d={str(cfg):>4s}{row}")

    print("\nweighted contribution per rung (sum = -fidelity):")
    for name, rep in reports.items():
        contribs = [it.weight * it.mean_distance for it in rep.items]
        print(f"  {name:14s} fid={rep.fidelity:+.5f}  top items: "
              + ", ".join(f"#{i}={c:.4f}" for i, c in sorted(enumerate(contribs), key=lambda x: -x[1])[:4]))


if __name__ == "__main__":
    main()
