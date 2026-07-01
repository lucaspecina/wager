"""Report contracts emitted by the reward path (scoring, L1 ladder, L2 variance)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RivalAccess(BaseModel):
    """The data access a gap-defining rival was fit under (Decision Log v0.30,
    self-describing certificates). Required so an access drift is visible in EVERY
    dossier instead of discoverable only by reading code (which is exactly how the
    v0.18->v0.29 drift went unnoticed). Doctrine (ARCHITECTURE §7, v0.29): the
    theory gap MUST be measured vs an EXPERIMENTAL-access rival (d-exp, access
    equalized to the agent); the mechanistic gap vs an OBSERVATIONAL one (d-obs / a).
    `standardized=False` flags the proto (d-exp) (ad-hoc do(dose) grid) that exists
    until the v0.29 standardized experimental budget lands (paso 3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: Literal["observational", "experimental"]
    n_rows: int = Field(ge=0)  # fitting budget (total rows the rival saw)
    seed0: int  # deterministic seed origin (reproducibility)
    grid: str | None = None  # experimental: factorial grid description; None for obs
    standardized: bool = False  # True once the v0.29 standardized (d-exp) exists


class ItemScore(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    weight: float  # normalized (w / sum(w))
    mean_distance: float  # mean over m reps, after per-rep cap at d_max
    d_max: float  # 1.5 x D(truth, per-item null) (Decision Log v0.10)
    capped_reps: int  # reps that hit the cap (incl. sandbox errors)
    sandbox_errors: int


class ScoringCost(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    k_items: int
    n_samples: int
    m_reps: int
    wall_seconds: float


class ScoreReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    fidelity: float  # -sum(w_i * d_i), <= 0
    mdl_bytes: int
    mdl_term: float  # lambda * mdl_bytes
    raw_score: float  # fidelity - mdl_term
    items: list[ItemScore]
    cost: ScoringCost


class AnchorSet(BaseModel):
    """Anchors computed with the SAME full score function as any submission
    (Decision Log v0.10). s_truth runs world.py through the same pipeline
    (same model-side seeds) so R(world.py) == 1.0 exactly (v0.11)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    s_truth: float
    s_naive: float
    s_null: float

    def r_of(self, raw_score: float) -> tuple[float, float]:
        """Returns (r_clipped, r_unclipped)."""
        denom = self.s_truth - self.s_naive
        if denom <= 0:
            raise ValueError(
                "s_truth - s_naive <= 0: the world does not discriminate "
                "(mechanistic gap ~ 0); the case must be rejected"
            )
        unclipped = (raw_score - self.s_naive) / denom
        return (min(max(unclipped, 0.0), 1.0), unclipped)

    @property
    def normalization_range(self) -> float:
        """S_truth - S_naive: the range R maps to [0, 1]; L1 margins are
        measured against THIS (Decision Log v0.12), not S_truth - S_null.
        R clips everything below S_naive to 0, and the null can be a
        pathological off-support outlier (it ignores controlled variables),
        so S_truth - S_null is a misleading denominator for margins."""
        return self.s_truth - self.s_naive

    @property
    def null_range(self) -> float:
        """S_truth - S_null: reported as a diagnostic only (the null is the
        D_MAX reference and the 'know nothing' floor), not the margin range."""
        return self.s_truth - self.s_null


class LadderRung(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    raw_score: float
    r: float
    r_unclipped: float
    # (raw_this - raw_next) / (s_truth - s_naive), i.e. the gap in normalized-R
    # units; None for the last rung (Decision Log v0.12)
    margin_to_next: float | None = None
    # How to read this rung's R (decided by construction, Decision Log v0.12):
    #  - "anchor:S_truth"  -> R == 1 by construction (world.py through the same
    #     pipeline); NOT a measurement of fidelity.
    #  - "anchor:S_naive"  -> R == 0 by construction; THIS fixture IS the same
    #     object as the S_naive anchor of the normalization (the naive rival a).
    #  - "reference:S_null" -> the D_MAX reference / diagnostic floor; below the
    #     R scale (R clips to 0), not an anchor of [0, 1].
    #  - "measurement"      -> a genuine score; its R carries information.
    kind: Literal["anchor:S_truth", "anchor:S_naive", "reference:S_null", "measurement"]


class LadderReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    rungs: list[LadderRung]  # all rungs reported, not just pass/fail (v0.11)
    anchors: AnchorSet
    margin_required: float
    passed: bool
    cost: ScoringCost


class VarianceReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    rung_name: str  # the mid-ladder submission measured
    r_production: float  # R under the fixed production seeds
    b_total: int  # full seed-set resamples (world + model side)
    r_values: list[float]
    cv_r: float
    s_truth_values: list[float]
    cv_s_truth: float
    b_model_side: int  # resamples varying only model-side reps (world fixed)
    r_values_model_side: list[float]
    total_std: float
    model_side_std: float
    world_side_std: float  # sqrt(max(total^2 - model^2, 0))
    cost: ScoringCost
