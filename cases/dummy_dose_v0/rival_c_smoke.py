"""LLM-first smoke of rival (c): panel -> executable program (Decision Log v0.17).

k=3 fresh LLMs see brief+schema (no data) and write the mechanism they expect;
each is brought through a schema smoke + repair loop; the rival is the equal-weight
ensemble. Validates panel->program. Also scores each compiled member (in-process)
to see WHERE the prior lands -- a fresh-LLM mechanism, with NO knowledge of the
trap, should sit well below the truth (it is the prior, not the answer).

Run:  .venv/Scripts/python cases/dummy_dose_v0/rival_c_smoke.py
"""

from pathlib import Path

from wager.factory.case_loader import load_battery, load_meta, load_world_sample
from wager.factory.rival_c_panel import derive_rival_c
from wager.reward.scorer import WorldSide, make_anchors, score_callable
from wager.factory.derive_rivals import observational_pool, rival_naive

CASE_DIR = Path(__file__).parent


def main():
    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    brief = (CASE_DIR / "brief.md").read_text(encoding="utf-8")
    params = meta.scoring

    print("Compiling rival (c) panel (k=3 fresh LLMs, panel->program)...")
    res = derive_rival_c(brief, meta.column_names, meta.episode.smoke_regimes, k=3)
    print(f"  compiled {res['k_compiled']}/{res['k_requested']} members")
    for i, m in enumerate(res["members"]):
        status = "OK" if m["code"] else f"FAILED ({m.get('last_error')})"
        print(f"  member {i}: repairs={m['repairs']} tokens={m['tokens']} -> {status}")

    if res["k_compiled"] == 0:
        print("PANEL SMOKE: no member compiled -- investigate panel prompt / smoke")
        return

    # score each compiled member in-process to locate the prior
    pool = observational_pool(world_sample, list(meta.episode.observe_sources.values())[0], 3000, 50001)
    ws = WorldSide(world_sample, battery, meta.column_names, params.n_samples)
    s_truth = score_callable(world_sample, ws, params)
    s_naive = score_callable(rival_naive(pool), ws, params)
    anchors = make_anchors(s_truth, s_naive, s_truth - 1.0)  # null anchor unused here

    print("\n  where the prior lands (R = fraction of truth-naive range):")
    for i, m in enumerate(res["members"]):
        if not m["code"]:
            continue
        ns_glb: dict = {}
        exec(m["code"], ns_glb)  # member passed lint+schema smoke
        fn = ns_glb["model"]
        s = score_callable(lambda r, n, sd: fn(r, n, sd), ws, params)
        r, _ = anchors.r_of(s)
        print(f"    member {i}: R={r:.3f}")
    print("\nPANEL SMOKE: panel -> executable program VALIDATED")


if __name__ == "__main__":
    main()
