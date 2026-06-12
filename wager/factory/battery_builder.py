"""Derive the battery from the declared case (ARCHITECTURE §6, factory side).

Algorithm: sample candidate regimes from the control surface -> disagreement(r)
between {truth, rivals} -> relevance(r) from the declared stakes -> weight
w ~ relevance x disagreement -> top-K + a low-weight uniform audit tail ->
battery.json. The battery IS the relevance, formalized: mass concentrates where
the tempting wrong rivals die -- exactly where the agent must understand the
world to predict well.

Deterministic (seeded) so the derived battery is reproducible and committable.
"""

from typing import Callable

import numpy as np

from wager.contracts import Battery, BatteryItem
from wager.contracts.world import Regime
from wager.reward.distance import energy_distance


def sample_candidates(rng, n: int, dose_lo=0.0, dose_hi=10.0) -> list[Regime]:
    regimes = []
    for _ in range(n):
        u = rng.random()
        if u < 0.65:  # interventional, in-surface
            regimes.append(Regime(config={"dose": float(rng.uniform(dose_lo, dose_hi))},
                                   context={"cohort": float(rng.uniform(-1.5, 1.5))}))
        elif u < 0.80:  # off-support: extreme cohort (outside the historical record)
            sign = 1.0 if rng.random() < 0.5 else -1.0
            regimes.append(Regime(config={"dose": float(rng.uniform(dose_lo, dose_hi))},
                                   context={"cohort": float(sign * rng.uniform(1.5, 2.5))}))
        else:  # observational
            regimes.append(Regime(config={}, context={"cohort": float(rng.uniform(-1.0, 1.0))}))
    return regimes


D_MAX_FACTOR = 1.5  # D_MAX_item = 1.5 x D(truth, null), as in scoring


def _disagreement(
    samplers: list[Callable], null_fn: Callable, regime: Regime,
    columns: list[str], n_mc: int, seed: int,
) -> float:
    """Mean pairwise energy distance among {truth, rivals} at this regime,
    standardized by the truth sample's stats and CAPPED at the per-regime
    D_MAX = 1.5 x D(truth, null) -- the SAME universal cap as scoring (Decision
    Log v0.21), so no single rival's distance can dominate the weights beyond the
    'worse than knowing nothing' bound."""
    from types import SimpleNamespace

    ns = SimpleNamespace(config=dict(regime.config), context=dict(regime.context), horizon=regime.horizon)
    draws = []
    for i, fn in enumerate(samplers):
        try:
            draws.append(fn(ns, n_mc, seed + i)[columns].to_numpy(dtype=float))
        except Exception:  # noqa: BLE001
            draws.append(None)
    truth = draws[0]
    mu, sd = truth.mean(0), truth.std(0)
    sd = np.where(sd < 1e-8 * (np.abs(mu) + 1.0), 1.0, sd)  # relative tol (v0.21)
    z = [None if d is None else (d - mu) / sd for d in draws]
    z_null = (null_fn(ns, n_mc, seed + 99)[columns].to_numpy(dtype=float) - mu) / sd
    d_max = D_MAX_FACTOR * energy_distance(z[0], z_null)
    dists = []
    for a in range(len(z)):
        for b in range(a + 1, len(z)):
            if z[a] is not None and z[b] is not None:
                dists.append(min(energy_distance(z[a], z[b]), d_max))
    return float(np.mean(dists)) if dists else 0.0


def build_battery(
    world_sample: Callable,
    rivals: list[Callable],
    null_fn: Callable,
    columns: list[str],
    decision_vars: list[str],
    n_candidates: int = 400,
    k_top: int = 12,
    k_audit: int = 4,
    n_mc: int = 400,
    seed: int = 314159,
) -> Battery:
    rng = np.random.default_rng(seed)
    candidates = sample_candidates(rng, n_candidates)
    samplers = [world_sample, *rivals]

    scored = []
    for i, r in enumerate(candidates):
        dis = _disagreement(samplers, null_fn, r, columns, n_mc, seed + 1000 * i)
        # relevance from the declared stakes: decision-relevant regimes (those that
        # set a decision var) weigh full; AND a taper away from the historical
        # support (cohort ~ 0) so off-support extreme regimes -- where a rival
        # merely EXTRAPOLATES badly -- do not dominate the top-K (they belong in
        # the low-weight audit tail; Decision Log v0.20). The taper keeps them
        # present (the brief does care about out-of-record populations) without
        # letting extrapolation blowups crowd out the discriminating in-support
        # regimes where the trap actually bites.
        cohort = r.context.get("cohort", 0.0)
        taper = float(np.exp(-0.5 * (cohort / 1.5) ** 2))
        rel = (1.0 if any(v in r.config for v in decision_vars) else 0.4) * taper
        scored.append((rel * dis, r))

    # STRATIFIED top-K by dose band (+ observational): weight by disagreement
    # WITHIN each band, but force coverage across the dose range so the battery
    # also separates small degradations (e.g. a param perturbation shows in the
    # saturation curvature at mid dose), not only the big ones at high dose
    # (Decision Log v0.20).
    def _stratum(r: Regime) -> str:
        if "dose" not in r.config:
            return "obs"
        d = r.config["dose"]
        return f"dose{int(min(d, 9.999) // 2.5)}"  # 4 dose bands over [0,10)

    by_stratum: dict[str, list] = {}
    for w, r in sorted(scored, key=lambda t: -t[0]):
        by_stratum.setdefault(_stratum(r), []).append((w, r))
    top = []
    rnd = 0
    while len(top) < k_top and any(rnd < len(v) for v in by_stratum.values()):
        for s in sorted(by_stratum):
            if rnd < len(by_stratum[s]) and len(top) < k_top:
                top.append(by_stratum[s][rnd])
        rnd += 1
    chosen = {id(t[1]) for t in top}
    rest = [t for t in scored if id(t[1]) not in chosen]
    audit_idx = rng.choice(len(rest), size=min(k_audit, len(rest)), replace=False) if rest else []
    audit = [rest[j] for j in audit_idx]

    total_top = sum(w for w, _ in top) or 1.0
    items = []
    sw = 11000
    for w, r in top:
        items.append(BatteryItem(weight=float(w / total_top), regime=r, seed_world=sw))
        sw += 1
    audit_w = 0.1 * (1.0 / max(len(audit), 1))  # low-weight tail, ~10% mass total
    for _, r in audit:
        items.append(BatteryItem(weight=float(audit_w), regime=r, seed_world=sw))
        sw += 1
    return Battery(items=items)
