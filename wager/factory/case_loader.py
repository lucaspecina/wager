"""Loads the on-disk anatomy of a case (ARCHITECTURE 1) into runtime objects.

The reward path never reads the filesystem itself: tests and runners load
artifacts here and hand plain objects (callables, strings, contracts) to
wager.reward. Visibility rule: everything loaded here is factory/server side;
the agent only ever sees brief.md and the env handle.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Callable

from wager.contracts import Battery, CaseMeta

LADDER_DIRNAME = "ladder"


def load_world_source(case_dir: str | Path) -> str:
    return (Path(case_dir) / "world.py").read_text(encoding="utf-8")


def load_world_module(case_dir: str | Path):
    """Import world.py in-process (server side: the truth is ours) and return the
    module -- exposes sample, and (structured worlds) mechanism + PARAMS for the
    factory to perturb/ablate when deriving twins/ladder."""
    case_dir = Path(case_dir)
    module_name = f"wager_world_{case_dir.name}"
    spec = importlib.util.spec_from_file_location(module_name, case_dir / "world.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def load_world_sample(case_dir: str | Path) -> Callable:
    """The world's sample(regime, n, seed) callable."""
    return load_world_module(case_dir).sample


def load_battery(case_dir: str | Path) -> Battery:
    return Battery.from_json_file(Path(case_dir) / "battery.json")


def load_meta(case_dir: str | Path) -> CaseMeta:
    return CaseMeta.from_json_file(Path(case_dir) / "meta.json")


def load_ladder(case_dir: str | Path) -> list[tuple[str, str]]:
    """Committed ladder fixtures (rungs 2..N), sorted by filename.

    Rung 1 is never a fixture: it is world.py itself (Decision Log v0.11).
    """
    ladder_dir = Path(case_dir) / LADDER_DIRNAME
    return [
        (path.stem, path.read_text(encoding="utf-8"))
        for path in sorted(ladder_dir.glob("rung_*.py"))
    ]
