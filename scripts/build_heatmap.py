#!/usr/bin/env python3
"""Build the benchmark × model HEATMAP — the autobenchmark.ai landing page (docs/index.html).

This replaces the retired tables dashboard. Grid:
  * Y axis = benchmark. Higher = more cumulative points. Points use the SHARED scoring
    (scripts/scoring.py): blog_headliner 3 / model_card 2 / system_card 1, counted as
    MAX per (benchmark, document, model) then SUMMED across documents (same as rank.py) —
    a benchmark headlined + tabled in one blog counts 3, headlined in 3 blogs counts 9.
    (H) suffix = currently Harbor-compatible (live-synced by sync_harbor.py); a DEEPER-BLUE (H)
    marks NATIVE Harbor format (registry entry with no adapter, incl. curated external-native
    datasets like deepswe), vs the regular deep-blue (H) for adapter-backed benchmarks.
  * X axis = citing model, MOST RECENT ON THE LEFT (models.yaml release_date; undated last).
  * cell (benchmark × model) = increasing DARKNESS OF GREY for the highest source class in
    which that model cites it: Headliner (near-black) > Model card (mid-grey) > System card
    (light-grey). In dark mode the ramp inverts (Headliner near-white, strongest).
  * hover / click-to-pin a cell → the source link(s) (headliner / model card / system card)
    with the reported score, for verifiability.

Filters (agentic/chat · Harbor-only · company) re-rank live over the VISIBLE columns.
Self-contained (embeds a compact JSON blob). Muted, Terminal-Bench-style monochrome UI:
grayscale citation ramp, two reserved blue accents (agentic label + Harbor (H) marks), and
Google Sans Code for the top toggles/selectors (body copy stays Inter). Reads
data/citations.jsonl (built by build.py, Harbor-synced by sync_harbor.py) + data/models.yaml.
"""
from __future__ import annotations

import collections
import datetime
import json
import pathlib
import re

import yaml
from scoring import points  # single source of truth for the 3/2/1 weights

ROOT = pathlib.Path(__file__).resolve().parents[1]
CITES = ROOT / "data" / "citations.jsonl"
MODELS = ROOT / "data" / "models.yaml"
OUT = ROOT / "docs" / "index.html"

# weight_class -> human label for the tooltip (points come from scoring.py)
WC_LABEL = {"blog_headliner": "Headliner", "model_card": "Model card", "system_card": "System card"}


def slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (s or "").lower())).strip("-")


def model_id(citing_model: str) -> str:
    return slug((citing_model or "").split(" / ")[0])


