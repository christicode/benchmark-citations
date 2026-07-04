#!/usr/bin/env python3
"""Generate the static trends dashboard (docs/index.html) for GitHub Pages.

Reads data/citations.jsonl and surfaces, per the project brief:
  - Top Harbor-conversion candidates (prominence-weighted usage x saturation headroom),
    excluding benchmarks already in Harbor, with a one-line "why now".
  - Rising CITATION USAGE (velocity: recent period vs prior).
  - Rising SATURATION (avg reported solve rate climbing toward ceiling).
  - Agentic vs static axis kept as a SEPARATE surfaced signal (not folded into score).
Regenerate whenever data changes. No external deps.
"""
from __future__ import annotations
import json, pathlib, collections, datetime, html

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPLIT = "2026-01-01"   # recent (>=) vs prior (<) period boundary for velocity/saturation trend
TABLE_NORM = 12.0      # deep table rows (row 47 of 50) decay; a blog headline stays 3.0


def pweight(p):
    t = p.get("type")
    if t == "headline":
        return 3.0
    if t in ("footnote", "prose"):
        return 0.5
    return min(1.0, TABLE_NORM / max(p.get("table_total") or 1, 1))


def load():
    rows = []
    for line in open(ROOT / "data" / "citations.jsonl"):
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def qkey(d):
    if not d:
        return None
    y, m = int(d[:4]), int(d[5:7])
    return f"{y}Q{(m - 1)//3 + 1}"


