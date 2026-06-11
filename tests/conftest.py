"""Shared fixtures: the dummy_dose_v0 case loaded once per session."""

from pathlib import Path

import pytest

from wager.contracts import ScoringParams
from wager.factory.case_loader import (
    load_battery,
    load_ladder,
    load_meta,
    load_world_sample,
    load_world_source,
)

CASE_DIR = Path(__file__).resolve().parents[1] / "cases" / "dummy_dose_v0"


@pytest.fixture(scope="session")
def case_dir() -> Path:
    return CASE_DIR


@pytest.fixture(scope="session")
def meta():
    return load_meta(CASE_DIR)


@pytest.fixture(scope="session")
def battery():
    return load_battery(CASE_DIR)


@pytest.fixture(scope="session")
def world_sample():
    return load_world_sample(CASE_DIR)


@pytest.fixture(scope="session")
def world_source():
    return load_world_source(CASE_DIR)


@pytest.fixture(scope="session")
def ladder():
    return load_ladder(CASE_DIR)


@pytest.fixture(scope="session")
def fast_params(meta):
    """Cheap params for wiring tests (small n, few reps)."""
    return ScoringParams(
        lambda_mdl=meta.scoring.lambda_mdl,
        n_samples=300,
        m_reps=2,
        model_call_timeout_s=meta.scoring.model_call_timeout_s,
    )
