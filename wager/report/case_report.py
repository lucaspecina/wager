"""Assemble a single human-readable HTML report for a case + an episode trace.

Run:
  python -m wager.report.case_report <case_dir> [trace.json] [-o out.html]

End-to-end view for a human auditor: the world and its hidden trap (answer key),
the brief the agent sees, the secret battery, the agent's full trajectory, and
how the grade was computed item by item (re-scored live, deterministic).
"""

import argparse
import json
import re
from pathlib import Path

_FENCE = re.compile(r"```(?:python|py)?\s*\n.*?```", re.DOTALL)


def _reasoning(reply: str) -> str:
    """The agent's prose reasoning = the reply with the code cell removed."""
    return _FENCE.sub("", reply or "").strip()

from wager.factory.case_loader import (
    load_battery, load_ladder, load_meta, load_world_module, load_world_sample, load_world_source,
)
from wager.report.html import code, details, esc, md, page, section, table


def _dose(regime) -> str:
    cfg = regime.config if hasattr(regime, "config") else regime.get("config", {})
    return "observational" if "dose" not in cfg else f"{cfg['dose']:.2f} mg"


# ---- sections -------------------------------------------------------------
def sec_overview(meta, trace) -> str:
    body = f"<p class='sub'>Suite: <b>{esc(meta.suite)}</b> &middot; observables: "
    body += ", ".join(f"<code>{esc(c.name)}</code>" for c in meta.columns) + "</p>"
    if trace:
        r = trace.get("R")
        body += "<div class='kv'>"
        body += f"<b>episode model</b><span>{esc(trace.get('model'))}</span>"
        body += f"<b>final grade R</b><span>{'%.3f' % r if r is not None else '-'} "
        body += f"(unclipped {trace.get('R_unclipped', float('nan')):+.3f})</span>"
        body += f"<b>turns</b><span>{trace.get('turns')}</span>"
        tok = trace.get("tokens", {})
        body += f"<b>cost</b><span>{tok.get('total','-')} tokens, {trace.get('wall_seconds','-')}s</span>"
        body += "</div>"
    return section("Case overview", body)


def sec_brief(case_dir) -> str:
    brief = (Path(case_dir) / "brief.md").read_text(encoding="utf-8")
    note = "<p class='note'>This is ALL the agent sees: the public face. The trap below is hidden from it.</p>"
    return section("The brief (what the agent sees)", note + md(brief, demote=2), "student")


def sec_truth(case_dir, meta) -> str:
    wmod = load_world_module(case_dir)
    body = "<p class='note'>The answer key: the real mechanism, the planted traps, the truth the "
    body += "scorer compares against. The agent never sees any of this.</p>"
    if wmod.__doc__:
        body += "<h3>How the world really works</h3>" + md(wmod.__doc__)
    if meta.operators:
        rows = [[o.name, o.layer, json.dumps(o.knobs), json.dumps(o.ablation)] for o in meta.operators]
        body += "<h3>Planted traps (operators)</h3>" + table(
            ["operator", "layer", "knobs", "ablation (off-switch)"], rows)
    if meta.episode and meta.episode.control_surface:
        body += "<h3>Control surface (what an experiment can set)</h3>"
        body += code(json.dumps(meta.episode.control_surface, indent=2))
    src = load_world_source(case_dir)
    body += details("Show world.py source", code(src))
    return section("The hidden truth", body, "truth")


def sec_certificates(case_dir) -> str:
    cpath = Path(case_dir) / "certificates.json"
    if not cpath.exists():
        return ""
    c = json.loads(cpath.read_text(encoding="utf-8"))
    body = "<p class='note'>Computable certificates (factory side, never seen by the agent): do the worlds " \
           "actually exert the pressures we claim? Each is in R units (fraction of the truth&ndash;naive range).</p>"
    def _acc(key):  # self-describing rival access (Decision Log v0.30)
        a = c.get(key)
        if not a:
            return "&mdash;"
        tag = "standardized" if a.get("standardized") else "PROTO"
        g = f"; {a['grid']}" if a.get("grid") else ""
        return f"{a['mode']}, n={a['n_rows']}, seed0={a['seed0']} ({tag}{g})"

    rows = [
        ["mechanistic gap", f"{c.get('mechanistic_gap', float('nan')):.3f}", _acc("mechanistic_access"),
         "truth minus the best model fit to OBSERVATIONAL data only -> you must EXPERIMENT to win (curve-fitting loses)"],
        ["theory gap", f"{c.get('theory_gap', float('nan')):.3f}", _acc("theory_access"),
         "truth minus the best model using only observable columns (no invented latent), access equalized to the agent -> pressure to INVENT hidden constructs"],
    ]
    if "prior_gap" in c:
        rows.append(["prior gap", f"{c['prior_gap']:.3f}", "&mdash;",
                     "truth minus the fresh-LLM prior-evoked model (contamination detector, in refinement)"])
    body += table(["certificate", "value (R units)", "rival access", "what it means"], rows, num_cols={1})
    body += (f"<p class='note'>discrimination scale (S_truth&minus;S_naive raw) = "
             f"{c.get('denom_raw', float('nan')):.4f}; the reward noise (CV) is ~1% of R, well below this, "
             f"so the exam genuinely separates good answers from bad.</p>")
    return section("Certificates (does this world exert the pressures?)", body, "truth")


