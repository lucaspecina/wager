"""Decision functionals scored ON TOP of energy distance (ARCHITECTURE §9.3).

ZERO-LLM ZONE. Pure numpy/pandas. A functional `F` maps a sample DataFrame to a
scalar; the per-item contribution to the combined distance is

    Σ_F  c_F · S_F( |F(pred) − F(real)| )

standardized BY TYPE so c_F is dimensionless and transferable across functionals
and suites (Decision Log v0.28 — the null-relative per-item normalization that
explodes at F(truth)≈F(null) is FORBIDDEN in the metric):

    exceedance     -> |ΔP|                     (raw; native [0,1])
    quantile       -> |Δ| / σ_truth(column)    (same play as energy standardization)
    subgroup_mean  -> |Δ| / σ_truth(column)
    expected_loss  -> |ΔL| / declared loss range

An empty functional list -> zero extra distance: the combined score is then
IDENTICAL to the energy score of §9 (identity by construction, the dummy suite).
"""

import numpy as np
import pandas as pd

from wager.contracts import FunctionalSpec


def functional_value(spec: FunctionalSpec, df: pd.DataFrame) -> float:
    """F(samples) for one declared functional. Computed from samples, not params."""
    col = df[spec.column].to_numpy(dtype=float)
    if spec.name == "exceedance":
        hit = col < spec.threshold if spec.direction == "below" else col > spec.threshold
        return float(np.mean(hit))
    if spec.name == "quantile":
        return float(np.quantile(col, spec.tau))
    if spec.name == "subgroup_mean":
        raise NotImplementedError(
            "subgroup_mean needs a declared subgroup filter; add when a case requires it"
        )
    if spec.name == "expected_loss":
        raise NotImplementedError(
            "expected_loss needs a declared loss rule + range; add when a case requires it"
        )
    raise ValueError(f"unknown functional: {spec.name}")


class FunctionalScorer:
    """Per-item functional contribution, built once from the truth sample.

    Holds F(real) and the truth column σ's; `extra_distance(pred)` returns the
    standardized, c_F-weighted sum added to the energy distance. Built with the
    SAME truth sample (CRN) the TruthSide standardizes against.
    """

    def __init__(
        self,
        specs: list[FunctionalSpec],
        truth_df: pd.DataFrame,
        columns: list[str],
        truth_std: np.ndarray,
        c_f: float | dict[str, float] = 1.0,
    ) -> None:
        self.specs = list(specs)
        self.c_f = c_f
        self.col_std = {c: float(truth_std[i]) for i, c in enumerate(columns)}
        self.f_real = [functional_value(s, truth_df) for s in self.specs]

    def _weight(self, spec: FunctionalSpec) -> float:
        return self.c_f.get(spec.name, 1.0) if isinstance(self.c_f, dict) else float(self.c_f)

    def _standardize(self, spec: FunctionalSpec, delta: float) -> float:
        if spec.name in ("quantile", "subgroup_mean"):
            return delta / (self.col_std.get(spec.column, 1.0) or 1.0)
        # exceedance (and 0-1 expected_loss): raw, already dimensionless in [0,1]
        return delta

    def extra_distance(self, pred: pd.DataFrame) -> float:
        """Σ c_F · S_F(|F(pred) − F(real)|). 0.0 when no functionals are declared
        (identity by construction)."""
        total = 0.0
        for spec, f_real in zip(self.specs, self.f_real):
            f_pred = functional_value(spec, pred)
            total += self._weight(spec) * self._standardize(spec, abs(f_pred - f_real))
        return total
