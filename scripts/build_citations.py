import json, re, pathlib
BC = pathlib.Path(__file__).resolve().parents[1]  # repo root (CI-safe)

# ---- deterministic Harbor status per canonical (curated; NO fuzzy guessing) ----
HARBOR = {  # canonical: (status, harbor_name)
 "swe-bench-verified":("confirmed","swebench-verified"),
 "swe-bench-pro":("confirmed","swebenchpro"),
 "swe-bench-multilingual":("confirmed","swebench_multilingual"),
 "gpqa-diamond":("confirmed","gpqa-diamond"),
 "arc-agi-2":("confirmed","arc_agi_2"),
 "finance-agent":("confirmed","financeagent"),
 "mmmlu":("confirmed","mmmlu"),
 "strongreject":("confirmed","strongreject"),
 "lab-bench":("needs_review","labbench"),
 "terminal-bench":("needs_review","terminal-bench"),
 "livecodebench":("needs_review","livecodebench"),
 "simpleqa":("needs_review","simpleqa"),
 "aime":("needs_review","aime"),
 "bfcl":("needs_review","bfcl"),
 "spreadsheetbench":("needs_review","spreadsheetbench-verified"),
 "cybench":("false_positive","legacy-bench"),
}
AXIS = {"agentic":set("swe-bench-verified swe-bench-pro swe-bench-multilingual swe-bench-multimodal terminal-bench frontiercode frontier-swe programbench cursorbench browsecomp deepsearchqa draco gdpval-aa mcp-atlas mcp-mark-verified osworld toolathlon automationbench vending-bench-2 finance-agent real-world-finance legal-agent-benchmark officeqa cybergym cve-bench cybench exploitbench tau2-bench bfcl livecodebench spreadsheetbench aider-polyglot webarena screenspot-pro benchcad".split()),
 "static":set("gpqa-diamond arc-agi-2 arc-agi-1 humanitys-last-exam matharena-apex aime usamo-2026 hmmt arxivmath critpt riemannbench graphwalks mmlu mmlu-pro mmmlu simpleqa healthbench healthadminbench codeforces imoanswerbench abstentionbench iheval".split()),
 "multimodal":set("mmmu mmmu-pro video-mmmu charxiv chartqapro chartmuseum gdp-pdf blueprint-bench-2 figqa".split()),
 "safety":set("wmdp lab-bench protocolqa seqqa or-bench agentharm bbq shade-arena mask petri biomysterybench proteingym biolp-bench cloning-scenarios makemesay biotier cybersec-eval harmbench deceptionbench propensitybench impossiblebench aa-omniscience spatialbench singlecellbench minimal-linuxbench troubleshootingbench paperbench creative-writing-v3 secure-bio-evals".split())}
def axis_of(c):
    for a,s in AXIS.items():
        if c in s: return a
    return "agentic"