def main():
    rows = load()
    agg = collections.defaultdict(lambda: {"usage": 0.0, "labs": set(), "docs": set(),
        "solve": [], "axis": "?", "status": "not_in_harbor", "on": False,
        "recent": 0, "prior": 0, "solve_recent": [], "solve_prior": [], "q": collections.Counter()})
    for c in rows:
        canon = c["benchmark_canonical"]
        if not canon:
            continue
        a = agg[canon]
        a["usage"] += pweight(c["prominence"])
        a["labs"].add(c["citing_lab"]); a["docs"].add(c["source_doc"]["url"])
        a["axis"] = c.get("axis", "?"); a["status"] = c.get("harbor_status", "not_in_harbor")
        a["on"] = a["on"] or c.get("on_harbor", False)
        d = c["source_doc"].get("pub_date")
        recent = bool(d and d >= SPLIT)
        a["recent" if recent else "prior"] += 1
        if d:
            a["q"][qkey(d)] += 1
        rep = c.get("reported") or {}
        if rep.get("unit") == "percent" and isinstance(rep.get("value"), (int, float)):
            v = rep["value"] / 100.0
            a["solve"].append(v)
            (a["solve_recent"] if recent else a["solve_prior"]).append(v)

    # ---- conversion candidates (exclude Harbor) ----
    cand = []
    for canon, a in agg.items():
        if a["on"]:
            continue
        diversity = 1 + 0.5 * (len(a["labs"]) - 1)
        usage = a["usage"] * diversity
        headroom = (1 - max(a["solve"])) if a["solve"] else 0.5
        penalty = 0.6 if a["status"] in ("needs_review", "false_positive") else 1.0
        priority = (usage * 0.6 + headroom * 4 * 0.4) * penalty
        cand.append((priority, canon, a, usage, headroom))
    cand.sort(reverse=True)

    # ---- rising usage (velocity) ----
    rising_use = []
    for canon, a in agg.items():
        vel = a["recent"] - a["prior"]
        if a["recent"] >= 2 and vel > 0:
            rising_use.append((vel, a["recent"], a["prior"], canon, a))
    rising_use.sort(reverse=True)

    # ---- rising saturation ----
    rising_sat = []
    for canon, a in agg.items():
        if len(a["solve_recent"]) >= 2 and a["solve_prior"]:
            rr = sum(a["solve_recent"]) / len(a["solve_recent"])
            rp = sum(a["solve_prior"]) / len(a["solve_prior"])
            if rr - rp > 0.02:
                rising_sat.append((rr - rp, rr, rp, canon, a))
    rising_sat.sort(reverse=True)

    axis_counts = collections.Counter(a["axis"] for a in agg.values())
    review = collections.Counter(c.get("review_reason") for c in rows if c.get("needs_review"))
    ndocs = len({c["source_doc"]["url"] for c in rows})

    def why(canon, a, usage, headroom):
        bits = [f"{len(a['docs'])} docs / {len(a['labs'])} labs"]
        if a["solve"]:
            bits.append(f"max solve {max(a['solve'])*100:.0f}% (headroom {headroom:.2f})")
        else:
            bits.append("no solved-rate yet (assume long half-life)")
        if a["recent"] > a["prior"]:
            bits.append("usage rising")
        if a["status"] in ("needs_review", "false_positive"):
            bits.append(f"Harbor status: {a['status']}")
        return "; ".join(bits)

    e = html.escape
    T = []
    T.append("<!doctype html><html lang=en><head><meta charset=utf-8>")
    T.append("<meta name=viewport content='width=device-width,initial-scale=1'>")
    T.append("<title>Benchmark Citations - Trends & Harbor Candidates</title>")
    T.append("""<style>
    :root{--bg:#0d1117;--card:#161b22;--b:#30363d;--fg:#e6edf3;--mut:#8b949e;--ac:#58a6ff;--ag:#3fb950;--sa:#d29922}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
    .wrap{max-width:1120px;margin:0 auto;padding:24px}
    h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:26px 0 10px;border-bottom:1px solid var(--b);padding-bottom:6px}
    .sub{color:var(--mut);margin:0 0 18px}
    .cards{display:flex;flex-wrap:wrap;gap:10px;margin:12px 0}
    .kpi{background:var(--card);border:1px solid var(--b);border-radius:8px;padding:10px 14px;min-width:120px}
    .kpi b{font-size:20px;display:block}
    table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--b);border-radius:8px;overflow:hidden}
    th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--b);vertical-align:top}
    th{color:var(--mut);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em}
    tr:last-child td{border-bottom:0}
    code{background:#010409;padding:1px 5px;border-radius:4px;color:var(--ac)}
    .ag{color:var(--ag)}.st{color:var(--ac)}.sa{color:var(--sa)}.mut{color:var(--mut)}
    .pill{font-size:11px;padding:1px 7px;border-radius:10px;border:1px solid var(--b);color:var(--mut)}
    .why{color:var(--mut);font-size:13px}
    a{color:var(--ac)}
    </style></head><body><div class=wrap>""")
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    T.append(f"<h1>Benchmark Citations - Trends &amp; Harbor Conversion Candidates</h1>")
    T.append(f"<p class=sub>Topline entity = the <b>benchmark</b>. Generated {now} from "
             f"<code>data/citations.jsonl</code>. Harbor status is a live-cross-referenced flag; "
             f"axis (agentic/static/multimodal/safety) is surfaced separately, never folded into the score.</p>")
    T.append("<div class=cards>")
    for label, val in [("citations", len(rows)), ("benchmarks", len(agg)), ("source docs", ndocs),
                       ("not in Harbor", sum(1 for _,a in agg.items() if not a['on'])),
                       ("needs review", sum(1 for c in rows if c.get('needs_review'))),
                       ("scores read", sum(1 for c in rows if (c.get('reported') or {}).get('value') is not None))]:
        T.append(f"<div class=kpi><b>{val}</b>{label}</div>")
    T.append("</div>")

    # candidates
    T.append("<h2>Top Harbor-conversion candidates &mdash; &ldquo;why now&rdquo;</h2>")
    T.append("<table><tr><th>#</th><th>Benchmark</th><th>Axis</th><th>Priority</th>"
             "<th>Usage</th><th>Headroom</th><th>Why now</th></tr>")
    for i, (pr, canon, a, usage, headroom) in enumerate(cand[:20], 1):
        ax = a["axis"]
        cls = {"agentic":"ag","static":"st","safety":"sa","multimodal":"sa"}.get(ax, "mut")
        T.append(f"<tr><td>{i}</td><td><code>{e(canon)}</code></td>"
                 f"<td><span class='pill {cls}'>{e(ax)}</span></td><td>{pr:.2f}</td>"
                 f"<td>{usage:.1f}</td><td>{headroom:.2f}</td><td class=why>{e(why(canon,a,usage,headroom))}</td></tr>")
    T.append("</table>")

    # rising usage
    T.append("<h2>Rising citation usage <span class=mut>(velocity: docs since 2026-01 vs before)</span></h2>")
    if rising_use:
        T.append("<table><tr><th>Benchmark</th><th>Axis</th><th>&Delta;</th><th>recent</th><th>prior</th><th>by quarter</th></tr>")
        for vel, rec, pri, canon, a in rising_use[:18]:
            qs = " ".join(f"{k}:{v}" for k, v in sorted(a["q"].items()))
            T.append(f"<tr><td><code>{e(canon)}</code></td><td class=mut>{e(a['axis'])}</td>"
                     f"<td class=ag>+{vel}</td><td>{rec}</td><td>{pri}</td><td class=mut>{e(qs)}</td></tr>")
        T.append("</table>")
    else:
        T.append("<p class=mut>No benchmark meets the rising-usage threshold yet.</p>")

    # rising saturation
    T.append("<h2>Rising saturation <span class=mut>(avg reported solve rate climbing toward ceiling)</span></h2>")
    if rising_sat:
        T.append("<table><tr><th>Benchmark</th><th>Axis</th><th>&Delta; avg</th><th>recent avg</th><th>prior avg</th></tr>")
        for dv, rr, rp, canon, a in rising_sat[:18]:
            T.append(f"<tr><td><code>{e(canon)}</code></td><td class=mut>{e(a['axis'])}</td>"
                     f"<td class=sa>+{dv*100:.1f}pp</td><td>{rr*100:.1f}%</td><td>{rp*100:.1f}%</td></tr>")
        T.append("</table>")
    else:
        T.append("<p class=mut>Not enough period-over-period scored data to compute saturation trend yet.</p>")

    # axis + review
    T.append("<h2>Signals surfaced separately</h2>")
    T.append("<p><b>Agentic vs static (vs multimodal/safety)</b> &mdash; kept as a distinct axis for human weighting:<br>")
    T.append(" &nbsp; ".join(f"<span class=pill>{e(k)}: {v}</span>" for k, v in axis_counts.most_common()) + "</p>")
    T.append("<p><b>Human review queue</b> (needs_review reasons):</p><table><tr><th>reason</th><th>citations</th></tr>")
    for reason, n in review.most_common():
        T.append(f"<tr><td>{e(str(reason))}</td><td>{n}</td></tr>")
    T.append("</table>")
    T.append("<p class=sub style='margin-top:26px'>Source of truth: git (<code>data/citations.jsonl</code>) + GitHub Issues "
             "(<code>needs-human-review</code>). Harbor registry cross-referenced live from "
             "<code>harbor-framework/harbor</code> main.</p>")
    T.append("</div></body></html>")
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(T))
    print("wrote", out, "|", len(rows), "citations,", len(agg), "benchmarks,",
          len(cand), "candidates,", len(rising_use), "rising-usage,", len(rising_sat), "rising-saturation")


if __name__ == "__main__":
    main()
