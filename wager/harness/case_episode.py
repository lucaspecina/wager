"""Build a WorldServer for a case (shared by C2 scripted solvers and C3 LLM).

Loads the server-side artifacts (world, battery, ladder anchors used for scoring,
episode config) and assembles the authority. The agent only ever sees brief +
verbs; everything loaded here is server side.
"""

from pathlib import Path

from wager.factory.case_loader import (
    load_battery,
    load_ladder,
    load_meta,
    load_world_sample,
    load_world_source,
)
from wager.harness.world_server import ScoringArtifacts, WorldServer


def build_world_server(case_dir: str | Path, seed_offset: int = 0) -> WorldServer:
    case_dir = Path(case_dir)
    meta = load_meta(case_dir)
    if meta.episode is None:
        raise ValueError(f"{meta.case_id} has no episode config (meta.episode)")
    ladder = dict(load_ladder(case_dir))
    brief = (case_dir / "brief.md").read_text(encoding="utf-8")
    scoring = ScoringArtifacts(
        world_source=load_world_source(case_dir),
        naive_code=ladder["rung_5_naive_fit"],  # the S_naive anchor (rival a)
        null_code=ladder["rung_6_null"],  # the S_null / D_MAX reference
        battery=load_battery(case_dir),
        params=meta.scoring,
    )
    return WorldServer(
        world_sample=load_world_sample(case_dir),
        columns=meta.column_names,
        brief=brief,
        config=meta.episode,
        scoring=scoring,
        control_surface=meta.episode.control_surface,
        case_id=meta.case_id,
        seed_offset=seed_offset,
    )