# ---- deterministic normalization: raw token -> canonical slug ----
def canon(raw):
    r=raw.strip().lower()
    m={"swe-bench verified":"swe-bench-verified","swe-bench":"swe-bench-verified","swe-bench pro":"swe-bench-pro",
    "swe-bench multilingual":"swe-bench-multilingual","swe-bench multimodal":"swe-bench-multimodal","frontier swe":"frontier-swe",
    "terminal-bench":"terminal-bench","terminal-bench 2.1":"terminal-bench","gpqa":"gpqa-diamond","gpqa diamond":"gpqa-diamond",
    "hle":"humanitys-last-exam","humanity":"humanitys-last-exam","humanity's last exam":"humanitys-last-exam",
    "arc-agi":"arc-agi-2","arc-agi-2":"arc-agi-2","matharena":"matharena-apex","matharena apex":"matharena-apex",
    "gdpval":"gdpval-aa","gdpval-aa":"gdpval-aa","gdp.pdf":"gdp-pdf","mcp atlas":"mcp-atlas","mcp-atlas":"mcp-atlas",
    "browsecomp":"browsecomp","osworld":"osworld","osworld-verified":"osworld","vending bench":"vending-bench-2","vending-bench":"vending-bench-2",
    "vending-bench 2":"vending-bench-2","lab-bench":"lab-bench","lab-bench figqa":"lab-bench","labbench":"lab-bench",
    "figqa":"figqa","tau2":"tau2-bench","τ2":"tau2-bench","tau2-bench":"tau2-bench","mmmu":"mmmu","mmmu-pro":"mmmu-pro",
    "mmlu":"mmlu","mmlu-pro":"mmlu-pro","mmmlu":"mmmlu","video-mmmu":"video-mmmu","simpleqa":"simpleqa",
    "aime":"aime","aime 2025":"aime","hmmt":"hmmt","usamo":"usamo-2026","usamo 2026":"usamo-2026","charxiv":"charxiv",
    "cybench":"cybench","cyber bench":"cybench","cyberbench":"cybench","cyberseceval":"cybersec-eval",
    "cybergym":"cybergym","cve-bench":"cve-bench","cyscenariobench":"cyscenariobench","exploitbench":"exploitbench",
    "wmdp":"wmdp","protocolqa":"protocolqa","seqqa":"seqqa","or-bench":"or-bench","agentharm":"agentharm","bbq":"bbq",
    "shade":"shade-arena","shade-arena":"shade-arena","mask":"mask","petri":"petri","harmbench":"harmbench",
    "deceptionbench":"deceptionbench","propensitybench":"propensitybench","impossiblebench":"impossiblebench",
    "iheval":"iheval","abstentionbench":"abstentionbench","biotier":"biotier","biolp":"biolp-bench","biolp-bench":"biolp-bench",
    "cloning":"cloning-scenarios","cloningscenarios":"cloning-scenarios","makemesay":"makemesay","strongreject":"strongreject",
    "healthbench":"healthbench","healthadminbench":"healthadminbench","biomysterybench":"biomysterybench","proteingym":"proteingym",
    "spatialbench":"spatialbench","singlecellbench":"singlecellbench","minimal-linuxbench":"minimal-linuxbench",
    "frontiercode":"frontiercode","programbench":"programbench","cursorbench":"cursorbench","riemannbench":"riemannbench",
    "arxivmath":"arxivmath","critpt":"critpt","graphwalks":"graphwalks","deepsearchqa":"deepsearchqa","draco":"draco",
    "blueprint-bench":"blueprint-bench-2","blueprint-bench 2":"blueprint-bench-2","benchcad":"benchcad","chartqapro":"chartqapro",
    "chartmuseum":"chartmuseum","screenspot":"screenspot-pro","screenspot-pro":"screenspot-pro","officeqa":"officeqa",
    "finance agent":"finance-agent","financeagent":"finance-agent","real-world finance":"real-world-finance",
    "legal agent":"legal-agent-benchmark","legal agent benchmark":"legal-agent-benchmark","toolathlon":"toolathlon",
    "automationbench":"automationbench","mrcr":"mrcr","webarena":"webarena","aider":"aider-polyglot","codeforces":"codeforces",
    "livecodebench":"livecodebench","imoanswerbench":"imoanswerbench","paperbench":"paperbench","troubleshootingbench":"troubleshootingbench",
    "aa-omniscience":"aa-omniscience","creative writing":"creative-writing-v3"}
    return m.get(r)  # None => unmatched -> needs_review

DROP={"terminus","vals","securebio","ledidi","nucleobench","opqa","linuxbench","linuxarena","spatial"}

