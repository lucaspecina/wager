"""L2 - reward variance protocol (ARCHITECTURE 13-L2).

Marked slow: it re-scores the mid rung over B resampled seed-sets. The full
deliverable numbers (CV over R, CV of S_truth, the world/model decomposition
and the K x n x m cost in seconds) are produced by
cases/dummy_dose_v0/run_slice.py; here we assert the protocol runs and that
CV over normalized R clears the initial target on a reduced configuration.
"""

import pytest

from wager.reward.variance import run_variance_protocol

CV_TARGET = 0.05  # initial target, Decision Log v0.10 (empirical)


@pytest.mark.slow
def test_variance_protocol_runs_and_is_low_cv(
    world_sample, world_source, ladder, battery, meta
):
    rungs = dict(ladder)
    params = meta.scoring  # v0 defaults (n=1000, m=2)
    report = run_variance_protocol(
        world_sample=world_sample,
        world_source=world_source,
        naive_code=rungs["rung_5_naive_fit"],
        null_code=rungs["rung_6_null"],
        rung_code=rungs["rung_3_linearized"],  # mid rung
        rung_name="rung_3_linearized",
        battery=battery,
        columns=meta.column_names,
        params=params,
        b_total=12,
        b_model_side=6,
        case_id=meta.case_id,
    )
    assert 0.0 <= report.r_production <= 1.0
    assert report.cv_r < CV_TARGET, f"CV(R)={report.cv_r:.4f} exceeds target {CV_TARGET}"
    # decomposition is well-formed
    assert report.world_side_std >= 0.0
    assert report.model_side_std >= 0.0