def main() -> int:
    rows = [json.loads(l) for l in open(CITES) if l.strip()]
    mdoc = yaml.safe_load(MODELS.read_text())
    models = mdoc.get("models", [])
    model_meta = {m["id"]: m for m in models}

    # Optional per-benchmark render label (registry.yaml `display:`). Keeps canonical IDs/keys stable
    # (used for search-links + citation joins) while the heatmap shows a human label — e.g. the
    # Terminal-Bench buckets render "Terminal-Bench 1.0, 2.0, 2.1" / "Terminal-Bench 3.0+" instead of
    # the hyphenated slug. Render-only; nothing downstream depends on it.
    reg = yaml.safe_load((ROOT / "data" / "registry.yaml").read_text()) or {}
    disp = {b["canonical"]: b["display"] for b in reg.get("benchmarks", []) if b.get("display")}

    companies = []
    seen = set()
    for m in models:
        if m["company"] not in seen:
            seen.add(m["company"])
            companies.append({"id": m["company"], "display": m["company_display"]})

    # ---- aggregate: MAX weight per (benchmark, model, document); collect per-doc display ----
    def newbench():
        return {"type": None, "domain": None, "on_harbor": False, "harbor_native": False,
                # model_id -> doc_id -> {p, wc, url, container, val, unit, cfg, dev}
                "m": collections.defaultdict(lambda: collections.defaultdict(
                    lambda: {"p": 0, "wc": None, "url": None, "container": None,
                             "val": None, "unit": None, "cfg": None, "dev": False}))}
    B = collections.defaultdict(newbench)

    for r in rows:
        c = r.get("benchmark_canonical")
        if not c:
            continue                                   # unresolved -> review queue, not the grid
        mid = model_id(r.get("citing_model"))
        if mid not in model_meta:
            continue
        did = r["source_doc"].get("id") or r["source_doc"]["url"]
        wc = r.get("weight_class")
        p = points(wc)
        b = B[c]
        b["type"] = b["type"] or r.get("type")
        b["domain"] = b["domain"] or r.get("domain")
        b["on_harbor"] = b["on_harbor"] or bool(r.get("on_harbor"))
        # native Harbor format = registry entry with no adapter (harbor_type "native"),
        # incl. the curated external-native overlay (e.g. deepswe) sync_harbor.py sets to "native".
        b["harbor_native"] = b["harbor_native"] or (r.get("harbor_type") == "native")
        d = b["m"][mid][did]
        if p >= d["p"]:                                # keep the DOC's max-class mention for display
            d["p"] = p
            d["wc"] = wc
        d["url"] = r["source_doc"]["url"]
        d["container"] = r["source_doc"].get("container")
        rep = r.get("reported") or {}
        val = rep.get("value")
        if rep.get("unit") == "percent" and isinstance(val, (int, float)):
            if d["val"] is None or (isinstance(d["val"], (int, float)) and val > d["val"]):
                d["val"], d["unit"] = val, "percent"
        elif d["val"] is None and val is not None:
            d["val"], d["unit"] = val, rep.get("unit")
        if rep.get("model_config"):
            d["cfg"] = rep["model_config"]
        if r.get("methodology_deviations"):
            d["dev"] = True

    benchmarks = []
    for canon, b in B.items():
        cells, total, sat = {}, 0, None
        for mid, docs in b["m"].items():
            docmax = [dd for dd in docs.values()]
            tier = max(dd["p"] for dd in docmax)       # cell colour = highest class in the cell
            pts = sum(dd["p"] for dd in docmax)        # cell points = sum of per-doc maxima
            score = None
            for dd in docmax:
                if dd["unit"] == "percent" and isinstance(dd["val"], (int, float)):
                    score = dd["val"] if score is None else max(score, dd["val"])
            doclist = sorted(
                [{"wc": dd["wc"], "url": dd["url"], "container": dd["container"],
                  "val": dd["val"], "unit": dd["unit"], "cfg": dd["cfg"], "dev": dd["dev"]}
                 for dd in docmax],
                key=lambda x: -points(x["wc"]))
            cells[mid] = {"tier": tier, "pts": pts, "score": score, "docs": doclist}
            total += pts
            if score is not None:
                sat = score if sat is None else max(sat, score)
        benchmarks.append({"canon": canon, "display": disp.get(canon, canon),
                           "type": b["type"] or "?", "domain": b["domain"] or "?",
                           "on_harbor": b["on_harbor"], "harbor_native": b["harbor_native"],
                           "points": total, "sat": sat,
                           "n_models": len(cells), "cells": cells})
    benchmarks.sort(key=lambda x: (-x["points"], x["canon"]))

    asof = max([datetime.date.today().isoformat()]
               + [r["source_doc"]["pub_date"] for r in rows if r["source_doc"].get("pub_date")])

    data = {
        "as_of": asof,
        "repo": "christicode/benchmark-citations",
        "wc_points": {k: points(k) for k in WC_LABEL},
        "wc_label": WC_LABEL,
        "companies": companies,
        "models": [{"id": m["id"], "display": m["display"], "company": m["company"],
                    "company_display": m["company_display"],
                    "release_date": m.get("release_date"), "dated": bool(m.get("release_date"))}
                   for m in models],
        "benchmarks": benchmarks,
    }

    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(PAGE.replace("/*__DATA__*/", json.dumps(data, ensure_ascii=False)))
    filled = sum(b["n_models"] for b in benchmarks)
    print(f"wrote {OUT} | {len(benchmarks)} benchmarks × {len(models)} models "
          f"| {filled} filled cells | as of {asof}")
PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>Benchmark-Bench</title>
<link rel=preconnect href="https://fonts.googleapis.com">
<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans+Code:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap" rel=stylesheet>
<style>
:root{--bg:#ffffff;--panel:#f6f7f8;--b:#e6e7ea;--fg:#40454e;--emph:#0a0c10;--mut:#969ca6;
  --accent:#0a0c10;--amber:#d97706;--segon:#eceef1;--seghov:#f4f5f7;
  /* two reserved accents: agentic (deep blue) + Harbor (deep indigo, native = deeper) */
  --acc-agentic:#1d4ed8;--acc-harbor:#4338ca;--acc-harbor-native:#312e81;
  /* GRAYSCALE citation ramp: System card (lightest grey) -> Model card (mid) -> Headliner (near-black) */
  --t1:#d8dbdf;--t2:#8b9198;--t3:#16181d;--empty:#fafbfc;
  --mono:"Google Sans Code",ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace}
body.dark{--bg:#0c0d10;--panel:#15171c;--b:#262a31;--fg:#9aa1ac;--emph:#f2f4f7;--mut:#6b7280;
  --accent:#f2f4f7;--amber:#f59e0b;--segon:#262b34;--seghov:#1b1e24;
  --acc-agentic:#60a5fa;--acc-harbor:#a5b4fc;--acc-harbor-native:#c7d2fe;
  /* inverted grayscale: Headliner (near-white, strongest) -> Model card (mid) -> System card (dark grey) */
  --t1:#3a3f47;--t2:#8b9198;--t3:#f2f4f7;--empty:#141619}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.55 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;transition:background-color 0.2s, color 0.2s}
.wrap{max-width:1400px;margin:0 auto;padding:26px 22px 40px}
.hdr{display:flex;justify-content:space-between;align-items:center;margin:0 0 14px}
h1{font-family:var(--mono);font-size:23px;font-weight:700;letter-spacing:-.01em;color:var(--emph);margin:0}
.theme-btn{cursor:pointer;border:1px solid var(--b);background:var(--panel);color:var(--emph);padding:6px 12px;border-radius:8px;font-family:var(--mono);font-size:14px;transition:.12s;user-select:none}
.theme-btn:hover{border-color:var(--accent);color:var(--accent)}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.bar{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:0 0 14px;font-family:var(--mono);
  background:var(--bg);border:1px solid var(--b);border-radius:0;padding:9px 12px}
.bar .grp{display:flex;gap:8px;align-items:center}
.bar b{color:var(--mut);font-size:11px;font-weight:400;text-transform:uppercase;letter-spacing:.06em;margin-right:1px}
/* segmented control (Harbor-Hub style): squared group, hairline dividers, subtle grey active */
.seg{display:inline-flex;border:1px solid var(--b);border-radius:0;overflow:hidden}
.chip{font-size:12px;font-weight:400;padding:5px 11px;border:0;border-right:1px solid var(--b);
  background:transparent;color:var(--mut);cursor:pointer;user-select:none;transition:.12s;white-space:nowrap}
.chip:last-child{border-right:0}
.chip:hover{background:var(--seghov);color:var(--emph)}
.chip.on{background:var(--segon);color:var(--emph);font-weight:400}
.chip.co.on{background:var(--segon);color:var(--emph);font-weight:400}
.co-btn{font-size:12px;color:var(--accent);cursor:pointer;user-select:none}
.co-btn:hover{text-decoration:underline}
.co-sep{color:var(--mut);margin:0 3px}
/* dual-handle range slider (Google-Flights style) for the release-date window */
.range{position:relative;width:230px;height:22px;margin:0 2px}
.range-track{position:absolute;left:0;right:0;top:9px;height:4px;background:var(--b);border-radius:3px}
.range-fill{position:absolute;top:9px;height:4px;background:var(--accent);border-radius:3px}
.range-input{position:absolute;top:4px;left:0;width:100%;height:14px;margin:0;background:transparent;
  -webkit-appearance:none;appearance:none;pointer-events:none}
.range-input:focus{outline:none}
.range-input::-webkit-slider-runnable-track{height:14px;background:transparent;border:none}
.range-input::-moz-range-track{height:14px;background:transparent;border:none}
.range-input::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;pointer-events:auto;
  width:13px;height:13px;border-radius:50%;background:var(--bg);border:2px solid var(--accent);
  cursor:ew-resize;box-shadow:0 1px 2px rgba(0,0,0,.18)}
.range-input::-moz-range-thumb{pointer-events:auto;width:13px;height:13px;border-radius:50%;
  background:var(--bg);border:2px solid var(--accent);cursor:ew-resize;box-shadow:0 1px 2px rgba(0,0,0,.18)}
