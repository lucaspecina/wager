"""Per-item diagnostic of a submission (Decision Log v0.15 follow-up).

Answers the mandatory question for a clipped R=0: is the floor reached by D_MAX
(the submission CRASHES on battery items -> contract/robustness failure, cousin
of attack #17) or by HONEST distances (the model runs but is genuinely far ->
skill/structure gap)? Prints per-item mean distance, the D_MAX cap, crash count,
and how much of the (negative) fidelity comes from crashed vs honest items, plus
R and R_unclipped.

Usage:
  .venv/Scripts/python cases/dummy_dose_v0/diagnose_submission.py <trace.json>
  (reads result["submission_code"]; also accepts a label via 'world'/'naive'/'canonical')
"""

import json
import sys
from pathlib import Path

from wager.factory.case_loader import (
    load_battery,
    load_ladder,
    load_meta,
    load_world_sample,
    load_world_source,
)
from wager.reward.scorer import WorldSide, make_anchors, sandboxed_null_sample, score_submission

CASE_DIR = Path(__file__).parent


def _code_from_arg(arg: str) -> tuple[str, str]:
    ladder = dict(load_ladder(CASE_DIR))
    if arg == "world":
        return load_world_source(CASE_DIR), "world.py"
    if arg == "naive":
        return ladder["rung_5_naive_fit"], "naive_fit(rung5)"
    if arg == "null":
        return ladder["rung_6_null"], "null(rung6)"
    trace = json.loads(Path(arg).read_text(encoding="utf-8"))
    code = trace.get("submission_code")
    if not code:
        raise SystemExit(f"{arg} has no submission_code (re-run the episode to capture it)")
    return code, f"{trace.get('model')} seed-trace"


def main():
    arg = sys.argv[1]
    code, label = _code_from_arg(arg)
    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    ladder = dict(load_ladder(CASE_DIR))
    params = meta.scoring

    with sandboxed_null_sample(ladder["rung_6_null"], meta.column_names, params.model_call_timeout_s) as null_sample:
        ws = WorldSide(world_sample, battery, meta.column_names, params.n_samples, null_sample=null_sample)
        s_truth = score_submission(load_world_source(CASE_DIR), ws, params).raw_score
        s_naive = score_submission(ladder["rung_5_naive_fit"], ws, params).raw_score
        s_null = score_submission(ladder["rung_6_null"], ws, params).raw_score
        rep = score_submission(code, ws, params)
    anchors = make_anchors(s_truth, s_naive, s_null)
    r, r_uncl = anchors.r_of(rep.raw_score)

    print("=" * 78)
    print(f"DIAGNOSE: {label}")
    print(f"  R={r:.3f}  R_uncl={r_uncl:+.3f}  raw={rep.raw_score:+.4f}  "
          f"(S_truth={s_truth:+.4f} S_naive={s_naive:+.4f} S_null={s_null:+.4f})")
    print("=" * 78)
    crashed_contrib = honest_contrib = 0.0
    n_crash_items = 0
    print(f"  {'item':>4} {'dose':>6} {'cohort':>7} {'w':>5} {'mean_d':>9} {'d_max':>9} "
          f"{'crashes':>8} {'contrib':>9}")
    for it, bi in zip(rep.items, battery.items):
        dose = bi.regime.config.get("dose", None)
        cohort = bi.regime.context.get("cohort", 0.0)
        contrib = it.weight * it.mean_distance
        crashed = it.sandbox_errors > 0
        n_crash_items += crashed
        if crashed:
            crashed_contrib += contrib
        else:
            honest_contrib += contrib
        dose_s = "obs" if dose is None else f"{dose:.1f}"
        print(f"  {it.index:>4} {dose_s:>6} {cohort:>7.1f} {it.weight:>5.2f} "
              f"{it.mean_distance:>9.4f} {it.d_max:>9.4f} {it.sandbox_errors:>4}/{params.m_reps:<3} "
              f"{contrib:>9.4f}")
    total = crashed_contrib + honest_contrib
    print("-" * 78)
    print(f"  items with crashes: {n_crash_items}/{len(battery.items)}")
    print(f"  fidelity contribution: crashed items {crashed_contrib:.4f} "
          f"({100*crashed_contrib/total:.0f}%)  |  honest items {honest_contrib:.4f} "
          f"({100*honest_contrib/total:.0f}%)")
    verdict = ("DOMINATED BY CRASHES -> contract/robustness (attack #17 cousin)"
               if crashed_contrib > honest_contrib else
               "HONEST DISTANCES -> genuine model inadequacy (no crashes dominating)")
    print(f"  VERDICT: {verdict}")
    print("=" * 78)


if __name__ == "__main__":
    main()
