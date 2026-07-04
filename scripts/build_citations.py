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
# ---- TWO orthogonal axes ----
# TYPE = how it's run (static Q&A/exam vs agentic tool/environment task). Harbor prefers agentic.
# DOMAIN = subject matter. Do NOT conflate the two.
AGENTIC = set("swe-bench-verified swe-bench-pro swe-bench-multilingual swe-bench-multimodal terminal-bench frontiercode frontier-swe programbench cursorbench aider-polyglot expert-swe spreadsheetbench minimal-linuxbench vibench osworld webarena screenspot-pro online-mind2web automationbench toolathlon mcp-atlas mcp-mark-verified bfcl tau2-bench vending-bench-2 browsecomp deepsearchqa draco gdpval-aa finance-agent real-world-finance legal-agent-benchmark officeqa apex-agents benchcad cybergym cve-bench cybench cyscenariobench exploitbench exploitgym paperbench mle-bench agentharm shade-arena petri makemesay impossiblebench genebench bixbench".split())
def type_of(c):
    return "agentic" if c in AGENTIC else "static"

DOMAIN = {
 "coding": "swe-bench-verified swe-bench-pro swe-bench-multilingual swe-bench-multimodal terminal-bench frontiercode frontier-swe programbench cursorbench vibench livecodebench aider-polyglot codeforces ojbench expert-swe spreadsheetbench minimal-linuxbench".split(),
 "math": "aime hmmt matharena-apex usamo-2026 arxivmath riemannbench imoanswerbench frontiermath".split(),
 "science": "gpqa-diamond critpt scicode proteingym biomysterybench biopipelinebench lab-bench protocolqa seqqa biolp-bench cloning-scenarios singlecellbench spatialbench genebench bixbench biotier secure-bio-evals paperbench troubleshootingbench".split(),
 "knowledge": "mmlu mmlu-pro mmmlu humanitys-last-exam simpleqa arc-agi-1 arc-agi-2 graphwalks mrcr aa-omniscience iheval abstentionbench browsecomp deepsearchqa draco creative-writing-v3".split(),
 "health": "healthbench healthadminbench".split(),
 "safety": "wmdp agentharm or-bench strongreject mask shade-arena petri bbq deceptionbench propensitybench impossiblebench makemesay harmbench".split(),
 "cyber": "cybench cybergym cve-bench cyscenariobench cybersec-eval exploitbench exploitgym".split(),
 "computer-use": "osworld webarena screenspot-pro online-mind2web automationbench toolathlon mcp-atlas mcp-mark-verified bfcl tau2-bench vending-bench-2".split(),
 "professional": "gdpval-aa finance-agent real-world-finance legal-agent-benchmark officeqa apex-agents benchcad".split(),
 "multimodal": "mmmu mmmu-pro video-mmmu charxiv chartqapro chartmuseum gdp-pdf blueprint-bench-2 figqa mathvision babyvision zerobench longvideobench worldvqa omnidocbench".split(),
}
DOM = {c: d for d, cs in DOMAIN.items() for c in cs}
UNCLASSIFIED = set()
def domain_of(c):
    d = DOM.get(c)
    if d is None:
        UNCLASSIFIED.add(c)
        return "knowledge"  # safe default; unclassified canonicals are surfaced for taxonomy review
    return d

# ---- deterministic normalization: raw token -> canonical slug ----
EXTRA = {}  # exact aliases registered during forward runs (deterministic lookup, never fuzzy)
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
    "figqa":"figqa","tau2":"tau2-bench","\u03c42":"tau2-bench","tau2-bench":"tau2-bench","mmmu":"mmmu","mmmu-pro":"mmmu-pro",
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
    return m.get(r) or EXTRA.get(r)  # None => unmatched -> needs_review

DROP={"terminus","vals","securebio","ledidi","nucleobench","opqa","linuxbench","linuxarena","spatial","vendingbench"}

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
   url="https://blog.google/products-and-platforms/products/gemini/gemini-3/",prom="headline",
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