.range-lbl{font-size:11px;color:var(--emph);font-variant-numeric:tabular-nums;white-space:nowrap;letter-spacing:.01em}
.legend{color:var(--mut);font-size:12px;margin:12px 2px 0;display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.sw{display:inline-block;width:12px;height:12px;border:1px solid var(--b);vertical-align:-2px;margin-right:4px;border-radius:3px}
.grid-scroll{overflow:auto;max-height:80vh;border:1px solid var(--b);border-radius:0}
table.hm{border-collapse:separate;border-spacing:0;margin-right:110px}
table.hm th,table.hm td{padding:0;margin:0}
thead{position:sticky;top:0;z-index:3;background:var(--bg)}
thead th{position:relative}
th.mh{height:170px;min-width:28px;vertical-align:bottom;transition:background-color 0.15s}
th.mh.active-col{background:var(--panel)!important}
th.mh .lab{position:absolute;z-index:1;bottom:12px;left:50%;transform:rotate(-55deg);transform-origin:0 50%;white-space:nowrap;
  font-size:11.5px;font-weight:500;color:var(--emph)}
td.yl{position:sticky;left:0;z-index:2;background:var(--bg);border-right:1px solid var(--b);
  padding:0 14px 0 10px;white-space:nowrap;font-size:12.5px;color:var(--emph);border-bottom:1px solid var(--b);transition:background-color 0.15s}
td.yl.active-row{background:var(--panel)!important;color:var(--accent)!important}
td.yl .rank{color:var(--mut);display:inline-block;min-width:22px;font-variant-numeric:tabular-nums}
td.yl .nm{cursor:pointer;font-weight:500;color:var(--emph)}
td.yl .nm:hover{color:var(--accent);text-decoration:underline}
td.yl .h{color:var(--acc-harbor);font-weight:700}
td.yl .h.hn{color:var(--acc-harbor-native)}
td.yl .ty{font-size:10px;color:var(--mut);margin-left:6px}
td.yl .ty.ag{color:var(--acc-agentic);font-weight:600}
th.corner{position:sticky;left:0;z-index:6;background:var(--bg);border-right:1px solid var(--b)}
td.cell{width:23px;height:30px;text-align:center;border-right:1px solid var(--b);
  border-bottom:1px solid var(--b);cursor:default;background:var(--empty)}
td.cell.f{cursor:pointer}
td.cell.t1{background:var(--t1)}td.cell.t2{background:var(--t2)}td.cell.t3{background:var(--t3)}
td.cell.pin{outline:2px solid var(--acc-agentic);outline-offset:-2px}
#tip{position:fixed;z-index:20;max-width:360px;background:var(--bg);color:var(--fg);border:1px solid var(--b);
  border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.2);padding:11px 13px;display:none;font-size:12.5px}
#tip h4{margin:0 0 5px;font-size:13px;font-weight:600;color:var(--emph)}
#tip .r{margin:3px 0;color:var(--fg)}
#tip .dt{font-weight:600;color:var(--emph)}
#tip .g{color:var(--amber)}
#tip .cl{color:var(--mut);font-size:11.5px}
#tip a{font-weight:600;color:var(--accent)}
input[type="text"], input[type="date"] {
  border: 1px solid var(--b);
  border-radius: 0;
  padding: 5px 9px;
  font-family: var(--mono);
  font-size: 12px;
  background: var(--bg);
  color: var(--fg);
  transition: border-color 0.12s;
}
input[type="text"]:focus, input[type="date"]:focus {
  outline: none;
  border-color: var(--accent);
}
</style></head><body><div class=wrap>
<div class=hdr>
  <h1>Benchmark-Bench</h1>
  <button id=theme-toggle class=theme-btn onclick="toggleTheme()">🌙</button>
</div>

