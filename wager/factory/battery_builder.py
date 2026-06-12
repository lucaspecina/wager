"""Derive the battery from the declared case (ARCHITECTURE §6, factory side).

Algorithm: sample candidate regimes from the control surface -> NORMALIZED
disagreement (D / D_MAX_item in [0,1]) among {truth, rivals}, dropping items that
do not even separate truth from the null -> relevance from the declared stakes
(decision variable + population mix) -> weight = relevance x disagreement_norm ->
dose-stratified top-K + a low-weight audit tail -> battery.json.

The normalization by D_MAX (Decision Log v0.22, the natural consequence of the
universal cap) makes disagreement a fraction of the item's own maximum credible
divergence, killing scale-absolute dominance with NO new constants. The stakes
relevance modulates context (it must not be flat) so off-support extremes land in
the audit tail, not the top-K. Deterministic (seeded) and reproducible.
"""

from types import SimpleNamespace
from typing import Callable

import numpy as np

from wager.contracts import Battery, BatteryItem, StakesSpec
from wager.contracts.world import Regime
from wager.reward.distance import energy_distance

D_MAX_FACTOR = 1.5  # D_MAX_item = 1.5 x D(truth, null), as in scoring
NOISE_FLOOR_MULT = 3.0  # eligibility: D(truth, null) must exceed 3 x sampling noise


def _ns(r: Regime) -> SimpleNamespace:
    return SimpleNamespace(config=dict(r.config), context=dict(r.context), horizon=r.horizon)


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


def _z(arr, mu, sd):
    return (arr - mu) / sd


def disagreement_norm(
    samplers: list[Callable], null_fn: Callable, regime: Regime,
    columns: list[str], n_mc: int, seed: int,
) -> tuple[float, bool]:
    """Returns (disagreement_norm in [0,1], eligible). norm = mean pairwise
    energy distance among {truth, rivals} (each capped at D_MAX) / D_MAX. eligible
    iff D(truth, null) > 3 x sampling-noise floor (else the item does not even
    separate truth from the null -> it cannot discriminate)."""
    ns = _ns(regime)
    truth = samplers[0](ns, n_mc, seed)[columns].to_numpy(dtype=float)
    truth2 = samplers[0](ns, n_mc, seed + 7919)[columns].to_numpy(dtype=float)  # noise floor
    mu = truth.mean(0)
    sd = truth.std(0)
    sd = np.where(sd < 1e-8 * (np.abs(mu) + 1.0), 1.0, sd)  # relative tol (v0.21)
    zt = _z(truth, mu, sd)
    z_null = _z(null_fn(ns, n_mc, seed + 99)[columns].to_numpy(dtype=float), mu, sd)
    d_tn = energy_distance(zt, z_null)
    noise = energy_distance(zt, _z(truth2, mu, sd))
    if d_tn <= NOISE_FLOOR_MULT * noise:
        return 0.0, False
    d_max = D_MAX_FACTOR * d_tn
    zs = [zt]
    for fn in samplers[1:]:
        try:
            zs.append(_z(fn(ns, n_mc, seed + 1 + len(zs))[columns].to_numpy(dtype=float), mu, sd))
        except Exception:  # noqa: BLE001
            zs.append(None)
    norm_dists = []
    for a in range(len(zs)):
        for b in range(a + 1, len(zs)):
            if zs[a] is not None and zs[b] is not None:
                norm_dists.append(min(energy_distance(zs[a], zs[b]), d_max) / d_max)
    return (float(np.mean(norm_dists)) if norm_dists else 0.0), True


