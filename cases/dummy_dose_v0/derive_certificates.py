"""Derive rivals + compute certificates for dummy_dose_v0 (theory-gap headline).

Tests pre-registered prediction (i) (Decision Log v0.17): the dummy's theory gap
should be SMALL (~0.1) -- a no-latent model conditioning outcome on the observed
marker recovers most of the structure.

Run:  .venv/Scripts/python cases/dummy_dose_v0/derive_certificates.py
"""

import sys
from pathlib import Path

from wager.contracts import RivalAccess
from wager.factory.case_loader import load_battery, load_meta, load_world_sample
from wager.factory.certificates import compute_certificates, per_regime_reading
from wager.factory.derive_rivals import (
    best_no_latent,
    capacity_ladder,
    experimental_grid,
    observational_pool,
    rival_naive,
)
from wager.factory.rival_c_panel import derive_rival_c, ensemble_callable
from wager.reward.scorer import WorldSide

CASE_DIR = Path(__file__).parent


def main():
    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)  # hand battery for now (acceptance i replaces it)
    world_sample = load_world_sample(CASE_DIR)
    params = meta.scoring
    source = list(meta.episode.observe_sources.values())[0]

    N_POOL, POOL_SEED = 4000, 50001
    pool = observational_pool(world_sample, source, N_POOL, POOL_SEED)
    # dense, smooth coverage of the control surface (a capable rival's experiments)
    DOSE_LEVELS = list(range(0, 11))
    COHORTS = [-1.5, -0.75, 0.0, 0.75, 1.5]
    N_TRAIN, TRAIN_SEED = 400, 60001
    train = experimental_grid(world_sample, "dose", DOSE_LEVELS, COHORTS, N_TRAIN, TRAIN_SEED)

    naive = rival_naive(pool)
    no_latent = best_no_latent(train, pool)  # full data access (incl. experiments)
    # associational baseline = best no-latent fit on OBSERVATIONAL data ONLY
    pool_train = pool.copy()
    pool_train["cohort"] = 0.0  # the observational source is cohort 0
    associational = capacity_ladder(pool_train, pool)

    # self-describing access (Decision Log v0.30). theory gap = vs PROTO-(d-exp):
    # the ad-hoc do(dose) grid below; standardized=False until the v0.29 budget
    # lands (paso 3). mechanistic gap = vs (a)/(d-obs): the observational pool.
    theory_access = RivalAccess(
        mode="experimental", n_rows=N_TRAIN * len(DOSE_LEVELS) * len(COHORTS), seed0=TRAIN_SEED,
        grid=f"do(dose) x {len(DOSE_LEVELS)} levels x {len(COHORTS)} cohorts (ad-hoc, pre-standard)",
        standardized=False,
    )
    mechanistic_access = RivalAccess(
        mode="observational", n_rows=N_POOL, seed0=POOL_SEED, grid=None, standardized=True,
    )

    # prior gap (cheap; rival c already built). Skip with --no-llm.
    prior_fn = None
    if "--no-llm" not in sys.argv:
        print("deriving rival (c) prior panel (k=3 LLMs)...")
        rc = derive_rival_c(brief_text(), meta.column_names, meta.episode.smoke_regimes, k=3)
        print(f"  compiled {rc['k_compiled']}/{rc['k_requested']} members")
        if rc["k_compiled"] > 0:
            prior_fn = ensemble_callable(rc["ensemble"])

    world_side = WorldSide(world_sample, battery, meta.column_names, params.n_samples)
    cert = compute_certificates(
        world_sample, naive, no_latent, associational, world_side, params,
        theory_access=theory_access, mechanistic_access=mechanistic_access, prior_rival=prior_fn,
    )

    print("=" * 70)
    print(f"CERTIFICATES -- {meta.case_id}")
    print("=" * 70)
    print(f"  R(naive, obs joint)          = {cert['R_naive']:.3f}")
    print(f"  R(best no-latent, full data) = {cert['R_no_latent']:.3f}")
    print(f"  R(associational, obs only)   : "
          + ", ".join(f"{k}={v:.3f}" for k, v in cert["R_associational"].items())
          + f"  (best: {cert['best_associational']})")
    if "R_prior" in cert:
        print(f"  R(prior-evoked, rival c)     = {cert['R_prior']:.3f}")
    print("-" * 70)
    ta, ma = cert["theory_access"], cert["mechanistic_access"]
    print(f"  THEORY GAP      = {cert['theory_gap']:.3f}   "
          f"(prediction i: small ~0.1)  {'OK' if cert['theory_gap'] < 0.25 else 'CHECK'}")
    print(f"    access: {ta['mode']} n={ta['n_rows']} seed0={ta['seed0']} "
          f"{'STANDARDIZED' if ta['standardized'] else 'PROTO (pre-v0.29-standard)'} -- {ta['grid']}")
    print(f"  MECHANISTIC GAP = {cert['mechanistic_gap']:.3f}   (obs-only baseline)")
    print(f"    access: {ma['mode']} n={ma['n_rows']} seed0={ma['seed0']} "
          f"{'STANDARDIZED' if ma['standardized'] else 'PROTO'}")
    if "prior_gap" in cert:
        print(f"  PRIOR GAP       = {cert['prior_gap']:.3f}   "
              f"(prediction: LOW => prior knows the textbook trap; in a seeded "
              f"world this is attack #16 rejection, here it shows the contamination test works)")
    print("-" * 70)
    print(f"  RAW denominator S_truth - S_naive = {cert['denom_raw']:.4f}  "
          f"(substantive discrimination scale; reward CV ~1% << this -> world discriminates)")
    print("=" * 70)

    # SYMMETRIC verification (Decision Log v0.19): read the confirmatory theory gap
    # per-regime, exactly as an anomalous value would be read.
    print("\nSYMMETRIC READING -- best no-latent vs truth, per battery item:")
    rows = per_regime_reading(no_latent, world_sample, world_side, params)
    crashes = sum(r["crashed"] for r in rows)
    print(f"  crashes: {crashes}/{len(rows)}  (theory gap is from HONEST distances, not D_MAX)")
    worst = sorted(rows, key=lambda r: -r["distance"])[:4]
    for r in worst:
        d = "obs" if r["dose"] is None else f"{r['dose']:.0f}"
        print(f"  item {r['idx']:>2} dose={d:>3} coh={r['cohort']:+.1f} w={r['weight']:.2f} "
              f"dist={r['distance']:.4f}  truth_out={r.get('truth_outcome_mean', float('nan')):.2f} "
              f"nolat_out={r.get('rival_outcome_mean', float('nan')):.2f}")

    # store the numbers so the deterministic dossier can read them (zero-LLM at
    # dossier time; certificates are a factory artifact, Decision Log v0.23)
    stored = {
        "theory_gap": cert["theory_gap"], "mechanistic_gap": cert["mechanistic_gap"],
        "R_no_latent": cert["R_no_latent"], "denom_raw": cert["denom_raw"],
        "best_associational": cert["best_associational"],
        "theory_access": cert["theory_access"], "mechanistic_access": cert["mechanistic_access"],
    }
    if "prior_gap" in cert:
        stored["prior_gap"] = cert["prior_gap"]
        stored["R_prior"] = cert["R_prior"]
    import json as _json
    (CASE_DIR / "certificates.json").write_text(_json.dumps(stored, indent=2) + "\n", encoding="utf-8")
    print(f"\nstored -> {CASE_DIR / 'certificates.json'}")


def brief_text():
    return (CASE_DIR / "brief.md").read_text(encoding="utf-8")


if __name__ == "__main__":
    main()
