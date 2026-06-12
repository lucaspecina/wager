"""Full derived-battery coverage map (all items + dose-band summary).

The battery audit needs the WHOLE picture, not only the top-10: does the deep
out-of-record region (dose 8-10) appear at all, and at what weight? This is also
the coverage map for the case dossier (section b).

Run:  .venv/Scripts/python cases/dummy_dose_v0/battery_coverage.py
"""

import sys
from collections import defaultdict
from pathlib import Path

CASE_DIR = Path(__file__).parent
sys.path.insert(0, str(CASE_DIR))

from wager.factory.battery_builder import build_battery
from wager.factory.case_loader import load_ladder, load_meta, load_world_sample
from wager.factory.derive_rivals import build_standard_rivals

DEDUP_RADIUS = 1.2  # hardened config (Decision Log v0.24): diversity radius


def main():
    meta = load_meta(CASE_DIR)
    ws = load_world_sample(CASE_DIR)
    cols = meta.column_names
    rivals, pool, train = build_standard_rivals(CASE_DIR, ws, meta)  # full capacity ladder + twins
    nl = {}
    exec(dict(load_ladder(CASE_DIR))["rung_6_null"], nl)
    bat = build_battery(ws, rivals, nl["model"], cols, meta.stakes, dedup_radius=DEDUP_RADIUS)

    items = sorted(bat.items, key=lambda it: -it.weight)
    print("ALL battery items (sorted by weight):")
    for i, it in enumerate(items, 1):
        d = "obs" if "dose" not in it.regime.config else f"{it.regime.config['dose']:.1f}"
        print(f"  {i:>2}. w={it.weight:.3f}  dose={d:>4}  cohort={it.regime.context.get('cohort',0.0):+.2f}")

    bands = defaultdict(lambda: [0, 0.0])
    for it in bat.items:
        if "dose" not in it.regime.config:
            key = "observational"
        else:
            d = it.regime.config["dose"]
            key = f"dose [{int(d//2.5)*2.5:.1f},{int(d//2.5)*2.5+2.5:.1f})"
        bands[key][0] += 1
        bands[key][1] += it.weight
    print("\nCOVERAGE MAP (band: count, total weight):")
    for k in sorted(bands):
        print(f"  {k:<18} n={bands[k][0]:>2}  weight={bands[k][1]:.3f}")
    oor = sum(it.weight for it in bat.items if it.regime.config.get("dose", 0) >= 6.0)
    deep = sum(it.weight for it in bat.items if it.regime.config.get("dose", 0) >= 8.0)
    print(f"\n  out-of-record (dose>=6): weight {oor:.3f}   deep (dose>=8): weight {deep:.3f}")

    # write to a SEPARATE file so the dossier can show the derived battery for
    # audit WITHOUT expiring the bootstrap (that only happens on Lucas's approval)
    out = CASE_DIR / "battery_derived.json"
    bat.to_json_file(out)
    print(f"\nderived battery (pre-audit, not battery.json) -> {out}")


if __name__ == "__main__":
    main()
