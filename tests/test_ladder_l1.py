"""L1 - the degraded-truth ladder acceptance test (ARCHITECTURE 13-L1).

For the canonical Slice 1 dummy the scorer must order all six rungs with the
declared margin (total order; production cases use monotonicity-per-axis +
extremes - Decision Log v0.10/v0.11). If this fails, the default is to
INVESTIGATE, never to retune the fixtures.
"""

import pytest

from wager.reward.ladder import DEFAULT_MARGIN, run_ladder


@pytest.fixture(scope="module")
def ladder_report(world_sample, world_source, ladder, battery, meta):
    return run_ladder(
        world_sample=world_sample,
        world_source=world_source,
        ladder=ladder,
        battery=battery,
        columns=meta.column_names,
        params=meta.scoring,
        margin_required=DEFAULT_MARGIN,
        case_id=meta.case_id,
    )


def test_ladder_has_all_six_rungs(ladder_report):
    assert len(ladder_report.rungs) == 6


def test_ladder_truth_rung_is_r_one(ladder_report):
    assert ladder_report.rungs[0].r == pytest.approx(1.0)
    assert ladder_report.rungs[0].r_unclipped == pytest.approx(1.0, abs=1e-9)


def test_anchors_are_labelled_and_naive_rung_is_the_s_naive_anchor(ladder_report):
    """The 'naive fit' fixture (rung -2) IS the same object as the S_naive
    anchor of the normalization (Decision Log P3/v0.12): its raw score equals
    s_naive exactly and its R is 0 by construction. Anchors must not be read as
    measurements."""
    rungs = ladder_report.rungs
    anchors = ladder_report.anchors
    assert rungs[0].kind == "anchor:S_truth"
    assert rungs[-2].kind == "anchor:S_naive"
    assert rungs[-1].kind == "reference:S_null"
    assert all(r.kind == "measurement" for r in rungs[1:-2])

    naive = rungs[-2]
    assert naive.raw_score == anchors.s_naive  # same object, not a coincidence
    assert naive.r == pytest.approx(0.0, abs=1e-12)
    truth = rungs[0]
    assert truth.raw_score == anchors.s_truth
    assert rungs[-1].raw_score == anchors.s_null


def test_ladder_strictly_descending(ladder_report):
    raws = [rung.raw_score for rung in ladder_report.rungs]
    assert raws == sorted(raws, reverse=True), [round(x, 5) for x in raws]


def test_ladder_passes_with_margin(ladder_report):
    failing = [
        (r.name, r.margin_to_next)
        for r in ladder_report.rungs
        if r.margin_to_next is not None and r.margin_to_next < ladder_report.margin_required
    ]
    assert ladder_report.passed, f"rungs below margin {ladder_report.margin_required}: {failing}"


def test_ladder_null_is_r_zero(ladder_report):
    assert ladder_report.rungs[-1].r == pytest.approx(0.0, abs=1e-9)


def test_rival_strength_gap_is_reported(ladder_report):
    # The 4->5 (innocent twin -> naive fit) distance diagnoses rival strength.
    twin = next(r for r in ladder_report.rungs if "innocent_twin" in r.name)
    assert twin.margin_to_next is not None and twin.margin_to_next > 0
