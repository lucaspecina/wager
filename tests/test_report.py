"""Smoke test for the human-inspection report generator (needs [report] extra)."""

import importlib.util
import json
from pathlib import Path

import pytest

CASE_DIR = Path(__file__).resolve().parents[1] / "cases" / "dummy_dose_v0"


@pytest.mark.slow
@pytest.mark.skipif(importlib.util.find_spec("markdown") is None, reason="install .[report]")
def test_build_report_has_all_sections():
    from wager.report.case_report import build_report

    trace = None
    for c in sorted((CASE_DIR / "traces").glob("e05_*.json")):
        if json.loads(c.read_text(encoding="utf-8")).get("submission_code"):
            trace = c
            break
    html = build_report(CASE_DIR, trace)
    for needle in ("<html>", "The brief", "The hidden truth", "secret exam",
                   "agent&#x27;s full trajectory", "The evaluation"):
        assert needle in html, needle
    if trace:  # the evaluation re-scored a real submission
        assert "final R" in html and "Per-item grading" in html
