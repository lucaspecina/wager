"""Contracts for the interactive episode: verbs, costs, submit result.

ExperimentDesign is agent-supplied, so it is the data-only boundary (Decision
Log v0.14, precision 3): typed scalar dicts with extra="forbid" reject callables
and stray objects at validation time.
"""

from pydantic import BaseModel, ConfigDict, Field

from wager.contracts.world import Regime


class ExperimentDesign(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    config: dict[str, float] = Field(default_factory=dict)  # do(): fixed knobs
    context: dict[str, float] = Field(default_factory=dict)
    n: int = Field(gt=0, le=5000)  # bounded: runaway guard on a single draw
    horizon: int | None = None

    def to_regime(self) -> Regime:
        return Regime(config=dict(self.config), context=dict(self.context), horizon=self.horizon)


class SourceConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cost_per_row: float = Field(ge=0)
    config: dict[str, float] = Field(default_factory=dict)
    context: dict[str, float] = Field(default_factory=dict)


class ExperimentCost(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cost_fixed: float = Field(ge=0)
    cost_per_row: float = Field(ge=0)


class EpisodeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    budget: float = Field(gt=0)
    observe_sources: dict[str, SourceConfig]
    experiment: ExperimentCost
    smoke_regimes: list[Regime] = Field(min_length=1)
    control_surface: dict = Field(default_factory=dict)  # what describe() shows


class SubmitResult(BaseModel):
    """What the AGENT sees on submit. R (the battery score) is server-side and
    NOT included here -- the battery is secret."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    error: str | None = None  # actionable smoke error when not accepted
