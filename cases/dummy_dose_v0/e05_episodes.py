"""E0.5 -- a small batch of episodes (Decision Log v0.14, precision 5/6).

3-5 episodes over dummy_dose_v0 varying the world seed, across two model families
(cross-family frictions are worth more). Each is observation, not eval. Per
episode we save the full trace and surface: R, turns, tokens, the failed-submit
count, and the before/after-suspicion signal (embryo of E1/E2 signatures).

Run:  .venv/Scripts/python cases/dummy_dose_v0/e05_episodes.py
"""

import json
import time
from pathlib import Path

from wager.harness.case_episode import build_world_server
from wager.harness.episode import run_episode

CASE_DIR = Path(__file__).parent

# (model deployment, seed_offset). gpt-5.4 seed 0 is E0; this batch is the rest.
PLAN = [
    ("gpt-5.4", 1),
    ("gpt-5.4", 2),
    ("DeepSeek-V3.2", 1),
    ("DeepSeek-V3.2", 2),
]


def n_failed_submits(result):
    return sum(
        1
        for t in result["trace"]
        for s in t.get("submit_attempts", [])
        if not s["args"].get("accepted")
    )


def main():
    out_dir = CASE_DIR / "traces"
    out_dir.mkdir(exist_ok=True)
    rows = []
    for model, seed in PLAN:
        print(f"\n>>> episode: model={model} seed_offset={seed} ...")
        try:
            server = build_world_server(CASE_DIR, seed_offset=seed)
            t0 = time.perf_counter()
            result = run_episode(server, model=model)
            result["wall_seconds"] = round(time.perf_counter() - t0, 1)
            name = f"e05_{model}_seed{seed}.json".replace("/", "_")
            (out_dir / name).write_text(json.dumps(result, indent=2), encoding="utf-8")
            sig = result["signal"]
            rows.append({
                "model": model, "seed": seed, "accepted": result["accepted"],
                "R": result["R"], "R_uncl": result["R_unclipped"], "turns": result["turns"],
                "tokens": result["tokens"]["total"], "failed_submits": n_failed_submits(result),
                "attr_before_exp": sig["attribution_before_experiment"],
                "first_attr": sig["first_attribution_turn"], "first_exp": sig["first_experiment_turn"],
                "abort": result["abort_reason"], "wall": result["wall_seconds"],
            })
            print(f"    R={result['R']} turns={result['turns']} tokens={result['tokens']['total']} "
                  f"abort={result['abort_reason']}")
        except Exception as exc:  # noqa: BLE001  (a model may be undeployed)
            print(f"    FAILED: {type(exc).__name__}: {exc}")
            rows.append({"model": model, "seed": seed, "error": f"{type(exc).__name__}: {exc}"})

    print("\n" + "=" * 92)
    print("E0.5 SUMMARY")
    print("=" * 92)
    hdr = (f"{'model':<16}{'seed':>4}{'R':>7}{'R_uncl':>8}{'turns':>6}{'tokens':>8}"
           f"{'fSub':>5}{'attr<exp':>9}{'1stAtt':>7}{'1stExp':>7}{'abort':>12}")
    print(hdr)
    for r in rows:
        if "error" in r:
            print(f"{r['model']:<16}{r['seed']:>4}  ERROR: {r['error']}")
            continue
        R = f"{r['R']:.3f}" if r["R"] is not None else "None"
        Ru = f"{r['R_uncl']:+.3f}" if r["R_uncl"] is not None else "None"
        print(f"{r['model']:<16}{r['seed']:>4}{R:>7}{Ru:>8}{r['turns']:>6}"
              f"{r['tokens']:>8}{r['failed_submits']:>5}{str(r['attr_before_exp']):>9}"
              f"{str(r['first_attr']):>7}{str(r['first_exp']):>7}{r['abort']:>12}")
    print("=" * 92)


if __name__ == "__main__":
    main()
