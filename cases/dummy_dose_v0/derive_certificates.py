"""Derive rivals + compute certificates for dummy_dose_v0 (theory-gap headline).

Tests pre-registered prediction (i) (Decision Log v0.17): the dummy's theory gap
should be SMALL (~0.1) -- a no-latent model conditioning outcome on the observed
marker recovers most of the structure.

Run:  .venv/Scripts/python cases/dummy_dose_v0/derive_certificates.py
"""

from pathlib import Path

from wager.factory.case_loader import load_battery, load_meta, load_world_sample
from wager.factory.certificates import compute_certificates
from wager.factory.derive_rivals import (
    best_no_latent,
    capacity_ladder,
    experimental_grid,
    observational_pool,
    rival_naive,
)
from wager.reward.scorer import WorldSide

CASE_DIR = Path(__file__).parent


def main():
    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)  # hand battery for now (acceptance i replaces it)
    world_sample = load_world_sample(CASE_DIR)
    params = meta.scoring
    source = list(meta.episode.observe_sources.values())[0]

    pool = observational_pool(world_sample, source, 4000, 50001)
    # dense, smooth coverage of the control surface (a capable rival's experiments)
    train = experimental_grid(
        world_sample, "dose", list(range(0, 11)), [-1.5, -0.75, 0.0, 0.75, 1.5], 400, 60001
    )

    naive = rival_naive(pool)
    no_latent = best_no_latent(train, pool)  # full data access (incl. experiments)
    # associational baseline = best no-latent fit on OBSERVATIONAL data ONLY
    pool_train = pool.copy()
    pool_train["cohort"] = 0.0  # the observational source is cohort 0
    associational = capacity_ladder(pool_train, pool)

    world_side = WorldSide(world_sample, battery, meta.column_names, params.n_samples)
    cert = compute_certificates(world_sample, naive, no_latent, associational, world_side, params)

    print("=" * 70)
    print(f"CERTIFICATES -- {meta.case_id}")
    print("=" * 70)
    print(f"  R(naive, obs joint)          = {cert['R_naive']:.3f}")
    print(f"  R(best no-latent, full data) = {cert['R_no_latent']:.3f}")
    print(f"  R(associational, obs only)   : "
          + ", ".join(f"{k}={v:.3f}" for k, v in cert["R_associational"].items())
          + f"  (best: {cert['best_associational']})")
    print("-" * 70)
    print(f"  THEORY GAP      = {cert['theory_gap']:.3f}   "
          f"(prediction i: small ~0.1)  {'OK' if cert['theory_gap'] < 0.25 else 'CHECK'}")
    print(f"  MECHANISTIC GAP = {cert['mechanistic_gap']:.3f}   (obs-only baseline)")
    print("=" * 70)


if __name__ == "__main__":
    main()