<div class=bar>
  <div class=grp><b>benchmarks</b>
    <div class=seg>
      <span class=chip data-ty=all onclick='setTy(this)'>all</span>
      <span class=chip data-ty=agentic onclick='setTy(this)'>agentic</span>
      <span class=chip data-ty=chat onclick='setTy(this)'>chat</span>
    </div>
    <div class=seg>
      <span class=chip id=harb onclick='toggleHarb(this)'>Harbor</span>
      <span class=chip id=multi onclick='toggleMulti(this)'>2+ cites</span>
    </div>
    <input type=text id=search-input placeholder="Search…" oninput="setSearch(this.value)" style="width:150px;">
  </div>
  <div class=grp><b>timeframe</b>
    <div class=range id=range title="drag the handles to set the release-date window">
      <div class=range-track></div>
      <div class=range-fill id=range-fill></div>
      <input type=range id=range-lo class=range-input oninput="onRange(this)">
      <input type=range id=range-hi class=range-input oninput="onRange(this)">
    </div>
    <span class=range-lbl id=range-lbl>all time</span>
  </div>
  <div class=grp><b>company</b>
    <span class=co-btn onclick="setAllCos(true)">all</span><span class=co-sep>/</span><span class=co-btn onclick="setAllCos(false)">none</span>
    <div class=seg id=cos-seg></div>
  </div>
</div>

<div class=grid-scroll><table class=hm id=hm></table></div>

<div class=legend>
  <span><span class=sw style=background:var(--t3)></span>Headliner (3)</span>
  <span><span class=sw style=background:var(--t2)></span>Model card (2)</span>
  <span><span class=sw style=background:var(--t1)></span>System card (1)</span>
  <span><span class=sw style=background:var(--empty)></span>not cited</span>
</div>
</div>

<div id=tip></div>
<script>
var DATA = /*__DATA__*/;

var state = {
  ty: 'all',
  harb: false,
  multi: true,          // "2+ cites" ON by default -> hide single-citation benchmarks
  rangeStart: null,     // release-date window as day-numbers (set in initRange)
  rangeEnd: null,
  search: '',
  cos: {}
};
DATA.companies.forEach(function(c){ state.cos[c.id]=true; });

var cos=document.getElementById('cos-seg');
DATA.companies.forEach(function(c){
  var s=document.createElement('span'); s.className='chip co on'; s.textContent=c.display;
  s.id = 'co-' + c.id;
  s.onclick=function(){ state.cos[c.id]=!state.cos[c.id]; s.classList.toggle('on'); render(); };
  cos.appendChild(s);
});
document.querySelector('.chip[data-ty=all]').classList.add('on');
document.getElementById('multi').classList.add('on');

// Theme init & handler
function toggleTheme() {
  document.body.classList.toggle('dark');
  var isDark = document.body.classList.contains('dark');
  localStorage.setItem('theme', isDark ? 'dark' : 'light');
  document.getElementById('theme-toggle').textContent = isDark ? '☀️' : '🌙';
}
if (localStorage.getItem('theme') === 'dark') {
  document.body.classList.add('dark');
  document.getElementById('theme-toggle').textContent = '☀️';
}

function setTy(el){ state.ty=el.dataset.ty;
  document.querySelectorAll('.chip[data-ty]').forEach(function(x){x.classList.remove('on')});
  el.classList.add('on'); render(); }
function toggleHarb(el){ state.harb=!state.harb; el.classList.toggle('on'); render(); }
function toggleMulti(el){ state.multi=!state.multi; el.classList.toggle('on'); render(); }

// ---- release-date range slider (dual handle, Google-Flights style) ----
function dayNum(d){ return Math.floor(new Date(d+'T00:00:00Z').getTime()/86400000); }
var DATED=DATA.models.filter(function(m){return m.release_date;}).map(function(m){return dayNum(m.release_date);});
var MIND=DATED.length?Math.min.apply(null,DATED):0, MAXD=DATED.length?Math.max.apply(null,DATED):0;
function fmtDay(n){ return new Date(n*86400000).toLocaleString('en-US',{month:'short',year:'numeric',timeZone:'UTC'}); }
function initRange(){
  state.rangeStart=MIND; state.rangeEnd=MAXD;
  var lo=document.getElementById('range-lo'), hi=document.getElementById('range-hi');
  [lo,hi].forEach(function(s){ s.min=MIND; s.max=MAXD; s.step=1; });
  lo.value=MIND; hi.value=MAXD; updateRangeUI();
}
function onRange(el){
  var lo=document.getElementById('range-lo'), hi=document.getElementById('range-hi');
  var a=+lo.value, b=+hi.value;
  if(a>b){ if(el.id==='range-lo'){ hi.value=a; b=a; } else { lo.value=b; a=b; } }
  state.rangeStart=a; state.rangeEnd=b; updateRangeUI(); render();
}
function updateRangeUI(){
  var span=(MAXD-MIND)||1;
  var f=document.getElementById('range-fill');
  f.style.left=((state.rangeStart-MIND)/span*100)+'%';
  f.style.width=((state.rangeEnd-state.rangeStart)/span*100)+'%';
  document.getElementById('range-lbl').textContent=
    (state.rangeStart<=MIND && state.rangeEnd>=MAXD)?'all time'
      :(fmtDay(state.rangeStart)+' – '+fmtDay(state.rangeEnd));
}