# ============================================================================
# FORWARD RUN 2026-07-03: promoted in-window backlog (discovered by crawling each
# lab's source_index_urls, diffed vs the 9 backfill docs + sources/manifest.yaml).
# Inventories are verbatim benchmark mentions read from each doc; scores are read
# from the CITING MODEL's own column/prose only. Unreadable (image/JS/gated) docs
# are FLAGGED (needs_review), never guessed. New benchmark names not in the alias
# registry are left unmatched -> needs_review (never silently mapped).
# ============================================================================
EXTRA.update({
 "arc-agi-1":"arc-agi-1","arc-agi-1 (verified)":"arc-agi-1",
 "spreadsheetbench":"spreadsheetbench","spreadsheetbench-v1":"spreadsheetbench",
 "imo-answerbench":"imoanswerbench","gpqa-diamond":"gpqa-diamond","webarena-verified":"webarena",
 "bfcl":"bfcl","vibench":"vibench",
})

NEWDOCS={
 # ---------- Anthropic (system cards via transparency hub) ----------
 "opus47":dict(lab="anthropic",model="Claude Opus 4.7",dt="system_card",date="2026-04-16",
   url="https://cdn.sanity.io/files/4zrzovbb/website/037f06850df7fbe871e206dad004c3db5fd50340.pdf",
   b=["SWE-bench Verified","Terminal-Bench","GPQA","AIME","ARC-AGI","MMLU","BrowseComp","HLE","DeepSearchQA","GDPval-AA","OSWorld","Vending-Bench","CharXiv","LAB-Bench","FigQA","MASK","SHADE","Petri","Cybench","CyberGym","BioMysteryBench","Minimal-LinuxBench","SimpleQA","MathArena","USAMO","BioPipelineBench"]),
 "mythospreview":dict(lab="anthropic",model="Claude Mythos Preview",dt="system_card",date="2026-04-07",
   url="https://www-cdn.anthropic.com/53566bf5440a10affd749724787c8913a2ae0841.pdf",
   b=["SWE-bench Verified","Terminal-Bench","GPQA","AIME","MMLU","MMMU","MMMU-Pro","BrowseComp","HLE","CharXiv","LAB-Bench","FigQA","MASK","SHADE","Petri","Cybench","CyberGym","OSWorld","Vending-Bench","SimpleQA","MathArena","USAMO","Minimal-LinuxBench"]),
 "sonnet46":dict(lab="anthropic",model="Claude Sonnet 4.6",dt="system_card",date="2026-02-17",
   url="https://www-cdn.anthropic.com/78073f739564e986ff3e28522761a7a0b4484f84.pdf",
   b=["SWE-bench Verified","SWE-bench Multilingual","Terminal-Bench","GPQA","AIME","ARC-AGI","MMLU","MMMU","MMMU-Pro","BrowseComp","HLE","DeepSearchQA","GDPval-AA","OSWorld","Vending-Bench","CharXiv","LAB-Bench","FigQA","Petri","SHADE","Cybench","CyberGym","WebArena"]),
 "opus45":dict(lab="anthropic",model="Claude Opus 4.5",dt="system_card",date="2025-11-24",
   url="https://assets.anthropic.com/m/64823ba7485345a7/Claude-Opus-4-5-System-Card.pdf",
   b=["SWE-bench Verified","Terminal-Bench","GPQA","AIME","ARC-AGI","MMLU","MMMU","BrowseComp","OSWorld","Vending-Bench","CharXiv","LAB-Bench","FigQA","ProtocolQA","SeqQA","Petri","SHADE","Cybench","CyberGym","WebArena","SimpleQA","SpreadSheetBench"]),
 "haiku45":dict(lab="anthropic",model="Claude Haiku 4.5",dt="system_card",date=None,
   url="https://assets.anthropic.com/m/99128ddd009bdcb/original/Claude-Haiku-4-5-System-Card.pdf",
   b=["SWE-bench Verified","Cybench","LAB-Bench","ProtocolQA","Petri","SHADE"]),
 "sonnet45":dict(lab="anthropic",model="Claude Sonnet 4.5",dt="system_card",date="2025-10-10",
   url="https://assets.anthropic.com/m/12f214efcc2f457a/original/Claude-Sonnet-4-5-System-Card.pdf",
   b=["SWE-bench Verified","Cybench","CyberGym","LAB-Bench","ProtocolQA","SeqQA","FigQA","SHADE"]),
 # ---------- Anthropic headline release blog (SEPARATE doc from the 50+-benchmark system card;
 #            prose headlines only a handful -> those get prominence=headline) ----------
 "fableblog":dict(lab="anthropic",model="Claude Fable 5 / Mythos 5",dt="blog_headliner",date="2026-06-09",
   url="https://www.anthropic.com/news/claude-fable-5-mythos-5",prom="headline",
   head=["FrontierCode","CyberGym","CyScenarioBench","CursorBench","ViBench","FrontierBench"],
   b=["FrontierCode","CyberGym","CyScenarioBench","CursorBench","ViBench","FrontierBench"]),
 # ---------- OpenAI ----------
 "gpt55":dict(lab="openai",model="GPT-5.5",dt="blog_headliner",date="2026-04-23",
   url="https://openai.com/index/introducing-gpt-5-5/",
   head=["Terminal-Bench","SWE-bench Pro","GDPval (wins or ties)","OSWorld-Verified","Toolathlon","BrowseComp","CyberGym","tau2-bench","Finance Agent","GeneBench"],
   b=["Terminal-Bench","SWE-bench Pro","GDPval (wins or ties)","OSWorld-Verified","Toolathlon","BrowseComp","CyberGym","Finance Agent","OfficeQA","MMMU-Pro","MCP Atlas","tau2-bench","GPQA Diamond","HLE","ARC-AGI","ARC-AGI-1","Graphwalks","MRCR","Expert-SWE","FrontierMath","GeneBench","BixBench","SciCode","AA-LCR","AA-Omniscience","CritPt","IFBench"]),
 "gpt54":dict(lab="openai",model="GPT-5.4",dt="blog_headliner",date="2026-03-05",
   url="https://openai.com/index/introducing-gpt-5-4/",
   head=["GDPval (wins or ties)","SWE-bench Pro","OSWorld-Verified","Toolathlon","BrowseComp","WebArena-Verified"],
   b=["GDPval (wins or ties)","SWE-bench Pro","OSWorld-Verified","Toolathlon","BrowseComp","Terminal-Bench","WebArena-Verified","MMMU-Pro","GPQA Diamond","HLE","tau2-bench","MCP Atlas","ARC-AGI","ARC-AGI-1","Finance Agent","OfficeQA","Graphwalks","MRCR","OmniDocBench","Online-Mind2Web","FrontierMath","APEX-Agents","BigLaw Bench","Frontier Science Research"]),
 "gpt56card":dict(lab="openai",model="GPT-5.6 Sol",dt="system_card",date="2026-06-26",
   url="https://deploymentsafety.openai.com/gpt-5-6-preview/gpt-5-6-preview.pdf",
   b=["HealthBench","CVE-Bench","ProtocolQA","TroubleshootingBench","GPQA","MMLU-Pro","HLE","BFCL","SWE-bench Verified","MLE-Bench"]),
 "gpt56sol":dict(lab="openai",model="GPT-5.6 Sol",dt="blog_headliner",date="2026-06-26",
   url="https://openai.com/index/previewing-gpt-5-6-sol/",prom="headline",
   b=["Terminal-Bench","GeneBench","ExploitBench","ExploitGym"]),
 # ---------- Google DeepMind ----------
 "gemini35":dict(lab="google_deepmind",model="Gemini 3.5 Pro",dt="blog_headliner",date=None,
   url="https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-3-5/",prom="headline",
   b=["CharXiv","GDPval-AA","Terminal-Bench"]),
 "gemini31pro":dict(lab="google_deepmind",model="Gemini 3.1 Pro",dt="model_card",date="2026-02-19",
   url="https://deepmind.google/models/model-cards/gemini-3-1-pro",
   b=["HLE","ARC-AGI-2","GPQA Diamond","Terminal-Bench","SWE-bench Verified","SWE-bench Pro","LiveCodeBench","SciCode","APEX-Agents","GDPval-AA","tau2-bench","MCP Atlas","BrowseComp","MMMU-Pro","MMMLU","MRCR"]),
 "gemini35flash":dict(lab="google_deepmind",model="Gemini 3.5 Flash",dt="model_card",date="2026-05-19",
   url="https://deepmind.google/models/model-cards/gemini-3-5-flash",
   b=["ARC-AGI","CharXiv","GDPval-AA","MMMU","MMMU-Pro","OSWorld","Toolathlon"]),
 # ---------- DeepSeek ----------
 "dsv4":dict(lab="deepseek",model="DeepSeek-V4-Pro",dt="system_card",date=None,
   url="https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro",
   b=["GPQA Diamond","HLE","LiveCodeBench","Codeforces","HMMT","Terminal-Bench","BrowseComp","AIME","SimpleQA","Toolathlon","IMOAnswerBench","MMLU","MMLU-Pro","GDPval-AA","SuperGPQA","Chinese-SimpleQA","CorpusQA"]),
 # ---------- Moonshot ----------
 "k26":dict(lab="moonshot",model="Kimi K2.6",dt="model_card",date="2026-04-20",
   url="https://www.kimi.com/blog/kimi-k2-6",
   b=["SWE-bench Verified","SWE-bench Multilingual","SWE-bench Pro","Terminal-Bench","GPQA","AIME","HMMT","HLE","BrowseComp","LiveCodeBench","OSWorld","Toolathlon","MMMU-Pro","CharXiv","DeepSearchQA","SciCode","IMO-AnswerBench","MMLU","MMMU","APEX-Agents","MCPMark","WideSearch","OJBench","MathVision","BabyVision","ZeroBench"]),
 "k25":dict(lab="moonshot",model="Kimi K2.5",dt="model_card",date="2026-01-27",
   url="https://www.kimi.com/blog/kimi-k2-5",
   b=["AIME","BrowseComp","CharXiv","CyberGym","DeepSearchQA","GPQA","HLE","HMMT","LiveCodeBench","MMLU","MMLU-Pro","MMMU","MMMU-Pro","OSWorld","Terminal-Bench","IMO-AnswerBench","LongVideoBench","OmniDocBench","WorldVQA","ZeroBench"]),
 # ---------- Z.ai ----------
 "glm47":dict(lab="zai",model="GLM-4.7",dt="model_card",date="2025-12-22",
   url="https://huggingface.co/zai-org/GLM-4.7",
   b=["GPQA","HLE","AIME","HMMT","LiveCodeBench","SWE-bench Verified","SWE-bench Multilingual","Terminal-Bench","BrowseComp","BrowseComp-Zh"]),
 "glm5":dict(lab="zai",model="GLM-5",dt="model_card",date="2026-02-12",
   url="https://huggingface.co/zai-org/GLM-5",
   b=["HLE","AIME","GPQA","SWE-bench Verified","SWE-bench Multilingual","Terminal-Bench","CyberGym","BrowseComp","HMMT","BrowseComp-Zh"]),
 "glm51":dict(lab="zai",model="GLM-5.1",dt="model_card",date="2026-04-07",
   url="https://huggingface.co/zai-org/GLM-5.1",
   b=["HLE","AIME","GPQA","SWE-bench Pro","Terminal-Bench","CyberGym","BrowseComp","HMMT"]),
 # ---------- Unreadable / gated / image-only -> FLAGGED for human extraction (issue #9) ----------
 "gemini3flash":dict(lab="google_deepmind",model="Gemini 3 Flash",dt="model_card",date="2025-12-17",
   url="https://deepmind.google/models/model-cards/gemini-3-flash/",b=["__UNREADABLE__"],
   reason="Gemini 3 Flash model card benchmark table is image-based (no text-extractable scores) - OCR/blog needed",issue=9),
 "k2think":dict(lab="moonshot",model="Kimi K2 Thinking",dt="model_card",date="2025-11-06",
   url="https://www.kimi.com/blog/kimi-k2-thinking",b=["__UNREADABLE__"],
   reason="Kimi K2 Thinking blog is JS-rendered; benchmark scores not in served HTML (curl) - needs headless render/human extraction",issue=9),
 "k27code":dict(lab="moonshot",model="Kimi K2.7-Code",dt="model_card",date=None,
   url="https://www.kimi.com/resources/kimi-k2-7-code",b=["__UNREADABLE__"],
   reason="Kimi K2.7-Code page is JS-rendered; benchmark scores not in served HTML (curl) - needs headless render/human extraction",issue=9),
 "glm46":dict(lab="zai",model="GLM-4.6",dt="model_card",date="2025-09-30",
   url="https://huggingface.co/zai-org/GLM-4.6",b=["__UNREADABLE__"],
   reason="GLM-4.6 HF README has no text-extractable benchmark table; scores live on z.ai blog (not archived) - human extraction needed",issue=9),
 "mistral3":dict(lab="mistral",model="Mistral Large 3",dt="model_card",date="2025-12-02",
   url="https://huggingface.co/mistralai/Mistral-Large-3-675B-Instruct-2512",b=["__UNREADABLE__"],
   reason="Mistral Large 3 card benchmarks are chart images only (issue #1); only AIME appears as text",issue=1),
 "qwen3max":dict(lab="qwen",model="Qwen3-Max",dt="blog_headliner",date=None,
   url="https://huggingface.co/Qwen/Qwen3-Max",b=["__UNREADABLE__"],
   reason="Qwen3-Max primary source not retrievable: HF repo gated (401) and qwenlm blog 404; Qwen source_index_urls need updating (feed relocated to qwen.ai)",issue=9),
}
DOCS.update(NEWDOCS)

