"""Verify the scale incoherence that motivates the universal D_MAX cap (b').

Question (Lucas): on the derived battery, does the UNCAPPED naive distance at
high-dose items exceed D_MAX? If so, a crash-everywhere submission (D_MAX on every
item) would score ABOVE the R=0 floor -- broken scale. Report per-item D_MAX vs the
naive's distance (and whether it is being capped), and R(crash-everywhere).

Run:  .venv/Scripts/python cases/dummy_dose_v0/verify_cap.py
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).parent
sys.path.insert(0, str(CASE_DIR))

from wager.factory.battery_builder import build_battery
from wager.factory.case_loader import (
    load_ladder, load_meta, load_world_module, load_world_sample, load_world_source,
)
from wager.factory.derive_rivals import (
    best_no_latent, experimental_grid, observational_pool, rival_naive, rival_twin,
)
from wager.reward.scorer import WorldSide, make_anchors, sandboxed_null_sample, score_submission

CRASH = "def model(regime, n, seed):\n raise RuntimeError('crash')\n"


def main():
    meta = load_meta(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    world_source = load_world_source(CASE_DIR)
    ladder = dict(load_ladder(CASE_DIR))
    cols, params = meta.column_names, meta.scoring

    pool = observational_pool(world_sample, list(meta.episode.observe_sources.values())[0], 4000, 50001)
    train = experimental_grid(world_sample, "dose", list(range(0, 11)), [-1.5, 0.0, 1.5], 300, 60001)
    wmod = load_world_module(CASE_DIR)
    conf = next(op for op in meta.operators if op.name == "confounding_por_indicacion")
    twin = rival_twin(wmod.mechanism, wmod.PARAMS, conf.ablation, pool)
    rivals = [rival_naive(pool), best_no_latent(train, pool), twin]
    nl_ns: dict = {}
    exec(ladder["rung_6_null"], nl_ns)
    battery = build_battery(world_sample, rivals, nl_ns["model"], cols, meta.stakes.decision_variables)

    with sandboxed_null_sample(ladder["rung_6_null"], cols, params.model_call_timeout_s) as null_sample:
        ws = WorldSide(world_sample, battery, cols, params.n_samples, null_sample=null_sample)
        rep_naive = score_submission(ladder["rung_5_naive_fit"], ws, params)
        rep_truth = score_submission(world_source, ws, params)
        rep_crash = score_submission(CRASH, ws, params)

    anchors = make_anchors(rep_truth.raw_score, rep_naive.raw_score,
                           score_submission_null(ladder, ws, params))
    r_crash, r_crash_uncl = anchors.r_of(rep_crash.raw_score)

    print("=" * 78)
    print("CAP VERIFICATION -- derived battery (high-dose-heavy)")
    print("=" * 78)
    print(f"  {'item':>4} {'dose':>6} {'w':>6} {'d_max':>9} {'naive_d':>9} {'capped?':>8}")
    for it, bi in zip(rep_naive.items, battery.items):
        dose = bi.regime.config.get("dose")
        ds = "obs" if dose is None else f"{dose:.1f}"
        flag = "CAPPED" if it.capped_reps > 0 else ""
        print(f"  {it.index:>4} {ds:>6} {it.weight:>6.3f} {it.d_max:>9.3f} "
              f"{it.mean_distance:>9.3f} {flag:>8}")
    n_capped = sum(1 for it in rep_naive.items if it.capped_reps > 0)
    print("-" * 78)
    print(f"  naive capped at D_MAX on {n_capped}/{len(rep_naive.items)} items "
          f"(uncapped naive exceeds D_MAX where CAPPED)")
    print(f"  S_truth={rep_truth.raw_score:+.4f}  S_naive={rep_naive.raw_score:+.4f}  "
          f"denom={anchors.normalization_range:.4f}")
    print(f"  R(crash-everywhere) = {r_crash:.3f}  (R_uncl={r_crash_uncl:+.3f})")
    print("  INCOHERENCE" if r_crash_uncl > 0 else "  floor sound: R(crash) <= 0", "(crash vs naive)")
    print("=" * 78)


def score_submission_null(ladder, ws, params):
    return score_submission(ladder["rung_6_null"], ws, params).raw_score


if __name__ == "__main__":
    main()
