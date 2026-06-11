"""The score: weighted energy distance over the battery, minus lambda*MDL.

score = -sum(w_i * min(d_i, D_MAX_i)) - lambda * mdl(submission)

Seeds follow Decision Log v0.10: world side fixed per item (CRN across
submissions), model side derived per rep. The WorldSide precomputation is
shared by every submission scored against the same seed-set, which is both the
CRN guarantee and the main speed win.

ZERO-LLM ZONE. Production scoring runs with the sandbox network disabled.
Ensembles: mdl_bytes already supports [(weight, code)]; sandboxed mixture
scoring is not implemented in Slice 1 (no ensemble fixtures yet).
"""

import time
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Callable, Iterator

import numpy as np

from wager.contracts import (
    AnchorSet,
    Battery,
    ItemScore,
    Regime,
    ScoreReport,
    ScoringCost,
    ScoringParams,
)
from wager.reward.distance import TruthSide
from wager.reward.mdl import mdl_bytes
from wager.reward.sandbox import SandboxedSubmission, SandboxError
from wager.reward.seeds import derive_null_seed, derive_seed

D_MAX_FACTOR = 1.5  # D_MAX_item = 1.5 x D(truth, null), Decision Log v0.10/v0.12
_NULL_REF_REP = -7  # rep tag for the D_MAX reference draw; disjoint from j>=0


def regime_to_namespace(regime: Regime) -> SimpleNamespace:
    """Plain view of a Regime: what world.sample() and model() receive."""
    return SimpleNamespace(
        config=dict(regime.config),
        context=dict(regime.context),
        horizon=regime.horizon,
    )


class WorldSide:
    """Precomputed world side of one battery seed-set: truth samples,
    standardization stats and D_MAX caps. Server-side, in-process (the truth
    is ours); submissions never touch it.

    D_MAX_item = 1.5 x D(truth, null) per item. The null reference is the null
    MODEL when given (`null_sample`, the same pool-marginal model that anchors
    S_null) so the cap is consistently "1.5x worse than knowing nothing" and a
    rival that beats the null never caps. Without it, a column-permutation
    fallback is used (cheap tests only); see Decision Log v0.12.
    """

    def __init__(
        self,
        world_sample: Callable,
        battery: Battery,
        columns: list[str],
        n_samples: int,
        null_sample: Callable | None = None,
    ) -> None:
        self.battery = battery
        self.columns = list(columns)
        self.n_samples = n_samples
        self.truth_sides: list[TruthSide] = []
        self.d_maxes: list[float] = []
        for item in battery.items:
            ns = regime_to_namespace(item.regime)
            real = world_sample(ns, n_samples, item.seed_world)
            truth_side = TruthSide(real, self.columns)
            if null_sample is not None:
                null_seed = derive_seed(item.seed_world, _NULL_REF_REP)
                null_pred = null_sample(ns, n_samples, null_seed)
                d_null = truth_side.distance_to(null_pred)
            else:
                d_null = truth_side.permutation_null_distance(derive_null_seed(item.seed_world))
            self.truth_sides.append(truth_side)
            self.d_maxes.append(D_MAX_FACTOR * d_null)


def score_submission(
    code: str,
    world_side: WorldSide,
    params: ScoringParams,
    sandbox: SandboxedSubmission | None = None,
    rep_offset: int = 0,
) -> ScoreReport:
    """Score one submission against a precomputed world side.

    Pass an open `sandbox` to reuse one worker across many scorings (L1/L2);
    `rep_offset` shifts the model-side reps (L2 model-side-only resamples).
    """
    t0 = time.perf_counter()
    own_sandbox = sandbox is None
    if own_sandbox:
        sandbox = SandboxedSubmission(
            code, world_side.columns, timeout_s=params.model_call_timeout_s
        )
    try:
        weights = np.array([item.weight for item in world_side.battery.items], dtype=float)
        weights = weights / weights.sum()
        fidelity = 0.0
        items: list[ItemScore] = []
        for idx, item in enumerate(world_side.battery.items):
            truth_side = world_side.truth_sides[idx]
            d_max = world_side.d_maxes[idx]
            distances: list[float] = []
            errors = 0
            capped = 0
            for j in range(params.m_reps):
                seed_model = derive_seed(item.seed_world, j + rep_offset)
                try:
                    pred = sandbox.run(item.regime, params.n_samples, seed_model)
                    d = truth_side.distance_to(pred)
                    if d >= d_max:  # robustness bound: worse than 1.5x the null
                        d = d_max
                        capped += 1
                except SandboxError:
                    # crash/NaN: assign D_MAX (strictly worse than the null),
                    # NOT a clamp on a legitimate distance (ARCHITECTURE 8)
                    errors += 1
                    d = d_max
                distances.append(d)
            mean_distance = float(np.mean(distances))
            fidelity -= float(weights[idx]) * mean_distance
            items.append(
                ItemScore(
                    index=idx,
                    weight=float(weights[idx]),
                    mean_distance=mean_distance,
                    d_max=d_max,
                    capped_reps=capped,
                    sandbox_errors=errors,
                )
            )
        mdl = mdl_bytes(code)
        mdl_term = params.lambda_mdl * mdl
        return ScoreReport(
            fidelity=fidelity,
            mdl_bytes=mdl,
            mdl_term=mdl_term,
            raw_score=fidelity - mdl_term,
            items=items,
            cost=ScoringCost(
                k_items=len(world_side.battery.items),
                n_samples=params.n_samples,
                m_reps=params.m_reps,
                wall_seconds=time.perf_counter() - t0,
            ),
        )
    finally:
        if own_sandbox:
            sandbox.close()


def make_anchors(s_truth: float, s_naive: float, s_null: float) -> AnchorSet:
    return AnchorSet(s_truth=s_truth, s_naive=s_naive, s_null=s_null)


@contextmanager
def sandboxed_null_sample(
    null_code: str, columns: list[str], timeout_s: float = 10.0
) -> Iterator[Callable]:
    """Yield a sample(regime, n, seed) callable backed by the null MODEL run in
    the same sandbox as any submission. Used to reference D_MAX to the null that
    anchors S_null (Decision Log v0.12). The null model is a frozen factory
    artifact (no LLM at scoring time); the sandbox keeps the network disabled.
    """
    with SandboxedSubmission(null_code, columns, timeout_s=timeout_s) as sb:

        def _sample(regime, n: int, seed: int):
            view = regime if isinstance(regime, Regime) else Regime(
                config=dict(getattr(regime, "config", {}) or {}),
                context=dict(getattr(regime, "context", {}) or {}),
                horizon=getattr(regime, "horizon", None),
            )
            return sb.run(view, n, seed)

        yield _sample