NEWSCORES={
 ("opus47","browsecomp"):(79.3,"percent","Opus 4.7"),
 ("sonnet46","swe-bench-verified"):(79.6,"percent","Sonnet 4.6"),("sonnet46","swe-bench-multilingual"):(75.9,"percent","Sonnet 4.6"),
 ("opus45","osworld"):(66.26,"percent","Opus 4.5 (P@1; avg@5)"),
 # GPT-5.5 (own column, xhigh)
 ("gpt55","terminal-bench"):(82.7,"percent","GPT-5.5 (TB 2.0)"),("gpt55","swe-bench-pro"):(58.6,"percent","GPT-5.5 (Public)"),
 ("gpt55","osworld"):(78.7,"percent","GPT-5.5"),("gpt55","toolathlon"):(55.6,"percent","GPT-5.5"),
 ("gpt55","browsecomp"):(84.4,"percent","GPT-5.5"),("gpt55","cybergym"):(81.8,"percent","GPT-5.5"),
 ("gpt55","finance-agent"):(60.0,"percent","GPT-5.5 (FinanceAgent v1.1)"),("gpt55","officeqa"):(54.1,"percent","GPT-5.5 (OfficeQA Pro)"),
 ("gpt55","mmmu-pro"):(81.2,"percent","GPT-5.5 (no tools)"),("gpt55","mcp-atlas"):(75.3,"percent","GPT-5.5 (Scale Apr-2026)"),
 ("gpt55","tau2-bench"):(98.0,"percent","GPT-5.5 Telecom (original prompts)"),("gpt55","gpqa-diamond"):(93.6,"percent","GPT-5.5"),
 ("gpt55","humanitys-last-exam"):(41.4,"percent","GPT-5.5 (no tools)"),("gpt55","arc-agi-2"):(85.0,"percent","GPT-5.5 (Verified)"),
 ("gpt55","arc-agi-1"):(95.0,"percent","GPT-5.5 (Verified)"),
 # GPT-5.4 (own column, xhigh)
 ("gpt54","swe-bench-pro"):(57.7,"percent","GPT-5.4 (Public)"),("gpt54","osworld"):(75.0,"percent","GPT-5.4"),
 ("gpt54","toolathlon"):(54.6,"percent","GPT-5.4"),("gpt54","browsecomp"):(82.7,"percent","GPT-5.4"),
 ("gpt54","terminal-bench"):(75.1,"percent","GPT-5.4 (TB 2.0)"),("gpt54","webarena"):(67.3,"percent","GPT-5.4 (WebArena-Verified)"),
 ("gpt54","mmmu-pro"):(81.2,"percent","GPT-5.4 (no tools)"),("gpt54","gpqa-diamond"):(92.8,"percent","GPT-5.4"),
 ("gpt54","humanitys-last-exam"):(39.8,"percent","GPT-5.4 (no tools)"),("gpt54","tau2-bench"):(98.9,"percent","GPT-5.4 Telecom"),
 ("gpt54","mcp-atlas"):(67.2,"percent","GPT-5.4"),("gpt54","arc-agi-2"):(73.3,"percent","GPT-5.4 (Verified)"),
 ("gpt54","arc-agi-1"):(93.7,"percent","GPT-5.4 (Verified)"),("gpt54","finance-agent"):(56.0,"percent","GPT-5.4 (v1.1)"),
 ("gpt54","officeqa"):(68.1,"percent","GPT-5.4"),
 # GPT-5.6 Sol system card (length-adjusted HealthBench)
 ("gpt56card","healthbench"):(60.5,"percent","GPT-5.6 Sol - HealthBench Professional, length-adjusted"),
 # Gemini 3.1 Pro (own column, Thinking High)
 ("gemini31pro","humanitys-last-exam"):(44.4,"percent","Gemini 3.1 Pro (no tools; 51.4 Search+Code)"),
 ("gemini31pro","arc-agi-2"):(77.1,"percent","Gemini 3.1 Pro (ARC Prize Verified)"),
 ("gemini31pro","gpqa-diamond"):(94.3,"percent","Gemini 3.1 Pro (no tools)"),
 ("gemini31pro","terminal-bench"):(68.5,"percent","Gemini 3.1 Pro (TB 2.0, Terminus-2)"),
 ("gemini31pro","swe-bench-verified"):(80.6,"percent","Gemini 3.1 Pro (single attempt)"),
 ("gemini31pro","swe-bench-pro"):(54.2,"percent","Gemini 3.1 Pro (Public)"),
 ("gemini31pro","livecodebench"):(2887,"elo","Gemini 3.1 Pro (LiveCodeBench Pro)"),
 ("gemini31pro","gdpval-aa"):(1317,"elo","Gemini 3.1 Pro"),
 ("gemini31pro","tau2-bench"):(99.3,"percent","Gemini 3.1 Pro Telecom (90.8 Retail)"),
 ("gemini31pro","mcp-atlas"):(69.2,"percent","Gemini 3.1 Pro"),("gemini31pro","browsecomp"):(85.9,"percent","Gemini 3.1 Pro"),
 ("gemini31pro","mmmu-pro"):(80.5,"percent","Gemini 3.1 Pro (no tools)"),("gemini31pro","mmmlu"):(92.6,"percent","Gemini 3.1 Pro"),
 ("gemini31pro","mrcr"):(84.9,"percent","Gemini 3.1 Pro (v2 8-needle 128k avg)"),
 # DeepSeek-V4-Pro (Max reasoning effort)
 ("dsv4","gpqa-diamond"):(90.1,"percent","DeepSeek-V4-Pro-Max"),("dsv4","humanitys-last-exam"):(37.7,"percent","DeepSeek-V4-Pro-Max (48.2 w/ tools)"),
 ("dsv4","livecodebench"):(93.5,"percent","DeepSeek-V4-Pro-Max"),("dsv4","codeforces"):(3206,"rank","DeepSeek-V4-Pro-Max (rating)"),
 ("dsv4","hmmt"):(95.2,"percent","DeepSeek-V4-Pro-Max (2026 Feb)"),("dsv4","terminal-bench"):(67.9,"percent","DeepSeek-V4-Pro-Max (TB 2.0)"),
 ("dsv4","browsecomp"):(83.4,"percent","DeepSeek-V4-Pro-Max"),
 # Kimi K2.6 (own column, thinking high)
 ("k26","swe-bench-verified"):(80.2,"percent","K2.6 thinking-high"),("k26","swe-bench-multilingual"):(76.7,"percent","K2.6 thinking-high"),
 ("k26","swe-bench-pro"):(58.6,"percent","K2.6 thinking-high"),("k26","terminal-bench"):(66.7,"percent","K2.6 (TB 2.0, Terminus-2)"),
 ("k26","gpqa-diamond"):(90.5,"percent","K2.6 thinking-high"),("k26","aime"):(96.4,"percent","K2.6 (AIME 2026)"),
 ("k26","hmmt"):(92.7,"percent","K2.6 (2026 Feb)"),("k26","humanitys-last-exam"):(34.7,"percent","K2.6 (HLE-Full)"),
 ("k26","browsecomp"):(83.2,"percent","K2.6"),("k26","livecodebench"):(89.6,"percent","K2.6 (v6)"),
 ("k26","osworld"):(73.1,"percent","K2.6 (OSWorld-Verified)"),("k26","toolathlon"):(50.0,"percent","K2.6"),
 ("k26","mmmu-pro"):(79.4,"percent","K2.6"),("k26","charxiv"):(80.4,"percent","K2.6 (RQ)"),
 # GLM-4.7 (own column 1)
 ("glm47","gpqa-diamond"):(85.7,"percent","GLM-4.7"),("glm47","humanitys-last-exam"):(24.8,"percent","GLM-4.7 (42.8 w/ tools)"),
 ("glm47","aime"):(95.7,"percent","GLM-4.7 (AIME 2025)"),("glm47","hmmt"):(97.1,"percent","GLM-4.7 (Feb 2025)"),
 ("glm47","livecodebench"):(84.9,"percent","GLM-4.7 (v6)"),("glm47","swe-bench-verified"):(73.8,"percent","GLM-4.7 (OpenHands)"),
 ("glm47","swe-bench-multilingual"):(66.7,"percent","GLM-4.7"),("glm47","terminal-bench"):(41.0,"percent","GLM-4.7 (TB 2.0, Terminus-2)"),
 ("glm47","browsecomp"):(52.0,"percent","GLM-4.7"),
 # GLM-5 (own column 1)
 ("glm5","humanitys-last-exam"):(30.5,"percent","GLM-5 (text-only; 50.4 w/ tools)"),("glm5","aime"):(92.7,"percent","GLM-5 (AIME 2026 I)"),
 ("glm5","gpqa-diamond"):(86.0,"percent","GLM-5"),("glm5","swe-bench-verified"):(77.8,"percent","GLM-5 (OpenHands)"),
 ("glm5","swe-bench-multilingual"):(73.3,"percent","GLM-5"),("glm5","terminal-bench"):(56.2,"percent","GLM-5 (TB 2.0, Terminus-2; 60.7 verified)"),
 ("glm5","cybergym"):(43.2,"percent","GLM-5 (Claude Code 2.1.18)"),("glm5","browsecomp"):(62.0,"percent","GLM-5 (75.9 w/ context mgmt)"),
 # GLM-5.1 (own column 1)
 ("glm51","humanitys-last-exam"):(31.0,"percent","GLM-5.1 (52.3 w/ tools)"),("glm51","aime"):(95.3,"percent","GLM-5.1 (AIME 2026)"),
 ("glm51","gpqa-diamond"):(86.2,"percent","GLM-5.1"),("glm51","swe-bench-pro"):(58.4,"percent","GLM-5.1"),
 ("glm51","terminal-bench"):(63.5,"percent","GLM-5.1 (TB 2.0, Terminus-2)"),("glm51","cybergym"):(68.7,"percent","GLM-5.1"),
 ("glm51","browsecomp"):(68.0,"percent","GLM-5.1"),("glm51","hmmt"):(82.6,"percent","GLM-5.1 (Feb 2026)"),
}
SCORES.update(NEWSCORES)

