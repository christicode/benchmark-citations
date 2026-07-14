#!/usr/bin/env python3
"""Build the benchmark × model HEATMAP — the autobenchmark.ai landing page (docs/index.html).

This replaces the retired tables dashboard. Grid:
  * Y axis = benchmark. Higher = more cumulative points. Points use the SHARED scoring
    (scripts/scoring.py): blog_headliner 3 / model_card 2 / system_card 1, counted as
    MAX per (benchmark, document, model) then SUMMED across documents (same as rank.py) —
    a benchmark headlined + tabled in one blog counts 3, headlined in 3 blogs counts 9.
    (H) suffix = currently Harbor-compatible (live-synced by sync_harbor.py).
  * X axis = citing model, MOST RECENT ON THE LEFT (models.yaml release_date; undated last).
  * cell (benchmark × model) = increasing DARKNESS OF BLUE for the highest source class in
    which that model cites it: Headliner (darkest) > Model card > System card (lightest).
  * Saturation gutter (left of the grid) = max reported % for that benchmark (headroom),
    on a green→amber→red ramp; hover shows which model set it + a source link.
  * hover / click-to-pin a cell → the source link(s) (headliner / model card / system card)
    with the reported score, for verifiability.

Filters (agentic/chat · Harbor-only · company) re-rank live over the VISIBLE columns.
Self-contained (embeds a compact JSON blob; modern sans UI via Inter). Reads
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

    companies = []
    seen = set()
    for m in models:
        if m["company"] not in seen:
            seen.add(m["company"])
            companies.append({"id": m["company"], "display": m["company_display"]})

    # ---- aggregate: MAX weight per (benchmark, model, document); collect per-doc display ----
    def newbench():
        return {"type": None, "domain": None, "on_harbor": False,
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
        benchmarks.append({"canon": canon, "type": b["type"] or "?", "domain": b["domain"] or "?",
                           "on_harbor": b["on_harbor"], "points": total, "sat": sat,
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
<title>PaperTrail</title>
<link rel=preconnect href="https://fonts.googleapis.com">
<link rel=preconnect href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel=stylesheet>
<style>
:root{--bg:#ffffff;--panel:#f7f8fa;--b:#e6e8eb;--fg:#3d4451;--emph:#0d0f13;--mut:#9aa1ac;
  --blue:#2563eb;--green:#16a34a;--amber:#d97706;--red:#dc2626;--violet:#7c3aed;
  /* blue citation ramp: System card (light) -> Model card -> Headliner (dark) */
  --t1:#dbeafe;--t2:#7fb0ee;--t3:#1e56b0;--empty:#fbfcfd}
body.dark{--bg:#0f172a;--panel:#1e293b;--b:#334155;--fg:#94a3b8;--emph:#f8fafc;--mut:#64748b;
  --blue:#3b82f6;--green:#22c55e;--amber:#f59e0b;--red:#ef4444;--violet:#8b5cf6;
  --t1:#1e3a8a;--t2:#3b82f6;--t3:#60a5fa;--empty:#1e293b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.55 "Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;transition:background-color 0.2s, color 0.2s}
.wrap{max-width:1400px;margin:0 auto;padding:26px 22px 40px}
.hdr{display:flex;justify-content:space-between;align-items:center;margin:0 0 14px}
h1{font-size:24px;font-weight:700;letter-spacing:-.02em;color:var(--emph);margin:0}
.theme-btn{cursor:pointer;border:1px solid var(--b);background:var(--panel);color:var(--emph);padding:6px 12px;border-radius:8px;font-size:14px;transition:.12s;user-select:none}
.theme-btn:hover{border-color:var(--blue);color:var(--blue)}
a{color:var(--blue);text-decoration:none}a:hover{text-decoration:underline}
.bar{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin:0 0 14px;
  background:var(--panel);border:1px solid var(--b);border-radius:12px;padding:10px 14px}
.bar .grp{display:flex;gap:6px;align-items:center}
.bar b{color:var(--mut);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-right:2px}
.chip{font-size:12.5px;font-weight:500;padding:4px 11px;border:1px solid var(--b);
  background:var(--bg);color:var(--fg);border-radius:999px;cursor:pointer;user-select:none;transition:.12s}
.chip:hover{border-color:var(--blue);color:var(--blue)}
.chip.on{background:var(--blue);color:#fff;border-color:var(--blue)}
.chip.co.on{background:var(--emph);color:var(--bg);border-color:var(--emph)}
body.dark .chip.co.on{background:var(--emph);color:#0f172a;border-color:var(--emph)}
.legend{color:var(--mut);font-size:12px;margin:12px 2px 0;display:flex;gap:16px;flex-wrap:wrap;align-items:center}
.sw{display:inline-block;width:12px;height:12px;border:1px solid var(--b);vertical-align:-2px;margin-right:4px;border-radius:3px}
.grid-scroll{overflow:auto;max-height:80vh;border:1px solid var(--b);border-radius:12px}
table.hm{border-collapse:separate;border-spacing:0}
table.hm th,table.hm td{padding:0;margin:0}
thead th{position:sticky;top:0;z-index:3;background:var(--bg)}
th.mh{height:120px;vertical-align:bottom;padding-bottom:8px;transition:background-color 0.15s}
th.mh.active-col{background:var(--panel)!important}
th.mh .lab{writing-mode:vertical-rl;transform:rotate(180deg);white-space:nowrap;
  font-size:11.5px;font-weight:600;color:var(--emph);max-height:104px;overflow:hidden}
td.yl{position:sticky;left:0;z-index:2;background:var(--bg);border-right:1px solid var(--b);
  padding:0 10px;white-space:nowrap;font-size:12.5px;color:var(--emph);border-bottom:1px solid var(--b);transition:background-color 0.15s}
td.yl.active-row{background:var(--panel)!important;color:var(--blue)!important}
td.yl .rank{color:var(--mut);display:inline-block;min-width:22px;font-variant-numeric:tabular-nums}
td.yl .nm{cursor:pointer;font-weight:500;color:var(--emph)}
td.yl .nm:hover{color:var(--blue);text-decoration:underline}
td.yl .h{color:var(--green);font-weight:700}
td.yl .ty{font-size:10px;color:var(--mut);margin-left:6px}
td.yl .ty.ag{color:var(--green)}
td.sat{position:sticky;left:var(--gutL);z-index:2;background:var(--bg);width:78px;
  border-right:1px solid var(--b);border-bottom:1px solid var(--b);padding:0 8px}
td.sat.hs{cursor:help}
.satbar{height:9px;background:#eef1f4;border-radius:999px;position:relative;overflow:hidden}
body.dark .satbar{background:#334155}
.satbar>i{display:block;height:100%;border-radius:999px}
.satnum{font-size:10px;color:var(--mut);font-variant-numeric:tabular-nums}
th.corner{left:0;z-index:6;background:var(--bg);border-right:1px solid var(--b)}
th.corner.sat2{left:var(--gutL);z-index:6;vertical-align:bottom;padding:0 8px 8px}
th.corner.sat2 .satlbl{font-size:10px;font-weight:600;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}
td.cell{width:22px;height:22px;text-align:center;border-right:1px solid var(--b);
  border-bottom:1px solid var(--b);cursor:default;background:var(--empty)}
td.cell.f{cursor:pointer}
td.cell.t1{background:var(--t1)}td.cell.t2{background:var(--t2)}td.cell.t3{background:var(--t3)}
td.cell.pin{outline:2px solid var(--red);outline-offset:-2px}
.count{color:var(--mut);font-size:12.5px;margin:10px 2px}
#tip{position:fixed;z-index:20;max-width:360px;background:var(--bg);color:var(--fg);border:1px solid var(--b);
  border-radius:12px;box-shadow:0 8px 30px rgba(0,0,0,.2);padding:11px 13px;display:none;font-size:12.5px}
#tip h4{margin:0 0 5px;font-size:13px;font-weight:600;color:var(--emph)}
#tip .r{margin:3px 0;color:var(--fg)}
#tip .dt{font-weight:600;color:var(--emph)}
#tip .g{color:var(--amber)}
#tip .cl{color:var(--mut);font-size:11.5px}
#tip a{font-weight:600;color:var(--blue)}
.foot{color:var(--mut);font-size:12px;margin:16px 0 0}
input[type="text"], input[type="date"] {
  border: 1px solid var(--b);
  border-radius: 6px;
  padding: 3px 8px;
  font-family: inherit;
  font-size: 12.5px;
  background: var(--bg);
  color: var(--fg);
  transition: border-color 0.12s;
}
input[type="text"]:focus, input[type="date"]:focus {
  outline: none;
  border-color: var(--blue);
}
.co-btn {
  font-size:12px;
  color:var(--blue);
  cursor:pointer;
  margin: 0 4px;
  user-select:none;
}
.co-btn:hover {
  text-decoration:underline;
}
</style></head><body><div class=wrap>
<div class=hdr>
  <h1>PaperTrail</h1>
  <button id=theme-toggle class=theme-btn onclick="toggleTheme()">🌙</button>
</div>

<div class=bar>
  <div class=grp><b>search</b>
    <input type=text id=search-input placeholder="Search benchmarks..." oninput="setSearch(this.value)" style="border-radius:999px;width:170px;"></div>
  <div class=grp><b>type</b>
    <span class=chip data-ty=all onclick='setTy(this)'>all</span>
    <span class=chip data-ty=agentic onclick='setTy(this)'>agentic</span>
    <span class=chip data-ty=chat onclick='setTy(this)'>chat</span></div>
  <div class=grp><b>harbor</b>
    <span class=chip id=harb onclick='toggleHarb(this)'>Harbor-compatible only</span></div>
  <div class=grp><b>tail</b>
    <span class=chip id=tail onclick='toggleTail(this)'>show single-citation</span></div>
  <div class=grp><b>timeframe</b>
    <span class=chip data-tf=all onclick='setTf(this)'>all time</span>
    <span class=chip data-tf=3m onclick='setTf(this)'>3 months</span>
    <span class=chip data-tf=6m onclick='setTf(this)'>6 months</span>
    <span class=chip data-tf=1y onclick='setTf(this)'>1 year</span>
    <span class=chip data-tf=custom onclick='setTf(this)'>custom</span>
    <div id=custom-dates style="display:none;gap:6px;align-items:center;font-size:12.5px;border-left:1px solid var(--b);padding-left:10px;margin-left:4px;">
      from <input type=date id=date-start onchange="setCustomDates()">
      to <input type=date id=date-end onchange="setCustomDates()">
    </div>
  </div>
  <div class=grp><b>options</b>
    <span class=chip id=undated onclick='toggleUndated(this)'>include undated</span></div>
  <div class=grp id=cos><b>company</b><span class=co-btn onclick="setAllCos(true)">all</span>/<span class=co-btn onclick="setAllCos(false)">none</span></div>
</div>

<div class=grid-scroll><table class=hm id=hm></table></div>
<div class=count id=count></div>

<div class=legend>
  <span><b style="color:var(--mut);font-weight:600">cell — cited in a:</b></span>
  <span><span class=sw style=background:var(--t3)></span>Headliner (3)</span>
  <span><span class=sw style=background:var(--t2)></span>Model card (2)</span>
  <span><span class=sw style=background:var(--t1)></span>System card (1)</span>
  <span><span class=sw style=background:var(--empty)></span>not cited</span>
  <span>· <b class=h style=color:var(--green)>(H)</b> = Harbor-compatible</span>
  <span>· Saturation = max reported % (hover for the model + source)</span>
</div>
<p class=foot>Points: Headliner 3 · Model card 2 · System card 1, max per document then summed.
Click a cell to pin its source links. christicode/benchmark-citations.</p>
</div>

<div id=tip></div>
<script>
var DATA = /*__DATA__*/;

var state = {
  ty: 'all',
  harb: false,
  tail: false,
  timeframe: 'all',
  customStart: '',
  customEnd: '',
  includeUndated: true,
  search: '',
  cos: {}
};
DATA.companies.forEach(function(c){ state.cos[c.id]=true; });

var cos=document.getElementById('cos');
DATA.companies.forEach(function(c){
  var s=document.createElement('span'); s.className='chip co on'; s.textContent=c.display;
  s.id = 'co-' + c.id;
  s.onclick=function(){ state.cos[c.id]=!state.cos[c.id]; s.classList.toggle('on'); render(); };
  cos.appendChild(s);
});
document.querySelector('.chip[data-ty=all]').classList.add('on');
document.querySelector('.chip[data-tf=all]').classList.add('on');
document.getElementById('undated').classList.add('on');

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
function toggleTail(el){ state.tail=!state.tail; el.classList.toggle('on'); render(); }

function setTf(el) {
  state.timeframe = el.dataset.tf;
  document.querySelectorAll('.chip[data-tf]').forEach(function(x){x.classList.remove('on')});
  el.classList.add('on');
  var div = document.getElementById('custom-dates');
  if (state.timeframe === 'custom') {
    div.style.display = 'flex';
  } else {
    div.style.display = 'none';
  }
  render();
}

function setCustomDates() {
  state.customStart = document.getElementById('date-start').value;
  state.customEnd = document.getElementById('date-end').value;
  render();
}

function toggleUndated(el) {
  state.includeUndated = !state.includeUndated;
  el.classList.toggle('on');
  render();
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
  if (!dateStr) {
    return state.includeUndated;
  }
  if (state.timeframe === 'all') return true;
  
  var date = new Date(dateStr);
  var refDate = new Date(DATA.as_of);
  
  if (state.timeframe === '3m') {
    var limit = new Date(refDate);
    limit.setMonth(limit.getMonth() - 3);
    return date >= limit && date <= refDate;
  }
  if (state.timeframe === '6m') {
    var limit = new Date(refDate);
    limit.setMonth(limit.getMonth() - 6);
    return date >= limit && date <= refDate;
  }
  if (state.timeframe === '1y') {
    var limit = new Date(refDate);
    limit.setFullYear(limit.getFullYear() - 1);
    return date >= limit && date <= refDate;
  }
  if (state.timeframe === 'custom') {
    var start = state.customStart ? new Date(state.customStart) : null;
    var end = state.customEnd ? new Date(state.customEnd) : null;
    if (start && date < start) return false;
    if (end && date > end) return false;
    return true;
  }
  return true;
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
    if(b.canon.toLowerCase().indexOf(q) === -1) return false;
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

function highlightRow(el, show) {
  var rowHeader = el.parentElement.querySelector('td.yl');
  if (rowHeader) rowHeader.classList.toggle('active-row', show);
}

function render(){
  var vm = visibleModels();
  var vmids = vm.map(function(m){return m.id;});
  var rows=[];
  DATA.benchmarks.forEach(function(b){
    if(!rowVisible(b)) return;
    var pts=0, sat=null, satMid=null, nm=0;
    vmids.forEach(function(id){ var c=b.cells[id]; if(c){ pts+=c.pts; nm++;
      if(c.score!=null && (sat==null || c.score>sat)){ sat=c.score; satMid=id; } } });
    if(nm===0) return;                          // no citation in visible columns
    if(!state.tail && b.n_models<2) return;     // long-tail cut (GLOBAL count, so a company
                                                // filter still re-ranks densely 1,2,3,4...)
    rows.push({b:b, pts:pts, sat:sat, satMid:satMid, nm:nm});
  });
  rows.sort(function(x,y){ return (y.pts-x.pts) || (y.nm-x.nm) || (x.b.canon<y.b.canon?-1:1); });

  var t=document.getElementById('hm');
  var H=[];
  H.push('<thead><tr><th class=corner>&nbsp;</th><th class="corner sat2"><span class=satlbl>Saturation</span></th>');
  vm.forEach(function(m){
    H.push('<th class="mh'+(m.dated?'':' new')+'" data-m-id="'+m.id+'" title="'+esc(m.model_title(m))+'">'+
      '<div class=lab>'+esc(m.display)+'</div></th>');
  });
  H.push('</tr></thead><tbody>');
  rows.forEach(function(r,i){
    var b=r.b;
    var ty = b.type==='agentic'?'<span class="ty ag">agentic</span>'
            : b.type==='chat'?'<span class=ty>chat</span>':'';
    var h = b.on_harbor? ' <span class=h title="Harbor-compatible">(H)</span>':'';
    H.push('<tr><td class=yl><span class=rank>'+(i+1)+'</span>'+
      '<span class=nm onclick="openRec(\''+esc(b.canon)+'\')" title="see citation records on GitHub">'+
      esc(b.canon)+'</span>'+h+ty+'</td>');
    if(r.sat!=null){
      var col = r.sat>=85?'var(--red)':r.sat>=70?'var(--amber)':'var(--green)';
      H.push('<td class="sat hs" data-b="'+esc(b.canon)+'" data-m="'+r.satMid+
        '" onmouseenter="showSat(event,this);highlightRow(this,true)" onmouseleave="hideTip();highlightRow(this,false)">'+
        '<div class=satbar><i style="width:'+Math.max(3,Math.round(r.sat))+
        '%;background:'+col+'"></i></div><span class=satnum>'+Math.round(r.sat)+'%</span></td>');
    } else { H.push('<td class=sat><span class=satnum>&mdash;</span></td>'); }
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
       'No benchmarks match. Try enabling <b>show single-citation</b> or re-adding companies.'+
       '</td></tr></tbody>'];
  }
  t.innerHTML=H.join('');
  var yl=t.querySelector('td.yl');
  document.documentElement.style.setProperty('--gutL',(yl?yl.getBoundingClientRect().width:220)+'px');
  document.getElementById('count').textContent =
    rows.length+' benchmarks × '+vm.length+' models shown'+
    (state.tail?'':' (single-citation benchmarks hidden)');
}

// model header tooltip text
DATA.models.forEach(function(m){ m.model_title=function(){ return m.display+
  (m.release_date?(' · '+m.release_date):' · date unknown')+' · '+m.company_display; }; });

var pinned=null;
function cellData(el){
  var b=el.dataset.b, m=el.dataset.m;
  var rec=DATA.benchmarks.find(function(x){return x.canon===b;});
  return {b:b, c:rec.cells[m], mm:DATA.models.find(function(x){return x.id===m;})};
}
function tipHTML(d){
  var s='<h4>'+esc(d.b)+' × '+esc(d.mm.display)+'</h4>';
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
function satHTML(el){
  var b=el.dataset.b, m=el.dataset.m;
  var rec=DATA.benchmarks.find(function(x){return x.canon===b;});
  var mm=DATA.models.find(function(x){return x.id===m;});
  var cell=rec.cells[m], best=null;
  cell.docs.forEach(function(dd){ if(dd.unit==='percent'&&dd.val!=null&&(best==null||dd.val>best.val)) best=dd; });
  var pct=best?best.val:cell.score;
  var s='<h4>'+esc(b)+' · saturation</h4>';
  s+='<div class=r>max <b>'+esc(String(Math.round(pct)))+'%</b> · '+esc(mm.display)+'</div>';
  if(best){
    var lab=DATA.wc_label[best.wc]||best.wc||'source';
    s+='<div class=r><a href="'+esc(best.url)+'" target=_blank rel=noopener>'+esc(lab)+' source ↗</a>'+
       (best.cfg?(' <span class=cl>'+esc(best.cfg)+'</span>'):'')+'</div>';
  }
  return s;
}
function pos(el){ var tip=document.getElementById('tip'); var r=el.getBoundingClientRect();
  var x=r.right+10, y=r.top; var t=tip.getBoundingClientRect();
  if(x+t.width>innerWidth) x=r.left-t.width-10; if(x<6) x=6;
  if(y+t.height>innerHeight) y=innerHeight-t.height-8; if(y<6) y=6;
  tip.style.left=x+'px'; tip.style.top=y+'px'; }
function showTip(e,el){ if(pinned) return; var tip=document.getElementById('tip');
  tip.innerHTML=tipHTML(cellData(el)); tip.style.display='block'; posMouse(e); }
function showSat(e,el){ if(pinned) return; var tip=document.getElementById('tip');
  tip.innerHTML=satHTML(el); tip.style.display='block'; pos(el); }
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

render();
</script>
</body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
