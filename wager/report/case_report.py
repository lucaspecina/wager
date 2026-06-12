"""Assemble a single human-readable HTML report for a case + an episode trace.

Run:
  python -m wager.report.case_report <case_dir> [trace.json] [-o out.html]

End-to-end view for a human auditor: the world and its hidden trap (answer key),
the brief the agent sees, the secret battery, the agent's full trajectory, and
how the grade was computed item by item (re-scored live, deterministic).
"""

import argparse
import json
from pathlib import Path

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


def sec_battery(case_dir, meta) -> str:
    bat = load_battery(case_dir)
    items = sorted(bat.items, key=lambda it: -it.weight)
    rows = [[f"{it.weight:.3f}", _dose(it.regime),
             f"{it.regime.context.get('cohort', 0.0):+.2f}"] for it in items]
    note = ("<p class='note'>The secret exam: weighted held-out scenarios the submission is graded on. "
            "Weight concentrates where understanding the trap changes the prediction. The agent never sees it.</p>")
    return section(f"The secret exam (battery, {len(items)} items)",
                   note + table(["weight", "dose", "cohort"], rows, num_cols={0, 2}))


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
    body += (f"<b>signal (v0.1)</b><span>attribution-before-experiment="
             f"{sig.get('attribution_before_experiment')} "
             f"(1st analysis turn {sig.get('first_attribution_turn')}, "
             f"1st experiment turn {sig.get('first_experiment_turn')})</span>")
    body += "</div>"

    for t in trace.get("trace", []):
        plan = (t.get("reply_text", "") or "").strip().split("\n", 1)[0][:140]
        cr = t.get("cell_result", {})
        card = f"<div class='turn'><h3>Turn {t.get('turn')}</h3>"
        card += f"<p><b>Plan:</b> {esc(plan)}</p>"
        card += details("Show full model reply (reasoning)", md("```\n" + (t.get("reply_text") or "") + "\n```"))
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


def sec_evaluation(case_dir, meta, trace) -> str:
    code_str = (trace or {}).get("submission_code")
    if not code_str:
        return section("The evaluation", "<p class='note'>No submission to score.</p>", "eval")
    from wager.reward.scorer import WorldSide, make_anchors, sandboxed_null_sample, score_submission

    bat = load_battery(case_dir)
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
def build_report(case_dir: str | Path, trace_path: str | Path | None) -> str:
    case_dir = Path(case_dir)
    meta = load_meta(case_dir)
    trace = json.loads(Path(trace_path).read_text(encoding="utf-8")) if trace_path else None
    head = f"<h1>WAGER case report &mdash; {esc(meta.case_id)}</h1>"
    head += "<p class='sub'>End-to-end human inspection: answer key &middot; agent view &middot; trajectory &middot; grading.</p>"
    body = (head + sec_overview(meta, trace) + sec_brief(case_dir) + sec_truth(case_dir, meta)
            + sec_battery(case_dir, meta) + sec_episode(trace) + sec_evaluation(case_dir, meta, trace))
    return page(f"WAGER {meta.case_id}", body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case_dir")
    ap.add_argument("trace", nargs="?", default=None)
    ap.add_argument("-o", "--out", default=None)
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
    html = build_report(case_dir, trace)
    out = Path(args.out) if args.out else Path("reports") / f"{case_dir.name}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"report -> {out.resolve()}")


if __name__ == "__main__":
    main()