NEWMETHOD={
 ("sonnet46","swe-bench-verified"):"averaged over 10 trials, adaptive; SWE-bench Multilingual 75.9",
 ("gpt55","swe-bench-pro"):"Public split; Anthropic notes evidence of memorization on this eval (claude-opus-4-7 news)",
 ("gpt54","webarena"):"WebArena-Verified, DOM+screenshot; Online-Mind2Web 92.8 (screenshot-only)",
 ("gemini31pro","terminal-bench"):"Terminus-2 harness; GPT-5.2 62.2 / GPT-5.3-Codex 77.3 on best self-reported (Codex) harness",
 ("dsv4","terminal-bench"):"Terminal-Bench 2.0; DeepSeek-V4-Pro-Max column of competitor comparison table (Opus-4.6/GPT-5.4/Gemini-3.1-Pro/K2.6/GLM-5.1/DS-V4-Pro-Max)",
 ("glm5","terminal-bench"):"Terminus 2 framework, 128K ctx; also 61.1 Claude Code 2.1.14; verified TB2.0 variant fixes ambiguous instructions",
 ("k26","terminal-bench"):"first data column = K2.6 (thinking high); Terminus-2 harness",
 ("gpt56card","healthbench"):"length-adjusted; also HealthBench 57.0 / Hard 33.1 / Consensus 95.5 (GPT-5.6 Sol)",
 ("fableblog","frontiercode"):"headline blog; main comparison table is an IMAGE (numbers live in the system card, not text) - blog prose headlines FrontierCode/CyberGym/CyScenarioBench + partner evals CursorBench/ViBench/FrontierBench",
}
METHOD.update(NEWMETHOD)

