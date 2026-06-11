"""E0 -- one real episode end to end (Decision Log v0.14, C3 acceptance).

A frontier model plays dummy_dose_v0 in the opaque harness and submits a model.
E0 is OBSERVATION of playability, not an eval. Deliverables: the full re-readable
trace (saved), episode cost (tokens + time), R of the submission, and the
contract frictions visible in the trace.

Expectation (Decision Log v0.14, precision 6): dummy_dose_v0 is ONE textbook
trap; a frontier is EXPECTED to reach high R. E0 measures whether the game is
PLAYABLE, not headroom. A LOW R here is the signal to investigate the game or the
contract -- not the model.

Run:  .venv/Scripts/python cases/dummy_dose_v0/e0_episode.py [model] [seed_offset]
"""

import json
import sys
import time
from pathlib import Path

from wager.harness.case_episode import build_world_server
from wager.harness.episode import run_episode

CASE_DIR = Path(__file__).parent


def main():
    model = sys.argv[1] if len(sys.argv) > 1 else None  # default: AZURE_MODEL (gpt-5.4)
    seed_offset = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    server = build_world_server(CASE_DIR, seed_offset=seed_offset)
    t0 = time.perf_counter()
    result = run_episode(server, model=model)
    result["wall_seconds"] = round(time.perf_counter() - t0, 1)

    out_dir = CASE_DIR / "traces"
    out_dir.mkdir(exist_ok=True)
    name = f"e0_{result['model']}_seed{seed_offset}.json".replace("/", "_")
    (out_dir / name).write_text(json.dumps(result, indent=2), encoding="utf-8")

    print("=" * 64)
    print(f"E0 -- {result['model']} on {result['case_id']} (seed_offset={seed_offset})")
    print("=" * 64)
    print(f"  accepted   : {result['accepted']}  (abort_reason={result['abort_reason']})")
    R = result["R"]
    print(f"  R          : {R:.3f} (R_uncl={result['R_unclipped']:+.3f})" if R is not None else "  R          : None")
    print(f"  turns      : {result['turns']}")
    print(f"  budget     : spent {result['budget_spent']:.0f} / {result['budget_total']:.0f}")
    print(f"  tokens     : total {result['tokens']['total']} "
          f"(prompt {result['tokens']['prompt']}, completion {result['tokens']['completion']}, "
          f"reasoning {result['tokens']['reasoning']})")
    print(f"  wall       : {result['wall_seconds']}s")
    sig = result["signal"]
    print(f"  signal(v0.1): attribution_before_experiment={sig['attribution_before_experiment']} "
          f"(1st_attribution_turn={sig['first_attribution_turn']}, "
          f"1st_experiment_turn={sig['first_experiment_turn']})")
    n_failed = sum(len([s for s in t.get("submit_attempts", []) if not s["args"].get("accepted")])
                   for t in result["trace"])
    print(f"  submits    : {sum(len(t.get('submit_attempts', [])) for t in result['trace'])} attempts "
          f"({n_failed} failed smoke)")
    print(f"  trace -> {out_dir / name}")


if __name__ == "__main__":
    main()