def stakes_relevance(regime: Regime, stakes: StakesSpec) -> float:
    """Declared relevance from the brief: full weight if the regime sets a decision
    variable, times the decision-variable VALUE emphasis (e.g. doses outside the
    historical record matter more -- Decision Log v0.23), times the population-mix
    density over context (NOT flat -- Decision Log v0.22)."""
    rel = 1.0 if any(v in regime.config for v in stakes.decision_variables) else 0.4
    for var, spec in stakes.decision_relevance.items():
        if var in regime.config and regime.config[var] >= spec.get("out_of_record_above", float("inf")):
            rel *= spec.get("out_of_record_weight", 1.0)
    for var, spec in stakes.context_relevance.items():
        center = spec.get("center", 0.0)
        val = regime.context.get(var, center)
        sd = spec.get("sd", 1.0) or 1.0
        g = float(np.exp(-0.5 * ((val - center) / sd) ** 2))
        # out-of-record TAIL (Decision Log v0.24): the brief wants populations
        # outside the record too -> a floor so atypical populations are not
        # Gaussian-killed (parallel to the dose out_of_record fix). The Gaussian
        # still makes typical populations dominate.
        thr = spec.get("out_of_record_above_abs")
        if thr is not None and abs(val - center) >= thr:
            g = max(g, spec.get("out_of_record_floor", 0.0))
        rel *= g
    return rel


def build_battery(
    world_sample: Callable,
    rivals: list[Callable],
    null_fn: Callable,
    columns: list[str],
    stakes: StakesSpec,
    n_candidates: int = 400,
    k_top: int = 12,
    k_audit: int = 4,
    n_mc: int = 400,
    seed: int = 314159,
    dedup_radius: float = 0.0,
) -> Battery:
    rng = np.random.default_rng(seed)
    candidates = sample_candidates(rng, n_candidates)
    samplers = [world_sample, *rivals]

    scored = []
    for i, r in enumerate(candidates):
        dis, eligible = disagreement_norm(samplers, null_fn, r, columns, n_mc, seed + 1000 * i)
        if not eligible:
            continue  # item does not separate truth from null -> non-discriminating
        scored.append((stakes_relevance(r, stakes) * dis, r))

    # dose-stratified top-K (force coverage across the dose range) + audit tail
    def _stratum(r: Regime) -> str:
        if "dose" not in r.config:
            return "obs"
        return f"dose{int(min(r.config['dose'], 9.999) // 2.5)}"

    def _too_close(r: Regime, chosen: list) -> bool:
        # diversity/dedup radius in (dose, cohort) space (Decision Log v0.24):
        # avoid near-duplicate probes (e.g. the dose 1.9-2.9 cluster)
        if dedup_radius <= 0:
            return False
        d = r.config.get("dose", -5.0)
        c = r.context.get("cohort", 0.0)
        for _, rr in chosen:
            dd = rr.config.get("dose", -5.0)
            cc = rr.context.get("cohort", 0.0)
            if ((d - dd) ** 2 + (c - cc) ** 2) ** 0.5 < dedup_radius:
                return True
        return False

    by_stratum: dict[str, list] = {}
    for w, r in sorted(scored, key=lambda t: -t[0]):
        by_stratum.setdefault(_stratum(r), []).append((w, r))
    top = []
    cursor = {s: 0 for s in by_stratum}
    progress = True
    while len(top) < k_top and progress:
        progress = False
        for s in sorted(by_stratum):
            items_s = by_stratum[s]
            while cursor[s] < len(items_s):
                cand = items_s[cursor[s]]
                cursor[s] += 1
                if not _too_close(cand[1], top):
                    top.append(cand)
                    progress = True
                    break
            if len(top) >= k_top:
                break
    chosen = {id(t[1]) for t in top}
    rest = [t for t in scored if id(t[1]) not in chosen]
    audit_idx = rng.choice(len(rest), size=min(k_audit, len(rest)), replace=False) if rest else []
    audit = [rest[j] for j in audit_idx]

    total_top = sum(w for w, _ in top) or 1.0
    items, sw = [], 11000
    for w, r in top:
        items.append(BatteryItem(weight=float(w / total_top), regime=r, seed_world=sw))
        sw += 1
    audit_w = 0.1 / max(len(audit), 1)
    for _, r in audit:
        items.append(BatteryItem(weight=float(audit_w), regime=r, seed_world=sw))
        sw += 1
    return Battery(items=items)
