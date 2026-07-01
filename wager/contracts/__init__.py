"""Pydantic contracts shared by the factory and the reward path.

This package must stay importable from the reward path: pydantic + stdlib only.
"""

from wager.contracts.case import (
    Battery,
    BatteryItem,
    CaseMeta,
    FunctionalSpec,
    OperatorInstance,
    ScoringParams,
    StakesSpec,
)
from wager.contracts.episode import (
    EpisodeConfig,
    ExperimentCost,
    ExperimentDesign,
    SourceConfig,
    SubmitResult,
)
from wager.contracts.reports import (
    AnchorSet,
    ItemScore,
    LadderReport,
    LadderRung,
    RivalAccess,
    ScoreReport,
    ScoringCost,
    VarianceReport,
)
from wager.contracts.world import (
    ColumnSpec,
    ControlSurface,
    KnobSpec,
    Regime,
    SourceSpec,
)

__all__ = [
    "AnchorSet",
    "Battery",
    "BatteryItem",
    "CaseMeta",
    "ColumnSpec",
    "ControlSurface",
    "EpisodeConfig",
    "ExperimentCost",
    "ExperimentDesign",
    "ItemScore",
    "KnobSpec",
    "LadderReport",
    "LadderRung",
    "OperatorInstance",
    "Regime",
    "RivalAccess",
    "ScoreReport",
    "ScoringCost",
    "ScoringParams",
    "SourceConfig",
    "SourceSpec",
    "StakesSpec",
    "FunctionalSpec",
    "SubmitResult",
    "VarianceReport",
]