function setSearch(val) {
  state.search = val.trim();
  render();
}

function setAllCos(val) {
  DATA.companies.forEach(function(c){
    state.cos[c.id] = val;
    var chip = document.getElementById('co-' + c.id);
    if (chip) {
      if (val) chip.classList.add('on');
      else chip.classList.remove('on');
    }
  });
  render();
}

function inTimeframe(dateStr) {
  if (!dateStr) return true;   // undated models can't be range-filtered -> always shown
  var d = dayNum(dateStr);
  return d >= state.rangeStart && d <= state.rangeEnd;
}

function visibleModels(){
  return DATA.models.filter(function(m){
    if (!state.cos[m.company]) return false;
    return inTimeframe(m.release_date);
  });
}

function rowVisible(b){
  if(state.ty!=='all' && b.type!==state.ty) return false;
  if(state.harb && !b.on_harbor) return false;
  if(state.search) {
    var q = state.search.toLowerCase();
    if(b.canon.toLowerCase().indexOf(q) === -1 && (b.display||'').toLowerCase().indexOf(q) === -1) return false;
  }
  return true;
}

function highlightCrosshair(el, show) {
  var m = el.dataset.m;
  var colHeader = document.querySelector('th[data-m-id="' + m + '"]');
  if (colHeader) colHeader.classList.toggle('active-col', show);
  
  var rowHeader = el.parentElement.querySelector('td.yl');
  if (rowHeader) rowHeader.classList.toggle('active-row', show);
}

function render(){
  var vm = visibleModels();
  var vmids = vm.map(function(m){return m.id;});
  var rows=[];
  DATA.benchmarks.forEach(function(b){
    if(!rowVisible(b)) return;
    var pts=0, nm=0, nc=0;
    vmids.forEach(function(id){ var c=b.cells[id]; if(c){ pts+=c.pts; nm++;
      nc+=(c.docs?c.docs.length:1); } });
    if(nm===0) return;                          // no citation in visible columns
    if(state.multi && nc<=1) return;            // hide single-citation benchmarks ("2+ cites")
    rows.push({b:b, pts:pts, nm:nm});
  });
  rows.sort(function(x,y){ return (y.pts-x.pts) || (y.nm-x.nm) || (x.b.canon<y.b.canon?-1:1); });

  var t=document.getElementById('hm');
  var H=[];
  H.push('<thead><tr><th class=corner>&nbsp;</th>');
  vm.forEach(function(m){
    H.push('<th class="mh'+(m.dated?'':' new')+'" data-m-id="'+m.id+'" title="'+esc(m.model_title(m))+'">'+
      '<div class=lab>'+esc(m.display)+'</div></th>');
  });
  H.push('</tr></thead><tbody>');
  rows.forEach(function(r,i){
    var b=r.b;
    var ty = b.type==='agentic'?'<span class="ty ag">agentic</span>'
            : b.type==='chat'?'<span class=ty>chat</span>':'';
    var h = b.on_harbor? ' <span class="h'+(b.harbor_native?' hn':'')+'" title="'+
            (b.harbor_native?'Native Harbor format (no adapter)':'Harbor-compatible (via adapter)')+
            '">(H)</span>':'';
    H.push('<tr><td class=yl><span class=rank>'+(i+1)+'</span>'+
      '<span class=nm onclick="openRec(\''+esc(b.canon)+'\')" title="see citation records on GitHub">'+
      esc(b.display||b.canon)+'</span>'+h+ty+'</td>');
    vm.forEach(function(m){
      var c=b.cells[m.id];
      if(!c){ H.push('<td class=cell></td>'); return; }
      H.push('<td class="cell f t'+c.tier+'" data-b="'+esc(b.canon)+'" data-m="'+m.id+
        '" onmouseenter="showTip(event,this);highlightCrosshair(this,true)" onmouseleave="hideTip();highlightCrosshair(this,false)" onclick="pin(this)"></td>');
    });
    H.push('</tr>');
  });
  H.push('</tbody>');
  if(rows.length===0){
    H=['<tbody><tr><td class=yl style="padding:14px 10px;white-space:normal;color:var(--mut)">'+
       'No benchmarks match. Try re-adding companies.'+
       '</td></tr></tbody>'];
  }
  t.innerHTML=H.join('');
}

