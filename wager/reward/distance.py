"""Sample-based energy distance with truth-side standardization.

D default of the score (ARCHITECTURE 9). Standardization uses the statistics
of the TRUTH sample of each battery item (per-item, declared here): the truth
side is fixed per item (CRN), so every submission is standardized identically.
"""

import numpy as np
import pandas as pd
from scipy.spatial.distance import cdist


def energy_distance(x: np.ndarray, y: np.ndarray) -> float:
    """V-statistic estimate of the energy distance between two samples.

    Non-negative, zero iff the samples are identical point sets.
    """
    dxy = cdist(x, y).mean()
    dxx = cdist(x, x).mean()
    dyy = cdist(y, y).mean()
    return float(2.0 * dxy - dxx - dyy)


class TruthSide:
    """Precomputed truth side of one battery item.

    Caches the standardized truth sample and its self-distance so that scoring
    m reps x many submissions against the same item only pays the cross terms.
    """

    def __init__(self, real: pd.DataFrame, columns: list[str]) -> None:
        arr = real[columns].to_numpy(dtype=float)
        self.columns = columns
        self.mean = arr.mean(axis=0)
        self.std = arr.std(axis=0)
        # Clamp near-zero std with a RELATIVE tolerance, not == 0: a controlled
        # variable (e.g. dose under do(dose=d)) is constant, but float roundoff
        # makes its std ~1e-15 (not exactly 0); the == 0 check missed it, so a
        # model that got that column WRONG (e.g. the null ignoring the regime)
        # divided by ~1e-15 and the distance exploded to ~1e16, breaking D_MAX
        # on every do() item (Decision Log v0.21).
        tol = 1e-8 * (np.abs(self.mean) + 1.0)
        self.std = np.where(self.std < tol, 1.0, self.std)
        self.z = (arr - self.mean) / self.std
        self._dxx = cdist(self.z, self.z).mean()

    def standardize(self, df: pd.DataFrame) -> np.ndarray:
        arr = df[self.columns].to_numpy(dtype=float)
        return (arr - self.mean) / self.std

    def distance_to(self, pred: pd.DataFrame) -> float:
        zp = self.standardize(pred)
        dxy = cdist(self.z, zp).mean()
        dpp = cdist(zp, zp).mean()
        return float(2.0 * dxy - self._dxx - dpp)

    def permutation_null_distance(self, rng_seed: int) -> float:
        """D(truth, column-permutation of the truth sample): exact truth
        marginals, dependencies destroyed. A self-contained fallback reference
        for D_MAX when no null MODEL is available (cheap wiring tests). NOTE:
        this keeps the TRUTH's correct marginals, so it understates how bad
        "knowing nothing" is in off-support regimes - the null MODEL is the
        production reference (Decision Log v0.12)."""
        rng = np.random.default_rng(rng_seed)
        z_null = self.z.copy()
        for j in range(z_null.shape[1]):
            z_null[:, j] = rng.permutation(z_null[:, j])
        dxy = cdist(self.z, z_null).mean()
        dnn = cdist(z_null, z_null).mean()
        return float(2.0 * dxy - self._dxx - dnn)