# ---- per-doc benchmark inventories (from detector, cleaned) ----
DOCS={
 "fable":dict(lab="anthropic",model="Claude Fable 5 / Mythos 5",dt="system_card",date="2026-06-09",
   url="https://www-cdn.anthropic.com/d00db56fa754a1b115b6dd7cb2e3c342ee809620.pdf",
   b=["SWE-bench Verified","SWE-bench Pro","SWE-bench Multilingual","SWE-bench Multimodal","Terminal-Bench 2.1","FrontierCode","Frontier SWE","ProgramBench","CursorBench","GPQA Diamond","RiemannBench","USAMO 2026","ArxivMath","CritPt","GraphWalks","HLE","BrowseComp","DeepSearchQA","DRACO","GDP.pdf","Blueprint-Bench 2","OSWorld-Verified","BenchCAD","ChartQAPro","ChartMuseum","LAB-Bench FigQA","CharXiv","ScreenSpot-Pro","OfficeQA","Finance Agent","Real-World Finance","Legal Agent Benchmark","MCP Atlas","Vending-Bench 2","GDPval-AA","Toolathlon","AutomationBench","HealthBench","HealthAdminBench","BioMysteryBench","CyberGym","Cybench","ExploitBench","WMDP","MMLU-Pro","SHADE","Petri","MASK","BBQ","AA-Omniscience","SimpleQA","MathArena","AIME","MMLU","ProteinGym","SpatialBench","SingleCellBench","Minimal-LinuxBench","FigQA"]),
 "opus46":dict(lab="anthropic",model="Claude Opus 4.6",dt="system_card",date="2026-02-05",
   url="https://www-cdn.anthropic.com/0dd865075ad3132672ee0ab40b05a53f14cf5288.pdf",
   b=["SWE-bench Verified","SWE-bench Multilingual","Terminal-Bench","ARC-AGI","GPQA","AIME","MMLU","MMMLU","MMMU","MMMU-Pro","MRCR","BrowseComp","HLE","DeepSearchQA","GDPval-AA","MCP-Atlas","OSWorld","Vending-Bench","Finance Agent","Real-World Finance","WebArena","CharXiv","LAB-Bench","FigQA","ProtocolQA","Cybench","CyberGym","BioMysteryBench","SHADE","Petri","BBQ","AA-Omniscience","GraphWalks","Cloning","tau2"]),
 "sonnet5":dict(lab="anthropic",model="Claude Sonnet 5",dt="system_card",date="2026-06-30",
   url="https://www-cdn.anthropic.com/480e0bb54327b9622282e9c39a83a4f490ed377e/Claude%20Sonnet%205%20System%20Card.pdf",
   b=["SWE-bench Verified","SWE-bench Pro","SWE-bench Multilingual","Terminal-Bench","FrontierCode","ProgramBench","CursorBench","HLE","BrowseComp","GDP.pdf","OSWorld-Verified","CharXiv","ChartMuseum","BenchCAD","OfficeQA","Toolathlon","AutomationBench","GDPval-AA","MathArena","AIME","USAMO","ArxivMath","HealthBench","Real-World Finance","Legal Agent Benchmark","Minimal-LinuxBench","ExploitBench","CyberGym","BioMysteryBench","SHADE","MASK","BBQ","AA-Omniscience","ProteinGym","MMLU"]),
 "deepseek":dict(lab="deepseek",model="DeepSeek-V3.2",dt="system_card",date="2025-12-01",
   url="https://arxiv.org/abs/2512.02556",
   b=["AIME","HMMT","GPQA","HLE","LiveCodeBench","Codeforces","Aider","SWE-bench Verified","Terminal-Bench","tau2","BrowseComp","MMLU-Pro","MMLU","IMOAnswerBench"]),
 "gpt5":dict(lab="openai",model="GPT-5",dt="system_card",date="2025-08-13",
   url="https://cdn.openai.com/gpt-5-system-card.pdf",
   b=["SWE-bench Verified","HealthBench","SimpleQA","BBQ","CharXiv","PaperBench","ProtocolQA","AbstentionBench","MMLU","StrongReject","TroubleshootingBench"]),
 "gpt52":dict(lab="openai",model="GPT-5.2",dt="system_card",date="2025-12-11",
   url="https://cdn.openai.com/pdf/3a4153c8-c748-4b71-8e31-aecbde944f8d/oai_5_2_system-card.pdf",
   b=["CVE-Bench","CharXiv","HealthBench","MMLU","PaperBench","ProtocolQA","StrongReject","TroubleshootingBench"]),
 "muse":dict(lab="meta",model="Muse Spark",dt="system_card",date="2026-04-08",
   url="https://ai.meta.com/static-resource/muse-spark-safety-and-preparedness-report/",
   b=["SWE-Bench","Terminal-Bench","GPQA","HLE","LiveCodeBench","CharXiv","LAB-Bench","WMDP","Cybench","CyScenarioBench","CyberGym","CyberSecEval","AgentHarm","OR-Bench","StrongReject","Harmbench","MASK","SHADE","Petri","DeceptionBench","PropensityBench","ImpossibleBench","IHEval","AbstentionBench","BioTIER","SimpleQA","MMLU","ProtocolQA","SeqQA","Creative Writing"]),
 "grok41":dict(lab="xai",model="Grok 4.1",dt="model_card",date="2025-11-17",
   url="https://data.x.ai/2025-11-17-grok-4-1-model-card.pdf",
   b=["BioLP","ProtocolQA","FigQA","CloningScenarios","Cybench","WMDP","AgentHarm","MASK","MakeMeSay"]),
 # Gemini 3 Pro model card table is IMAGE-BASED (0 text tokens) -> numbers taken from PRIMARY blog
 "gemini3":dict(lab="google_deepmind",model="Gemini 3 Pro",dt="blog_headliner",date="2025-11-18",
   url="https://blog.google/products-and-platforms/products/gemini/gemini-3/",
   b=["GPQA Diamond","HLE","ARC-AGI-2","MathArena","MMMU-Pro","Video-MMMU","SimpleQA","AIME","Vending-Bench 2","ScreenSpot-Pro","LiveCodeBench"]),
}
# ---- scores actually read from tables/blogs (doc, canonical) -> (value, unit, model_config) ----
SCORES={
 ("fable","swe-bench-verified"):(95,"percent","Fable 5"),("fable","swe-bench-pro"):(80,"percent","Fable 5"),
 ("fable","terminal-bench"):(84.3,"percent","Fable 5"),("fable","frontiercode"):(29.3,"percent","Fable 5"),
 ("fable","gdp-pdf"):(29.8,"percent","Fable 5"),("fable","osworld"):(85.0,"percent","Fable 5"),
 ("fable","gdpval-aa"):(1932,"elo","Fable 5"),("fable","officeqa"):(57.9,"percent","Fable 5"),
 ("fable","automationbench"):(17.4,"percent","Fable 5"),("fable","blueprint-bench-2"):(38.6,"percent","Fable 5"),
 ("fable","humanitys-last-exam"):(59.0,"percent","Mythos 5 (no tools)"),("fable","healthbench"):(62.7,"percent","Mythos 5"),
 ("fable","critpt"):(28.6,"percent","Mythos 5"),
 ("gemini3","gpqa-diamond"):(91.9,"percent",None),("gemini3","humanitys-last-exam"):(37.5,"percent","no tools"),
 ("gemini3","matharena-apex"):(23.4,"percent",None),("gemini3","mmmu-pro"):(81.0,"percent",None),
 ("gemini3","video-mmmu"):(87.6,"percent",None),("gemini3","simpleqa"):(72.1,"percent","Verified"),
 ("gemini3","arc-agi-2"):(31.1,"percent",None),
 ("gpt5","healthbench"):(46.2,"percent","gpt-5-thinking, Hard"),
 ("deepseek","tau2-bench"):(96.2,"percent","Telecom"),("deepseek","terminal-bench"):(46.4,"percent","Claude Code harness"),
 ("muse","terminal-bench"):(59.0,"percent","Thinking"),
}
METHOD={  # (doc, canonical) -> methodology note
 ("fable","swe-bench-verified"):"standard config, thinking blocks incl.; Mythos 5 95.5",
 ("fable","terminal-bench"):"Harbor maintains TB 2.1 leaderboard; competitor harnesses Codex/Gemini CLI",
 ("deepseek","terminal-bench"):"thinking-mode incompatible w/ Terminus; Terminus non-thinking 39.3",
 ("deepseek","tau2-bench"):"model itself as user agent; Airline 63.8 / Retail 81.1",
 ("muse","cybench"):"Anthropic 37/40 vs Muse full 40 - not comparable",
}
ISSUE={"cybench":4,"terminal-bench":4,"lab-bench":4,"osworld":4,"simpleqa":4,"aime":4,"livecodebench":4,"bfcl":4,"spreadsheetbench":4}

