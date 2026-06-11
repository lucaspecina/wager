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
    load_battery, load_ladder, load_meta, load_world_module, load_world_sample, load_world_source,
)
from wager.factory.battery_builder import build_battery  # noqa: E402
from wager.factory.derive_rivals import (  # noqa: E402
    best_no_latent, experimental_grid, observational_pool, rival_naive, rival_twin,
)
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

    pool = observational_pool(world_sample, list(meta.episode.observe_sources.values())[0], 4000, 50001)
    train = experimental_grid(world_sample, "dose", list(range(0, 11)), [-1.5, 0.0, 1.5], 300, 60001)
    # disagreement set: naive (believes data), best no-latent, and the innocent
    # TWIN (confounding ablated + refit) -- the twin fails IN-SUPPORT, so the
    # battery weighs the regimes where the trap bites, not only off-support
    # extrapolation (Decision Log v0.20).
    wmod = load_world_module(CASE_DIR)
    conf = next(op for op in meta.operators if op.name == "confounding_por_indicacion")
    twin = rival_twin(wmod.mechanism, wmod.PARAMS, conf.ablation, pool)
    rivals = [rival_naive(pool), best_no_latent(train, pool), twin]
    derived = build_battery(world_sample, rivals, cols, meta.stakes.decision_variables)

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
    for label, bat in (("hand", hand), ("derived", derived)):
        rn = score_episode_submission(naive_code, world_sample, world_source, dict(ladder)["rung_5_naive_fit"], null_code, bat, cols, params)
        rc = score_episode_submission(canon_code, world_sample, world_source, dict(ladder)["rung_5_naive_fit"], null_code, bat, cols, params)
        print(f"    [{label:<7s}] naive R={rn['R']:.3f}  canonical R={rc['R']:.3f}  spread={rc['R']-rn['R']:.3f}")

    # top-10 of the derived battery, readable (human audit)
    print("\n  TOP-10 derived battery items (human audit):")
    ranked = sorted(derived.items, key=lambda it: -it.weight)[:10]
    for it in ranked:
        d = "obs" if "dose" not in it.regime.config else f"{it.regime.config['dose']:.1f}"
        print(f"    w={it.weight:.3f}  dose={d:>4}  cohort={it.regime.context.get('cohort',0.0):+.2f}")

    ok = l_hand.passed and l_der.passed
    print("\n" + "=" * 72)
    print(f"ACCEPTANCE (i): {'PASS' if ok else 'CHECK'} -- both ladders ordered with margins")
    print("=" * 72)

    if "--write" in sys.argv and ok:
        derived.to_json_file(CASE_DIR / "battery.json")
        print("  derived battery written to battery.json (bootstrap expired)")


if __name__ == "__main__":
    main()
