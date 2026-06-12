"""Battery hardening round (Decision Log v0.24) -- items 1-5, one pass each.

A) rivals in the disagreement set (item 4: full capacity ladder).
B) attribution matrix {cohort-fix on/off} x {dedup on/off} at one seed (item 3).
C) seed robustness of the canonical config over 3 seeds (item 2).
D) decisive 67/25 experiment: degraded-truth ladder restricted BY BAND (item 5).

Run:  .venv/Scripts/python cases/dummy_dose_v0/hardening.py
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).parent
sys.path.insert(0, str(CASE_DIR))

from wager.contracts import Battery
from wager.factory.battery_builder import build_battery
from wager.factory.case_loader import load_ladder, load_meta, load_world_sample, load_world_source
from wager.factory.derive_rivals import build_standard_rivals
from wager.reward.ladder import run_ladder

N_MC = 300
N_CAND = 400


def coverage(bat):
    total = sum(it.weight for it in bat.items) or 1.0
    bands = {}
    for it in bat.items:
        if "dose" not in it.regime.config:
            k = "obs"
        else:
            lo = int(min(it.regime.config["dose"], 9.999) // 2.5) * 2.5
            k = f"d[{lo:.1f},{lo+2.5:.1f})"
        bands[k] = bands.get(k, 0.0) + it.weight / total
    oor = sum(it.weight for it in bat.items if it.regime.config.get("dose", 0) >= 6.0) / total
    extreme_coh = sum(it.weight for it in bat.items if abs(it.regime.context.get("cohort", 0)) >= 1.5) / total
    return bands, oor, extreme_coh


def print_cov(label, bat):
    bands, oor, ec = coverage(bat)
    s = "  ".join(f"{k}={v:.0%}" for k, v in sorted(bands.items()))
    print(f"  [{label:<26s}] {s}")
    print(f"  {'':28s} out-of-record(d>=6)={oor:.0%}  extreme-cohort(|c|>=1.5)={ec:.0%}")
    return bands


def main():
    meta = load_meta(CASE_DIR)
    ws = load_world_sample(CASE_DIR)
    wsrc = load_world_source(CASE_DIR)
    ladder = load_ladder(CASE_DIR)
    cols = meta.column_names
    nl = {}
    exec(dict(ladder)["rung_6_null"], nl)
    null_fn = nl["model"]

    rivals, pool, train = build_standard_rivals(CASE_DIR, ws, meta)
    print("=" * 78)
    print(f"A) DISAGREEMENT RIVALS (item 4): {len(rivals)} programs = "
          f"naive(a) + full capacity ladder(d: linear+GBM) + twins(b, per mechanism op)")

    stakes_on = meta.stakes  # cohort tail ON (the fix)
    stakes_off = meta.stakes.model_copy(update={"context_relevance": {"cohort": {"center": 0.0, "sd": 1.0}}})

    def build(stakes, dedup, seed, n_cand=N_CAND):
        return build_battery(ws, rivals, null_fn, cols, stakes,
                             n_candidates=n_cand, n_mc=N_MC, seed=seed, dedup_radius=dedup)

    print("\n" + "=" * 78)
    print("B) ATTRIBUTION MATRIX (item 3) -- seed 314159")
    cfgs = [("cohortFIX=off dedup=off", stakes_off, 0.0), ("cohortFIX=on  dedup=off", stakes_on, 0.0),
            ("cohortFIX=off dedup=on", stakes_off, 1.2), ("cohortFIX=on  dedup=on", stakes_on, 1.2)]
    canon = None
    for label, st, dd in cfgs:
        bat = build(st, dd, 314159)
        print_cov(label, bat)
        if "on  dedup=on" in label:
            canon = bat

    print("\n" + "=" * 78)
    N_CAND_ROBUST = 1000
    print(f"C) SEED ROBUSTNESS (item 2) -- canonical (cohortFIX=on, dedup=on), {N_CAND_ROBUST} candidates, 3 seeds")
    seeds = [314159, 271828, 161803]
    band_sets = []
    for sd in seeds:
        bat = build(stakes_on, 1.2, sd, n_cand=N_CAND_ROBUST)
        band_sets.append(print_cov(f"seed {sd}", bat))
    allbands = set().union(*[set(b) for b in band_sets])
    print("  per-band variation (max-min across seeds):")
    worst = 0.0
    for k in sorted(allbands):
        vals = [b.get(k, 0.0) for b in band_sets]
        v = max(vals) - min(vals)
        worst = max(worst, v)
        print(f"    {k:<14s} {v*100:.1f}pp")
    print(f"  >>> worst band variation = {worst*100:.1f}pp  (pre-reg: < 5pp)  "
          f"{'PASS' if worst < 0.05 else 'FAIL -> raise candidates'}")

    print("\n" + "=" * 78)
    print("D) DECISIVE 67/25 EXPERIMENT (item 5) -- degraded ladder BY BAND")
    bat = canon
    in_sup = Battery(items=[it for it in bat.items
                            if it.regime.config.get("dose", 0) < 6.0 and abs(it.regime.context.get("cohort", 0)) < 1.5])
    oor = Battery(items=[it for it in bat.items
                         if it.regime.config.get("dose", 0) >= 6.0 or abs(it.regime.context.get("cohort", 0)) >= 1.5])
    for name, sub in (("IN-SUPPORT", in_sup), ("OUT-OF-RECORD", oor)):
        if not sub.items:
            print(f"  [{name}] empty"); continue
        rep = run_ladder(ws, wsrc, ladder, sub, cols, meta.scoring)

        def _key(nm):
            for k in ("perturbed", "linearized", "innocent", "naive", "null", "truth"):
                if k in nm:
                    return k
            return nm
        rungs = {_key(r.name): r.r for r in rep.rungs}
        fine = {k: rungs[k] for k in ("perturbed", "linearized", "innocent") if k in rungs}
        spread = max(fine.values()) - min(fine.values()) if fine else 0.0
        print(f"  [{name:<14s}] K={len(sub.items):>2}  fine-rung R: "
              + ", ".join(f"{k}={v:.3f}" for k, v in fine.items()) + f"   spread={spread:.3f}")
    print("  pre-reg (Claude): in-support spread WIDE, out-of-record spread COMPRESSED.")
    print("=" * 78)


if __name__ == "__main__":
    main()
