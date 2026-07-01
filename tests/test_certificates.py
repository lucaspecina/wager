"""Certificates on dummy_dose_v0 (pre-registered prediction i, Decision Log v0.17).

Slow: fits the derived rivals and scores them. The dummy is a CONFOUNDING trap,
not a latent-structure trap: mechanistic gap large (must intervene), theory gap
small (a no-latent model with full data access recovers the structure).
"""

from pathlib import Path

import pytest

from wager.contracts import RivalAccess
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

CASE_DIR = Path(__file__).resolve().parents[1] / "cases" / "dummy_dose_v0"


@pytest.mark.slow
def test_dummy_theory_gap_small_mechanistic_gap_large():
    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    source = list(meta.episode.observe_sources.values())[0]

    pool = observational_pool(world_sample, source, 4000, 50001)
    # the THEORY-GAP reference must be the BEST no-latent -> dense, smooth grid
    train = experimental_grid(
        world_sample, "dose", list(range(0, 11)), [-1.5, -0.75, 0.0, 0.75, 1.5], 400, 60001
    )
    naive = rival_naive(pool)
    no_latent = best_no_latent(train, pool)
    pool_train = pool.copy()
    pool_train["cohort"] = 0.0
    associational = capacity_ladder(pool_train, pool)

    ws = WorldSide(world_sample, battery, meta.column_names, meta.scoring.n_samples)
    theory_access = RivalAccess(mode="experimental", n_rows=len(train), seed0=60001,
                                grid="do(dose) grid", standardized=False)
    mech_access = RivalAccess(mode="observational", n_rows=len(pool), seed0=50001, standardized=True)
    cert = compute_certificates(world_sample, naive, no_latent, associational, ws, meta.scoring,
                                theory_access=theory_access, mechanistic_access=mech_access)

    # prediction (i): dummy theory gap small (a no-latent model recovers ~all)
    assert cert["theory_gap"] < 0.2, f"theory gap {cert['theory_gap']:.3f} not small"
    # the dummy still forces investigation: obs-only curve-fitting loses
    assert cert["mechanistic_gap"] > 0.7, f"mechanistic gap {cert['mechanistic_gap']:.3f} not large"
    # self-describing access travels with the certificate (Decision Log v0.30)
    assert cert["theory_access"]["mode"] == "experimental"
    assert cert["mechanistic_access"]["mode"] == "observational"


def test_certificate_access_guard():
    """The contract REQUIRES correct access modes: theory=experimental,
    mechanistic=observational (Decision Log v0.30/v0.29). A swapped access raises,
    so a drift can't silently emit a meaningless gap."""
    import pytest as _pytest

    meta = load_meta(CASE_DIR)
    battery = load_battery(CASE_DIR)
    world_sample = load_world_sample(CASE_DIR)
    source = list(meta.episode.observe_sources.values())[0]
    pool = observational_pool(world_sample, source, 200, 50001)
    naive = rival_naive(pool)
    ws = WorldSide(world_sample, battery, meta.column_names, meta.scoring.n_samples)
    obs = RivalAccess(mode="observational", n_rows=200, seed0=1)
    exp = RivalAccess(mode="experimental", n_rows=200, seed0=2, grid="g")
    with _pytest.raises(ValueError, match="theory gap requires an EXPERIMENTAL"):
        compute_certificates(world_sample, naive, naive, [("a", naive)], ws, meta.scoring,
                             theory_access=obs, mechanistic_access=obs)
    with _pytest.raises(ValueError, match="mechanistic gap requires an OBSERVATIONAL"):
        compute_certificates(world_sample, naive, naive, [("a", naive)], ws, meta.scoring,
                             theory_access=exp, mechanistic_access=exp)
