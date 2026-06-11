"""Contracts for worlds: regimes, observables schema, control surface, sources.

A Regime is a point of the declared control surface plus non-intervenible
context (ARCHITECTURE 2.1). `do(X=x)` is the degenerate minimal case: a single
constant entry in `config`. An empty `config` means the world runs its natural
assignment process (mechanism-layer, Decision Log v0.11).
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class Regime(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    config: dict[str, float] = Field(default_factory=dict)
    context: dict[str, float] = Field(default_factory=dict)
    horizon: int | None = None


class ColumnSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    dtype: Literal["float", "int", "category"]
    unit: str | None = None
    description: str | None = None


class KnobSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    low: float
    high: float


class ControlSurface(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    knobs: list[KnobSpec] = Field(default_factory=list)
    context_vars: list[KnobSpec] = Field(default_factory=list)


class SourceSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    cost: float
    n_max: int
    description: str