R=[]; unmatched=set()
for did,d in DOCS.items():
    for raw in d["b"]:
        if raw.strip().lower() in DROP: continue
        c=canon(raw)
        if not c:
            unmatched.add(raw)
        cc=c
        hs,hn=HARBOR.get(cc,("not_in_harbor",None)) if cc else ("not_in_harbor",None)
        on = hs=="confirmed"
        val,unit,cfg=SCORES.get((did,cc),(None,None,None))
        # needs_review = genuine HUMAN decision only (unmatched / harbor collision / config-dependent).
        # A missing score is a to-extract state -> score_pending, NOT needs_review.
        nr=False; reason=None; issue=None
        if not cc: nr=True; reason="unmatched benchmark name - register in aliases"; issue=4
        elif hs=="false_positive": nr=True; reason="Harbor auto-match is false positive"; issue=4
        elif hs=="needs_review": nr=True; reason="Harbor variant/version unconfirmed"; issue=ISSUE.get(cc,4)
        score_pending = val is None
        if score_pending and not issue: issue=6
        meth=[METHOD[(did,cc)]] if (did,cc) in METHOD else []
        R.append({"benchmark_canonical":cc,"benchmark_raw":raw,
          "source_doc":{"lab":d["lab"],"model":d["model"],"doc_type":d["dt"],"url":d["url"],"pub_date":d["date"],"primary":True},
          "citing_lab":d["lab"],"citing_model":d["model"],
          "prominence":{"type":"table_row"},
          "reported":{"value":val,"unit":unit,"model_config":cfg},
          "axis":axis_of(cc) if cc else "agentic","on_harbor":on,"harbor_status":hs,"harbor_name":hn,
          "methodology_deviations":meth,"score_pending":score_pending,
          "needs_review":nr,"review_reason":reason,"review_issue":issue})

with open(BC/"data/citations.jsonl","w") as fh:
    for r in R: fh.write(json.dumps(r,ensure_ascii=False)+"\n")
print("TOTAL citation records:", len(R))
print("distinct benchmarks   :", len({r['benchmark_canonical'] for r in R if r['benchmark_canonical']}))
print("distinct docs         :", len(DOCS))
print("on_harbor=True        :", sum(1 for r in R if r['on_harbor']))
print("needs_review          :", sum(1 for r in R if r['needs_review']))
print("with a score          :", sum(1 for r in R if r['reported']['value'] is not None))
print("unmatched raw names   :", sorted(unmatched))
