"""Tiny dependency-light HTML helpers for the case report (lab-notebook style)."""

import html as _html

import markdown as _md

CSS = """
:root { --fg:#1a1a1a; --muted:#666; --line:#e3e3e3; --bg:#fff;
        --truth:#fff7ed; --truth-bd:#fdba74; --student:#eff6ff; --student-bd:#93c5fd;
        --eval:#f0fdf4; --eval-bd:#86efac; --code:#f6f8fa; --warn:#fef2f2; --warn-bd:#fca5a5; }
* { box-sizing:border-box; }
body { font:15px/1.55 -apple-system,Segoe UI,Roboto,sans-serif; color:var(--fg);
       max-width:1000px; margin:0 auto; padding:24px; background:var(--bg); }
h1 { font-size:26px; margin:0 0 4px; }
h2 { font-size:20px; margin:32px 0 8px; padding-bottom:6px; border-bottom:2px solid var(--line); }
h3 { font-size:16px; margin:18px 0 6px; }
.sub { color:var(--muted); margin:0 0 18px; }
section { border:1px solid var(--line); border-radius:10px; padding:4px 18px 16px; margin:18px 0; }
section.truth { background:var(--truth); border-color:var(--truth-bd); }
section.student { background:var(--student); border-color:var(--student-bd); }
section.eval { background:var(--eval); border-color:var(--eval-bd); }
.tag { display:inline-block; font-size:11px; font-weight:700; text-transform:uppercase;
       letter-spacing:.04em; padding:2px 8px; border-radius:99px; color:#fff; vertical-align:middle; }
.tag.truth { background:#ea580c; } .tag.student { background:#2563eb; } .tag.eval { background:#16a34a; }
pre.code { background:var(--code); border:1px solid var(--line); border-radius:8px;
           padding:12px; overflow-x:auto; font:12.5px/1.4 SFMono-Regular,Consolas,monospace; }
pre.out { background:#1f2937; color:#e5e7eb; border-radius:8px; padding:12px; overflow-x:auto;
          font:12.5px/1.4 SFMono-Regular,Consolas,monospace; white-space:pre-wrap; }
code { background:var(--code); padding:1px 5px; border-radius:4px; font-family:Consolas,monospace; font-size:90%; }
table { border-collapse:collapse; width:100%; margin:10px 0; font-size:13.5px; }
th,td { border:1px solid var(--line); padding:6px 10px; text-align:left; }
th { background:#fafafa; } tr:nth-child(even) td { background:#fcfcfc; }
.num { text-align:right; font-variant-numeric:tabular-nums; }
details { margin:8px 0; } summary { cursor:pointer; color:#2563eb; font-weight:600; }
.turn { border:1px solid var(--line); border-radius:8px; padding:2px 14px 12px; margin:14px 0; background:#fff; }
.turn h3 { color:#374151; }
.kv { display:grid; grid-template-columns:max-content 1fr; gap:2px 14px; margin:8px 0; }
.kv b { color:var(--muted); font-weight:600; }
.warn { background:var(--warn); border:1px solid var(--warn-bd); border-radius:6px; padding:8px 12px; margin:8px 0; }
.ok { color:#16a34a; font-weight:700; } .bad { color:#dc2626; font-weight:700; }
.note { color:var(--muted); font-size:13.5px; font-style:italic; margin:6px 0; }
"""


def esc(s) -> str:
    return _html.escape(str(s))


def page(title: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{esc(title)}</title>"
            f"<style>{CSS}</style></head><body>{body}</body></html>")


def md(text: str, demote: int = 0) -> str:
    out = _md.markdown(text or "", extensions=["tables", "fenced_code"])
    for level in range(6, 0, -1):  # demote headers so they nest under section <h2>
        tgt = min(level + demote, 6)
        out = out.replace(f"<h{level}>", f"<h{tgt}>").replace(f"</h{level}>", f"</h{tgt}>")
    return out


def code(src: str, out: bool = False) -> str:
    cls = "out" if out else "code"
    return f"<pre class='{cls}'>{esc(src)}</pre>"


def details(summary: str, inner: str, open_: bool = False) -> str:
    o = " open" if open_ else ""
    return f"<details{o}><summary>{esc(summary)}</summary>{inner}</details>"


def table(headers: list[str], rows: list[list], num_cols: set[int] | None = None) -> str:
    num_cols = num_cols or set()
    head = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = ""
    for r in rows:
        cells = "".join(
            f"<td class='num'>{esc(c)}</td>" if i in num_cols else f"<td>{esc(c)}</td>"
            for i, c in enumerate(r)
        )
        body += f"<tr>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def section(title: str, body: str, kind: str = "") -> str:
    tag = f"<span class='tag {kind}'>{ {'truth':'answer key','student':'agent view','eval':'grading'}.get(kind,'') }</span>" if kind else ""
    return f"<section class='{kind}'><h2>{esc(title)} {tag}</h2>{body}</section>"
