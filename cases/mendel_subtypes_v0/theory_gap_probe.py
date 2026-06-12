"""Mendel theory-gap probe -- tests pre-registered prediction (ii) (Decision Log
v0.25): the theory gap should be LARGE (unlike the dummy's 0.062).

Self-contained (does NOT touch the shared factory, whose context var is hardwired
to 'cohort'; the factory generalization to per-case context vars is the next
increment). It fits three rivals on Mendel and certifies, mirroring the dummy's
derive_certificates exactly:
  - naive        : unimodal joint Gaussian of the observational pool (rival a)
  - no_latent    : best generative fit over observables, poly means on
                   (dose, mix_logit) + a SINGLE Gaussian residual -> UNIMODAL, so
                   it cannot reproduce the bimodal (marker, outcome) joint (the
                   capacity ladder d -- the theory-gap reference)
  - latent_disc  : a model that POSITS the latent: cluster the biomarker -> 2
                   subtypes, per-subtype dose-response, mix as p(mix_logit). This
                   should recover R~=1 -- the gap is the VALUE of positing the
                   latent, not a weak-rival artifact (the failure mode caught in
                   the dummy at v0.18).

Run:  .venv/Scripts/python cases/mendel_subtypes_v0/theory_gap_probe.py
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures

CASE_DIR = Path(__file__).parent
sys.path.insert(0, str(CASE_DIR))

import world  # the truth (server-side)

from wager.contracts import Battery, BatteryItem, Regime, ScoringParams
from wager.reward.scorer import WorldSide, make_anchors, score_callable

COLS = ["dose", "marker", "outcome"]
CTX = "mix_logit"


def ns(config=None, context=None):
    return SimpleNamespace(config=config or {}, context=context or {}, horizon=None)


# ---- data a capable rival would buy ---------------------------------------
def observational_pool(n, seed):
    return world.sample(ns({}, {CTX: 0.0}), n, seed)


def experimental_grid(levels, mixes, n, seed0):
    frames, s = [], seed0
    for lv in levels:
        for mx in mixes:
            df = world.sample(ns({"dose": float(lv)}, {CTX: float(mx)}), n, s).copy()
            df[CTX] = mx
            frames.append(df)
            s += 1
    return pd.concat(frames, ignore_index=True)


# ---- rival (a) naive: unimodal joint Gaussian of the pool ------------------
def rival_naive(pool):
    mu = pool[COLS].mean().to_numpy()
    cov = pool[COLS].cov().to_numpy()

    def sample(regime, n, seed):
        rng = np.random.default_rng(seed)
        if "dose" in regime.config:
            d = float(regime.config["dose"])
            mu_c = mu[1:] + cov[1:, 0] / cov[0, 0] * (d - mu[0])
            cov_c = cov[1:, 1:] - np.outer(cov[1:, 0], cov[0, 1:]) / cov[0, 0]
            draw = rng.multivariate_normal(mu_c, cov_c, n)
            return pd.DataFrame({"dose": np.full(n, d), "marker": draw[:, 0], "outcome": draw[:, 1]})
        draw = rng.multivariate_normal(mu, cov, n)
        return pd.DataFrame({"dose": np.clip(draw[:, 0], 0, 10), "marker": draw[:, 1], "outcome": draw[:, 2]})

    return sample


# ---- rival (d) no-latent: poly means + SINGLE Gaussian residual (unimodal) --
def rival_no_latent(train, deg=3):
    def _mk():
        return make_pipeline(PolynomialFeatures(deg), LinearRegression())

    X = train[["dose", CTX]].to_numpy()
    m_model = _mk().fit(X, train["marker"].to_numpy())
    o_model = _mk().fit(X, train["outcome"].to_numpy())
    rm = train["marker"].to_numpy() - m_model.predict(X)
    ro = train["outcome"].to_numpy() - o_model.predict(X)
    resid_cov = np.cov(np.vstack([rm, ro]))
    dose_pool = train["dose"].to_numpy()

    def sample(regime, n, seed):
        rng = np.random.default_rng(seed)
        c = float(regime.context.get(CTX, 0.0))
        dose = np.full(n, float(regime.config["dose"])) if "dose" in regime.config else rng.choice(dose_pool, n)
        Xq = np.column_stack([dose, np.full(n, c)])
        resid = rng.multivariate_normal([0.0, 0.0], resid_cov, n)
        return pd.DataFrame({"dose": dose, "marker": m_model.predict(Xq) + resid[:, 0],
                             "outcome": o_model.predict(Xq) + resid[:, 1]})

    return sample


# ---- DECISIVE CONTROL: moment-matched Gaussian oracle (best UNIMODAL model) --
def rival_gaussian_oracle(world_sample, n_moment=4000, moment_seed=80001):
    """The strongest no-multimodality competitor: a Gaussian with the EXACT
    per-regime mean and covariance of the truth, but unimodal by construction.
    It fits any mean/variance/heteroscedasticity perfectly. If it STILL fails,
    the residual gap is irreducibly the BIMODALITY -> the value of positing the
    latent, cleanly separated from any mean/variance-fitting capacity (this
    answers the v0.18 weak-rival concern: even an oracle-moment rival fails)."""
    def sample(regime, n, seed):
        rng = np.random.default_rng(seed)
        t = world_sample(regime, n_moment, moment_seed)
        if "dose" in regime.config:
            mu = t[["marker", "outcome"]].mean().to_numpy()
            cov = t[["marker", "outcome"]].cov().to_numpy()
            draw = rng.multivariate_normal(mu, cov, n)
            return pd.DataFrame({"dose": np.full(n, float(regime.config["dose"])),
                                 "marker": draw[:, 0], "outcome": draw[:, 1]})
        mu = t[COLS].mean().to_numpy()
        cov = t[COLS].cov().to_numpy()
        draw = rng.multivariate_normal(mu, cov, n)
        return pd.DataFrame({"dose": np.clip(draw[:, 0], 0, 10), "marker": draw[:, 1], "outcome": draw[:, 2]})

    return sample


# ---- latent-discovering reference: POSITS the latent (should recover R~=1) --
def rival_latent_disc(train):
    """Cluster the biomarker -> 2 subtypes; per-subtype marker law + outcome ~
    dose; mixing weight as logistic of mix_logit. Reproduces the bimodal joint."""
    km = KMeans(2, n_init=10, random_state=0).fit(train[["marker"]].to_numpy())
    lab = km.labels_
    sub = {}
    for k in (0, 1):
        m = train[lab == k]
        o = LinearRegression().fit(m[["dose"]].to_numpy(), m["outcome"].to_numpy())
        sub[k] = {
            "marker_mu": float(m["marker"].mean()), "marker_sd": float(m["marker"].std() + 1e-9),
            "b0": float(o.intercept_), "b1": float(o.coef_[0]),
            "osd": float((m["outcome"].to_numpy() - o.predict(m[["dose"]].to_numpy())).std() + 1e-9),
        }
    # p(subtype=1 | mix_logit) learned from the grid (it knows the context)
    clf = LogisticRegression().fit(train[[CTX]].to_numpy(), lab)
    dose_pool = train["dose"].to_numpy()

    def sample(regime, n, seed):
        rng = np.random.default_rng(seed)
        c = float(regime.context.get(CTX, 0.0))
        p1 = float(clf.predict_proba(np.array([[c]]))[0, 1])
        z = rng.binomial(1, p1, n)
        dose = np.full(n, float(regime.config["dose"])) if "dose" in regime.config else rng.choice(dose_pool, n)
        marker = np.empty(n)
        outcome = np.empty(n)
        for k in (0, 1):
            mask = z == k
            nk = int(mask.sum())
            if nk == 0:
                continue
            s = sub[k]
            marker[mask] = rng.normal(s["marker_mu"], s["marker_sd"], nk)
            outcome[mask] = s["b0"] + s["b1"] * dose[mask] + rng.normal(0.0, s["osd"], nk)
        return pd.DataFrame({"dose": dose, "marker": marker, "outcome": outcome})

    return sample


# ---- null model (for D_MAX + S_null anchor): independent pool marginals -----
def null_model(pool):
    stats = {c: (float(pool[c].mean()), float(pool[c].std())) for c in COLS}

    def sample(regime, n, seed):
        rng = np.random.default_rng(seed)
        out = {}
        for c in COLS:
            mu, sd = stats[c]
            v = rng.normal(mu, sd, n)
            out[c] = np.clip(v, 0, 10) if c == "dose" else v
        return pd.DataFrame(out)

    return sample


def probe_battery():
    """Uniform-weight grid over the control surface -- NOT the derived battery,
    just a probe of where truth and the no-latent rival diverge. Bimodality is
    strongest at mix_logit=0 (p=0.5) and grows with dose (clusters spread)."""
    items = []
    s = 70001
    for dose in (0.0, 2.0, 4.0, 6.0, 8.0):
        for mx in (-1.5, 0.0, 1.5):
            items.append(BatteryItem(weight=1.0, regime=Regime(config={"dose": dose}, context={CTX: mx}), seed_world=s))
            s += 1
    for mx in (-1.0, 0.0, 1.0):  # observational
        items.append(BatteryItem(weight=1.0, regime=Regime(config={}, context={CTX: mx}), seed_world=s))
        s += 1
    return Battery(items=items)


def main():
    params = ScoringParams(lambda_mdl=0.0, n_samples=1000, m_reps=2)
    pool = observational_pool(4000, 50001)
    train = experimental_grid(list(range(0, 11)), [-1.5, -0.75, 0.0, 0.75, 1.5], 400, 60001)

    naive = rival_naive(pool)
    no_latent = rival_no_latent(train)
    oracle = rival_gaussian_oracle(world.sample)
    latent = rival_latent_disc(train)
    null = null_model(pool)

    battery = probe_battery()
    ws = WorldSide(world.sample, battery, COLS, params.n_samples, null_sample=null)

    s_truth = score_callable(world.sample, ws, params)
    s_naive = score_callable(naive, ws, params)
    s_nl = score_callable(no_latent, ws, params)
    s_orac = score_callable(oracle, ws, params)
    s_lat = score_callable(latent, ws, params)
    s_null = score_callable(null, ws, params)
    denom = s_truth - s_naive

    def R(s):
        return (s - s_naive) / denom if denom != 0 else float("nan")

    print("=" * 72)
    print("MENDEL theory-gap probe  (pre-reg ii: theory gap LARGE)")
    print("=" * 72)
    print(f"  S_truth={s_truth:.4f}  S_naive={s_naive:.4f}  S_null={s_null:.4f}  denom={denom:.4f}")
    print(f"  R(naive)             = {R(s_naive):.3f}")
    print(f"  R(no_latent, homosc) = {R(s_nl):.3f}   <- poly means + GLOBAL Gaussian residual")
    print(f"  R(gaussian ORACLE)   = {R(s_orac):.3f}   <- exact per-regime mean+cov, but UNIMODAL (decisive)")
    print(f"  R(latent_disc)       = {R(s_lat):.3f}   <- POSITS the latent (clusters the biomarker)")
    print(f"  R(null)              = {R(s_null):.3f}")
    print("-" * 72)
    theory_gap = R(s_truth) - R(s_nl)
    gap_irreducible = R(s_truth) - R(s_orac)
    print(f"  THEORY GAP (vs homosc no-latent) = {theory_gap:.3f}  (inflated by heteroscedasticity)")
    print(f"  >>> IRREDUCIBLE GAP (vs Gaussian oracle) = {gap_irreducible:.3f}   "
          f"(pre-reg ii: LARGE; dummy ~0)  {'LARGE -> must posit the latent' if gap_irreducible > 0.4 else 'CHECK'}")
    print(f"  latent-recovery: R(latent_disc)={R(s_lat):.3f} "
          f"({'OK -> positing the latent recovers it' if R(s_lat) > 0.7 else 'LOW -> latent rival too weak, investigate'})")
    print("=" * 72)

    # SYMMETRIC per-regime reading (Decision Log v0.19): the DECISIVE question --
    # does the moment-matched ORACLE fail where bimodality is MAXIMAL (dose high,
    # mix~0)? If it succeeds even there, (ii) is fully refuted; if it fails only
    # there, a bimodality-weighted battery could still find a gap.
    from wager.reward.seeds import derive_seed
    print("\nSYMMETRIC READING -- ORACLE (decisive rival) vs truth, per probe item:")
    rows = []
    for idx, it in enumerate(battery.items):
        tside = ws.truth_sides[idx]
        nsr = ns(it.regime.config, it.regime.context)
        d_orac = tside.distance_to(oracle(nsr, params.n_samples, derive_seed(it.seed_world, 0)))
        d_nl = tside.distance_to(no_latent(nsr, params.n_samples, derive_seed(it.seed_world, 0)))
        truth = world.sample(nsr, params.n_samples, it.seed_world)
        rows.append({
            "idx": idx, "dose": it.regime.config.get("dose"), "mix": it.regime.context.get(CTX, 0.0),
            "d_orac": d_orac, "d_nl": d_nl, "dmax": ws.d_maxes[idx],
            "truth_out_sd": float(truth["outcome"].std()),
        })
    # show the maximal-bimodality items explicitly + the worst oracle items
    hi_bimodal = [r for r in rows if r["dose"] in (6.0, 8.0) and abs(r["mix"]) < 0.5]
    print("  -- maximal-bimodality regimes (dose high, mix~0; clusters far apart):")
    for r in hi_bimodal:
        print(f"     dose={r['dose']:.0f} mix={r['mix']:+.1f}  ORACLE dist={r['d_orac']:.3f} "
              f"(of D_MAX {r['dmax']:.3f})  homosc-no_latent dist={r['d_nl']:.3f}  truth_out_sd={r['truth_out_sd']:.2f}")
    print("  -- worst ORACLE items overall:")
    for r in sorted(rows, key=lambda r: -r["d_orac"])[:4]:
        dd = "obs" if r["dose"] is None else f"{r['dose']:.0f}"
        print(f"     item {r['idx']:>2} dose={dd:>3} mix={r['mix']:+.1f}  ORACLE dist={r['d_orac']:.3f} "
              f"(of D_MAX {r['dmax']:.3f})  truth_out_sd={r['truth_out_sd']:.2f}")
    print("\n  Read: if the ORACLE's distance is small even at dose=8/mix=0 (maximal")
    print("  bimodality), energy distance barely sees multimodality at matched moments")
    print("  -> latent heterogeneity is NOT rewarded by marginal energy distance (the finding).")

    # SALVAGE CHECK (not a reward-path change; a diagnostic): does a DECISION
    # FUNCTIONAL expose the gap energy distance misses? P(harm) = P(outcome <
    # harm_threshold). A convex/threshold stakes loss is decision-relevant and
    # DIFFERS between the bimodal truth and the moment-matched unimodal oracle.
    print("\nSALVAGE -- decision functional P(outcome < harm_thr) truth vs ORACLE (the gap energy distance misses):")
    for thr in (-5.0,):
        for dose in (4.0, 6.0, 8.0):
            nsr = ns({"dose": dose}, {CTX: 0.0})
            t = world.sample(nsr, 20000, 90100)
            o = oracle(nsr, 20000, 90200)
            pt = float((t["outcome"] < thr).mean())
            po = float((o["outcome"] < thr).mean())
            print(f"  do(dose={dose:.0f}, mix=0)  P(harm)<{thr:.0f}:  truth={pt:.3f}  oracle={po:.3f}  "
                  f"|gap|={abs(pt - po):.3f}")
    print("  -> the latent IS decision-relevant; it is invisible to RAW marginal energy distance but")
    print("     visible to a stakes FUNCTIONAL. Design question for Lucas (Decision Log v0.25 RESULTADOS).")


if __name__ == "__main__":
    main()