R=[]; unmatched=set()
for did,d in DOCS.items():
    _head = {x.strip().lower() for x in d.get("head", [])}
    _M = sum(1 for x in d["b"] if x != "__UNREADABLE__" and x.strip().lower() not in DROP)
    for raw in d["b"]:
        if raw == "__UNREADABLE__":
            R.append({"benchmark_canonical":None,"benchmark_raw":d.get("reason","primary source not machine-readable"),
              "source_doc":{"lab":d["lab"],"model":d["model"],"doc_type":d["dt"],"url":d["url"],"pub_date":d["date"],"primary":True},
              "citing_lab":d["lab"],"citing_model":d["model"],"prominence":{"type":"prose"},
              "reported":{"value":None,"unit":None,"model_config":None},
              "type":None,"domain":None,"on_harbor":False,"harbor_status":"not_in_harbor","harbor_name":None,
              "methodology_deviations":[],"score_pending":False,
              "needs_review":True,"review_reason":d.get("reason"),"review_issue":d.get("issue")})
            continue
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
        if not cc: nr=True; reason="unmatched benchmark name - register in aliases"; issue=8
        elif hs=="false_positive": nr=True; reason="Harbor auto-match is false positive"; issue=4
        elif hs=="needs_review": nr=True; reason="Harbor variant/version unconfirmed"; issue=ISSUE.get(cc,4)
        score_pending = val is None
        if score_pending and not issue: issue=6
        meth=[METHOD[(did,cc)]] if (did,cc) in METHOD else []
        R.append({"benchmark_canonical":cc,"benchmark_raw":raw,
          "source_doc":{"lab":d["lab"],"model":d["model"],"doc_type":d["dt"],"url":d["url"],"pub_date":d["date"],"primary":True},
          "citing_lab":d["lab"],"citing_model":d["model"],
          "prominence":{"type":("headline" if raw.strip().lower() in _head else d.get("prom","table_row")),"table_row_n":None,"table_total":_M},
          "reported":{"value":val,"unit":unit,"model_config":cfg},
          "type":type_of(cc) if cc else None,"domain":domain_of(cc) if cc else None,"on_harbor":on,"harbor_status":hs,"harbor_name":hn,
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
print("UNCLASSIFIED domain   :", sorted(UNCLASSIFIED))
