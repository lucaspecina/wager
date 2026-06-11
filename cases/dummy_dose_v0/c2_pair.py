"""C2 -- the scripted solver pair (Decision Log v0.14).

Runs solver_naive and solver_canonical through the real interactive game and
reports the R each lands on plus its trajectory. The naive<->canonical spread
is the harness's degraded-truth ladder: it shows that investigating wins by the
real path, before any LLM. Acceptance: naive ~ R 0, canonical > 0.7. If the
canonical solver cannot land high, investigate the GAME, not the script.

Run:  .venv/Scripts/python cases/dummy_dose_v0/c2_pair.py
"""

import sys
from pathlib import Path

CASE_DIR = Path(__file__).parent
sys.path.insert(0, str(CASE_DIR))

from solvers import solver_canonical, solver_naive  # noqa: E402

from wager.harness.case_episode import build_world_server  # noqa: E402
from wager.harness.env import Env  # noqa: E402


def main():
    print("=" * 64)
    print("C2 -- scripted solver pair on dummy_dose_v0")
    print("=" * 64)

    results = {}
    for name, solver in (("naive", solver_naive), ("canonical", solver_canonical)):
        server = build_world_server(CASE_DIR)
        solver(Env(server))
        res = server.result
        results[name] = res
        print(f"\n[{name}] trajectory:")
        for ev in server.trajectory:
            extra = f"  {ev.note}" if ev.note else ""
            print(f"  {ev.verb:<11s} cost={ev.cost:7.1f}  budget_left={ev.budget_remaining:8.1f}  "
                  f"{ev.args}{extra}")
        if res:
            print(f"  -> R = {res['R']:.3f}  (R_uncl={res['R_unclipped']:+.3f}, raw={res['raw_score']:.4f}, "
                  f"S_truth={res['s_truth']:.4f}, S_naive={res['s_naive']:.4f})")
        else:
            print("  -> no submission accepted")

    print("\n" + "=" * 64)
    rn = results["naive"]["R"] if results["naive"] else None
    rc = results["canonical"]["R"] if results["canonical"] else None
    print(f"SPREAD: naive R={rn:.3f}  canonical R={rc:.3f}" if rn is not None and rc is not None
          else f"SPREAD: naive R={rn}  canonical R={rc}")
    ok = rn is not None and rc is not None and rn < 0.2 and rc > 0.7
    print(f"C2 acceptance (naive<0.2 and canonical>0.7): "
          f"{'PASS' if ok else 'CHECK -- investigate the GAME, not the script'}")
    print("=" * 64)


if __name__ == "__main__":
    main()