def _coverage_map(bat) -> str:
    total = sum(it.weight for it in bat.items) or 1.0
    bands: dict[str, list] = {}
    for it in bat.items:
        if "dose" not in it.regime.config:
            key = "observational"
        else:
            d = it.regime.config["dose"]
            lo = int(min(d, 9.999) // 2.5) * 2.5
            key = f"dose [{lo:.1f}, {lo + 2.5:.1f})"
        b = bands.setdefault(key, [0, 0.0])
        b[0] += 1
        b[1] += it.weight
    rows = [[k, bands[k][0], f"{bands[k][1] / total:.0%}"] for k in sorted(bands)]
    oor = sum(it.weight for it in bat.items if it.regime.config.get("dose", 0) >= 6.0) / total
    deep = sum(it.weight for it in bat.items if it.regime.config.get("dose", 0) >= 8.0) / total
    t = table(["region", "items", "% of weight"], rows, num_cols={1, 2})
    t += (f"<p class='note'>out-of-record (dose &ge; 6): <b>{oor:.0%}</b> of weight &middot; "
          f"deep / saturation (dose &ge; 8): <b>{deep:.0%}</b>. Audit the COVERAGE, not only the top-N "
          f"(the top-N cutoff is arbitrary).</p>")
    return t


def _promises_checklist(meta, bat) -> str:
    """Deterministic brief-promises checklist (Decision Log v0.24): every declared
    stakes claim is ticked against the coverage. The human cross-checks against
    the brief narrative (shown) to catch UNDECLARED promises -- the failure mode
    that let 'populations outside the record' slip through."""
    total = sum(it.weight for it in bat.items) or 1.0

    def wfrac(pred):
        return sum(it.weight for it in bat.items if pred(it)) / total

    checks = []
    st = meta.stakes
    for v in st.decision_variables:
        f = wfrac(lambda it, v=v: v in it.regime.config)
        checks.append((f"the decision sets <code>{esc(v)}</code>", f > 0.05, f"{f:.0%} weight"))
    for var, spec in st.decision_relevance.items():
        thr = spec.get("out_of_record_above")
        if thr is not None:
            f = wfrac(lambda it, var=var, thr=thr: it.regime.config.get(var, -1e9) >= thr)
            checks.append((f"<code>{esc(var)}</code> outside the historical record (&ge; {thr})", f > 0.05, f"{f:.0%} weight"))
    for var, spec in st.context_relevance.items():
        thr = spec.get("out_of_record_above_abs")
        if thr is not None:
            f = wfrac(lambda it, var=var, thr=thr: abs(it.regime.context.get(var, 0.0)) >= thr)
            checks.append((f"populations with |<code>{esc(var)}</code>| &ge; {thr} (outside the record)", f > 0.05, f"{f:.0%} weight"))
    rows = ""
    for claim, ok, detail in checks:
        mark = "<span class='ok'>&#10003;</span>" if ok else "<span class='bad'>&#10007;</span>"
        rows += f"<tr><td>{mark}</td><td>{claim}</td><td>{esc(detail)}</td></tr>"
    tbl = (f"<table><thead><tr><th></th><th>declared stakes promise</th><th>coverage</th></tr></thead>"
           f"<tbody>{rows}</tbody></table>")
    note = (f"<p class='note'>Cross-check these DECLARED promises against the brief narrative below "
            f"(an undeclared promise will not appear here &mdash; that is the gap to look for):</p>"
            f"<blockquote class='note'>{esc(meta.stakes.narrative)}</blockquote>")
    return note + tbl


def sec_battery(bat, meta) -> str:
    items = sorted(bat.items, key=lambda it: -it.weight)
    rows = [[i + 1, f"{it.weight:.3f}", _dose(it.regime),
             f"{it.regime.context.get('cohort', 0.0):+.2f}"] for i, it in enumerate(items)]
    note = ("<p class='note'>The secret exam: weighted held-out scenarios the submission is graded on. "
            "Weight concentrates where understanding the trap changes the prediction. The agent never sees it.</p>")
    body = note + "<h3>Brief-promises checklist (start the audit here)</h3>" + _promises_checklist(meta, bat)
    body += "<h3>Coverage map (the right audit lens)</h3>" + _coverage_map(bat)
    body += "<h3>All items (by weight)</h3>" + table(["#", "weight", "dose", "cohort"], rows, num_cols={0, 1, 3})
    return section(f"The secret exam (battery, {len(items)} items)", body)


def _verbs_table(verbs) -> str:
    rows = []
    for v in verbs:
        a = v.get("args", {})
        if v["verb"] == "observe":
            arg = f"source={a.get('source')}, n={a.get('n')}"
        elif v["verb"] == "experiment":
            arg = f"config={a.get('config')}, context={a.get('context')}, n={a.get('n')}"
        else:
            arg = json.dumps(a)
        rows.append([v["verb"], arg, f"{v.get('cost', 0):.0f}",
                     f"{v.get('budget_remaining', 0):.0f}", v.get("note", "")])
    return table(["verb", "args", "cost", "budget left", "note"], rows, num_cols={2, 3})


def sec_episode(trace) -> str:
    if not trace:
        return section("The episode", "<p class='note'>No trace provided.</p>", "student")
    sig = trace.get("signal", {})
    body = "<div class='kv'>"
    body += f"<b>accepted</b><span>{trace.get('accepted')} (ended: {trace.get('abort_reason')})</span>"
    body += f"<b>budget</b><span>spent {trace.get('budget_spent','-')} / {trace.get('budget_total','-')}</span>"
    body += "</div>"
    # behavioral signature (observed, never rewarded): did the agent do attribution
    # analysis BEFORE paying for the first experiment? -- hypothesis-before-spend.
    abe = sig.get("attribution_before_experiment")
    badge = "<span class='ok'>yes</span>" if abe else ("<span class='bad'>no</span>" if abe is False else "&mdash;")
    body += (f"<div class='warn'><b>Behavioral signature (v0.1):</b> attribution analysis before the first "
             f"paid experiment = {badge} &mdash; first analysis at turn {sig.get('first_attribution_turn')}, "
             f"first experiment at turn {sig.get('first_experiment_turn')}. "
             f"<span class='note'>Observed, never rewarded (the reward is only on the submission).</span></div>")

    for t in trace.get("trace", []):
        reasoning = _reasoning(t.get("reply_text", ""))
        cr = t.get("cell_result", {})
        card = f"<div class='turn'><h3>Turn {t.get('turn')}</h3>"
        if reasoning:
            card += "<p><b>Reasoning (the agent thinking about the evidence):</b></p>" + md(reasoning, demote=2)
        else:
            card += "<p class='note'>(no prose reasoning in this reply)</p>"
        if t.get("cell"):
            card += "<p><b>Code the agent ran:</b></p>" + code(t["cell"])
        out = cr.get("stdout") or "(no output)"
        if cr.get("truncated"):
            out += "\n[output truncated in trace]"
        card += "<p><b>Kernel output it saw:</b></p>" + code(out, out=True)
        if cr.get("error"):
            card += "<div class='warn'><b>cell error:</b><br>" + esc(cr["error"]) + "</div>"
        if t.get("verbs"):
            card += "<p><b>Actions (verbs) this turn:</b></p>" + _verbs_table(t["verbs"])
        for s in t.get("submit_attempts", []):
            ok = s["args"].get("accepted")
            cls = "ok" if ok else "bad"
            card += (f"<div class='warn'><span class='{cls}'>submit "
                     f"{'ACCEPTED' if ok else 'REJECTED'}</span> &mdash; {esc(s.get('note',''))}</div>")
        tok = t.get("tokens", {})
        card += f"<p class='note'>tokens: prompt {tok.get('prompt')}, completion {tok.get('completion')}</p>"
        card += "</div>"
        body += card

    if trace.get("submission_code"):
        body += details("Show the final submitted model program", code(trace["submission_code"]))
    return section("The episode (agent's full trajectory)", body, "student")


def sec_evaluation(case_dir, meta, trace, bat) -> str:
    code_str = (trace or {}).get("submission_code")
    if not code_str:
        return section("The evaluation", "<p class='note'>No submission to score.</p>", "eval")
    from wager.reward.scorer import WorldSide, make_anchors, sandboxed_null_sample, score_submission

    ladder = dict(load_ladder(case_dir))
    ws_fn = load_world_sample(case_dir)
    cols, params = meta.column_names, meta.scoring
    with sandboxed_null_sample(ladder["rung_6_null"], cols, params.model_call_timeout_s) as null_sample:
        ws = WorldSide(ws_fn, bat, cols, params.n_samples, null_sample=null_sample)
        s_truth = score_submission(load_world_source(case_dir), ws, params).raw_score
        s_naive = score_submission(ladder["rung_5_naive_fit"], ws, params).raw_score
        s_null = score_submission(ladder["rung_6_null"], ws, params).raw_score
        rep = score_submission(code_str, ws, params)
    anchors = make_anchors(s_truth, s_naive, s_null)
    r, r_uncl = anchors.r_of(rep.raw_score)

    body = ("<p class='note'>The grade is how closely the submitted model reproduces the real world across the "
            "secret exam. R=1 means as good as the truth itself; R=0 means no better than naively believing the "
            "raw (trap-laden) data; below 0 is worse than that (clipped to 0). NO LLM touches this number.</p>")
    body += "<div class='kv'>"
    body += f"<b>final R</b><span><b>{r:.3f}</b> (unclipped {r_uncl:+.3f})</span>"
    body += f"<b>anchors</b><span>truth={s_truth:+.4f} (R=1) &middot; naive={s_naive:+.4f} (R=0) &middot; null={s_null:+.4f}</span>"
    body += "</div>"
    rows = []
    for it, bi in zip(rep.items, bat.items):
        rows.append([_dose(bi.regime), f"{bi.regime.context.get('cohort',0.0):+.2f}",
                     f"{it.weight:.3f}", f"{it.mean_distance:.4f}", f"{it.d_max:.3f}",
                     "yes" if it.sandbox_errors else "", f"{it.weight*it.mean_distance:.4f}"])
    body += "<h3>Per-item grading (lower distance = closer to the truth)</h3>"
    body += table(["dose", "cohort", "weight", "distance", "max (cap)", "crashed", "contribution"],
                  rows, num_cols={2, 3, 4, 6})
    return section("The evaluation (how the grade was computed)", body, "eval")


# ---- assembly -------------------------------------------------------------
def build_report(case_dir: str | Path, trace_path: str | Path | None,
                 battery_file: str | Path | None = None) -> str:
    from wager.contracts import Battery

    case_dir = Path(case_dir)
    meta = load_meta(case_dir)
    bat = Battery.from_json_file(battery_file) if battery_file else load_battery(case_dir)
    bat_label = Path(battery_file).name if battery_file else "battery.json (bootstrap)"
    trace = json.loads(Path(trace_path).read_text(encoding="utf-8")) if trace_path else None
    head = f"<h1>WAGER case report &mdash; {esc(meta.case_id)}</h1>"
    head += "<p class='sub'>End-to-end human inspection: answer key &middot; agent view &middot; trajectory &middot; grading."
    head += f" &middot; battery: <b>{esc(bat_label)}</b></p>"
    body = (head + sec_overview(meta, trace) + sec_brief(case_dir) + sec_truth(case_dir, meta)
            + sec_certificates(case_dir) + sec_battery(bat, meta) + sec_episode(trace)
            + sec_evaluation(case_dir, meta, trace, bat))
    return page(f"WAGER {meta.case_id}", body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("trace", nargs="?", default=None)
    ap.add_argument("-o", "--out", default=None)
    ap.add_argument("-b", "--battery", default=None, help="battery file to show (default: case battery.json)")
    args = ap.parse_args()
    case_dir = Path(args.case_dir)
    trace = args.trace
    if trace and not Path(trace).exists():
        trace = case_dir / "traces" / trace
    if trace is None:  # auto-pick a trace that has a submission to grade
        for cand in sorted((case_dir / "traces").glob("*.json"), reverse=True):
            try:
                if json.loads(cand.read_text(encoding="utf-8")).get("submission_code"):
                    trace = cand
                    break
            except Exception:  # noqa: BLE001
                continue
        if trace:
            print(f"(no trace given; using {Path(trace).name})")
    bfile = args.battery
    if bfile and not Path(bfile).exists():
        bfile = case_dir / bfile
    html = build_report(case_dir, trace, battery_file=bfile)
    out = Path(args.out) if args.out else Path("reports") / f"{case_dir.name}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"report -> {out.resolve()}")


if __name__ == "__main__":
    main()
