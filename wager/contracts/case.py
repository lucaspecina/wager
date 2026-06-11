"""Contracts for cases: battery, declared operators, stakes, scoring params.

battery.json holds one world-side seed per item (Decision Log v0.10): the
model-side seeds are derived as derive_seed(seed_world, rep), never persisted.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from wager.contracts.episode import EpisodeConfig
from wager.contracts.world import ColumnSpec, Regime


class BatteryItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    weight: float = Field(gt=0)
    regime: Regime
    seed_world: int


class Battery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    items: list[BatteryItem] = Field(min_length=1)

    @classmethod
    def from_json_file(cls, path: str | Path) -> "Battery":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_json_file(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.model_dump(), indent=2) + "\n", encoding="utf-8"
        )


class OperatorInstance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    layer: Literal["mechanism", "channel", "sampling", "meta"]
    knobs: dict[str, float] = Field(default_factory=dict)
    # mechanism-layer operators declare param overrides that ABLATE them, so the
    # factory can render the world with this operator off (derived twins / ladder)
    ablation: dict[str, float] = Field(default_factory=dict)


class StakesSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    narrative: str
    decision_variables: list[str]


class ScoringParams(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    lambda_mdl: float = Field(ge=0)
    # lambda calibrated so the MDL term is ~5% of (S_truth - S_null) on this
    # case; provisional until calibrated over the E1 suite (Decision Log v0.11)
    lambda_provisional: bool = True
    n_samples: int = 1000
    m_reps: int = 2  # v0 default (Decision Log v0.12 item 2): CV(R)~1.2% on the
    # dummy, world-side noise dominates so m>2 buys little; raise per case if the
    # L2 protocol shows model-side noise matters
    model_call_timeout_s: float = 10.0


class CaseMeta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    suite: str
    columns: list[ColumnSpec] = Field(min_length=1)
    operators: list[OperatorInstance]
    stakes: StakesSpec
    scoring: ScoringParams
    episode: EpisodeConfig | None = None
    prior_reliability: float | None = None

    @classmethod
    def from_json_file(cls, path: str | Path) -> "CaseMeta":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]