// model header tooltip text
DATA.models.forEach(function(m){ m.model_title=function(){ return m.display+
  (m.release_date?(' · '+m.release_date):' · date unknown')+' · '+m.company_display; }; });

var pinned=null;
function cellData(el){
  var b=el.dataset.b, m=el.dataset.m;
  var rec=DATA.benchmarks.find(function(x){return x.canon===b;});
  return {b:b, bdisp:(rec.display||rec.canon), c:rec.cells[m], mm:DATA.models.find(function(x){return x.id===m;})};
}
function tipHTML(d){
  var s='<h4>'+esc(d.bdisp)+' × '+esc(d.mm.display)+'</h4>';
  d.c.docs.forEach(function(doc){
    var lab=DATA.wc_label[doc.wc]||doc.wc||'cited';
    var v=(doc.val!=null)?(' — '+esc(String(doc.val))+(doc.unit==='percent'?'%':(doc.unit&&doc.unit!=='other'?(' '+doc.unit):''))):'';
    var ct=doc.container?(' <span class=cl>['+esc(doc.container)+']</span>'):'';
    s+='<div class=r><span class=dt>'+esc(lab)+'</span>'+v+
       (doc.dev?' <span class=g title="methodology deviation on record">⚙</span>':'')+ct+
       '<br><a href="'+esc(doc.url)+'" target=_blank rel=noopener>source ↗</a>'+
       (doc.cfg?(' <span class=cl>'+esc(doc.cfg)+'</span>'):'')+'</div>';
  });
  return s;
}
function pos(el){ var tip=document.getElementById('tip'); var r=el.getBoundingClientRect();
  var x=r.right+10, y=r.top; var t=tip.getBoundingClientRect();
  if(x+t.width>innerWidth) x=r.left-t.width-10; if(x<6) x=6;
  if(y+t.height>innerHeight) y=innerHeight-t.height-8; if(y<6) y=6;
  tip.style.left=x+'px'; tip.style.top=y+'px'; }
function showTip(e,el){ if(pinned) return; var tip=document.getElementById('tip');
  tip.innerHTML=tipHTML(cellData(el)); tip.style.display='block'; posMouse(e); }
function posMouse(e){ var tip=document.getElementById('tip');
  var x=e.clientX+14, y=e.clientY+14; var r=tip.getBoundingClientRect();
  if(x+r.width>innerWidth) x=e.clientX-r.width-14; if(x<6) x=6;
  if(y+r.height>innerHeight) y=innerHeight-r.height-8; if(y<6) y=6;
  tip.style.left=x+'px'; tip.style.top=y+'px'; }
function hideTip(){ if(!pinned) document.getElementById('tip').style.display='none'; }
function pin(el){
  document.querySelectorAll('td.cell.pin').forEach(function(x){x.classList.remove('pin')});
  if(pinned===el){ pinned=null; document.getElementById('tip').style.display='none'; return; }
  pinned=el; el.classList.add('pin');
  var tip=document.getElementById('tip'); tip.innerHTML=tipHTML(cellData(el));
  tip.style.display='block'; pos(el);
}
document.addEventListener('click',function(e){
  if(pinned && !e.target.classList.contains('cell')){ pinned.classList.remove('pin'); pinned=null;
    document.getElementById('tip').style.display='none'; }
},true);
function openRec(canon){
  window.open('https://github.com/search?q='+encodeURIComponent('repo:'+DATA.repo+' "'+canon+'"')+'&type=code','_blank');
}
function esc(s){ return String(s).replace(/[&<>"']/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];}); }

initRange();
render();
</script>
</body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
