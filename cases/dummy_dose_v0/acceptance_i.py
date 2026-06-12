"""Acceptance (i): the DERIVED battery reproduces the hand battery's discrimination.

Side-by-side (Decision Log v0.17 ajuste 5): ladder order + margins + naive<->canonical
spread on the hand battery vs the 100%-derived battery. Plus the top-10 items of the
derived battery in readable form for the first human battery audit. If this passes,
the bootstrap battery.json can be replaced by the derived one (bootstrap expires).

Run:  .venv/Scripts/python cases/dummy_dose_v0/acceptance_i.py [--write]
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).parent
sys.path.insert(0, str(CASE_DIR))

from solvers import solver_canonical, solver_naive  # noqa: E402

from wager.factory.case_loader import (  # noqa: E402
    load_battery, load_ladder, load_meta, load_world_sample, load_world_source,
)
from wager.factory.battery_builder import build_battery  # noqa: E402
from wager.factory.derive_rivals import build_standard_rivals  # noqa: E402
from wager.harness.case_episode import build_world_server  # noqa: E402
from wager.harness.env import Env  # noqa: E402
from wager.reward.episode_score import score_episode_submission  # noqa: E402
from wager.reward.ladder import run_ladder  # noqa: E402


def solver_code(solver):
    server = build_world_server(CASE_DIR)
    solver(Env(server))
    return server.result["code"]


def ladder_table(world_sample, world_source, ladder, battery, columns, params, label):
    rep = run_ladder(world_sample, world_source, ladder, battery, columns, params, case_id=label)
    print(f"\n  [{label}] K={len(battery.items)}  passed={rep.passed}  "
          f"denom(S_truth-S_naive)={rep.anchors.normalization_range:.4f}")
    for rung in rep.rungs:
        m = "-" if rung.margin_to_next is None else f"{rung.margin_to_next:+.3f}"
        print(f"    {rung.name:<26s} R={rung.r:6.3f}  margin->next {m}  [{rung.kind}]")
    return rep


def main():
    meta = load_meta(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    world_source = load_world_source(CASE_DIR)
    ladder = load_ladder(CASE_DIR)
    hand = load_battery(CASE_DIR)
    cols = meta.column_names
    params = meta.scoring

    # hardened canonical config (Decision Log v0.24): naive + FULL capacity ladder
    # (linear+GBM) + twin per mechanism op, with dedup_radius=1.2 for diversity.
    rivals, pool, train = build_standard_rivals(CASE_DIR, world_sample, meta)
    nl_ns: dict = {}
    exec(dict(ladder)["rung_6_null"], nl_ns)  # null model for the D_MAX disagreement cap
    derived = build_battery(world_sample, rivals, nl_ns["model"], cols, meta.stakes, dedup_radius=1.2)

    print("=" * 72)
    print("ACCEPTANCE (i) -- hand battery vs 100%-derived battery")
    print("=" * 72)
    l_hand = ladder_table(world_sample, world_source, ladder, hand, cols, params, "hand")
    l_der = ladder_table(world_sample, world_source, ladder, derived, cols, params, "derived")

    # naive <-> canonical spread on both
    null_code = dict(ladder)["rung_6_null"]
    naive_code = solver_code(solver_naive)
    canon_code = solver_code(solver_canonical)
    print("\n  naive <-> canonical spread (the harness degraded-truth ladder):")
    spreads = {}
    for label, bat in (("hand", hand), ("derived", derived)):
        rn = score_episode_submission(naive_code, world_sample, world_source, dict(ladder)["rung_5_naive_fit"], null_code, bat, cols, params)
        rc = score_episode_submission(canon_code, world_sample, world_source, dict(ladder)["rung_5_naive_fit"], null_code, bat, cols, params)
        spreads[label] = rc["R"] - rn["R"]
        print(f"    [{label:<7s}] naive R={rn['R']:.3f}  canonical R={rc['R']:.3f}  spread={spreads[label]:.3f}")

    # top-10 of the derived battery, readable (human audit)
    print("\n  TOP-10 derived battery items (human audit):")
    ranked = sorted(derived.items, key=lambda it: -it.weight)[:10]
    for it in ranked:
        d = "obs" if "dose" not in it.regime.config else f"{it.regime.config['dose']:.1f}"
        print(f"    w={it.weight:.3f}  dose={d:>4}  cohort={it.regime.context.get('cohort',0.0):+.2f}")

    # PRODUCTION L1 criterion (Decision Log v0.10/v0.12): monotonicity-per-axis +
    # extremes -- NOT the total-order-with-5%-margins, which is the canonical-dummy
    # scorer-acceptance test only. A derived/production battery is judged by the
    # production criterion.
    def production_ok(rep):
        rs = [rung.r for rung in rep.rungs]
        monotone = all(rs[i] >= rs[i + 1] - 1e-9 for i in range(len(rs) - 1))
        extremes = rep.rungs[0].r > 0.99 and rep.rungs[-2].r < 0.01 and rep.rungs[-1].r < 0.01
        return monotone and extremes

    der_prod = production_ok(l_der)
    spread_ok = abs(spreads["hand"] - spreads["derived"]) < 0.1
    print("\n" + "=" * 72)
    print("ACCEPTANCE (i) -- production criterion (monotonicity + extremes), derived battery")
    print(f"  monotone order + extremes preserved: {der_prod}")
    print(f"  naive<->canonical spread preserved : {spread_ok} "
          f"(derived {spreads['derived']:.3f} vs hand {spreads['hand']:.3f})")
    print("  (margin criterion = 3xCV(R) per-axis; the 5%-total-order margin is the canonical-dummy test only)")
    print(f"\nACCEPTANCE (i): {'MET (production criterion)' if der_prod and spread_ok else 'CHECK'}")
    print("=" * 72)

    # bootstrap expires ONLY after Lucas's human audit approves the top-10
    # (Decision Log v0.22); --write is gated behind that approval, not run here.
    if "--write" in sys.argv and der_prod and spread_ok:
        derived.to_json_file(CASE_DIR / "battery.json")
        print("  derived battery written to battery.json (bootstrap expired)")


if __name__ == "__main__":
    main()
