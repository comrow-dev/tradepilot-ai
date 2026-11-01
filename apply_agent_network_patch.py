from pathlib import Path
import shutil

def backup(path):
    shutil.copy2(path, str(path) + ".before-agent-network.bak")

def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise RuntimeError(label + ": förväntade en träff, fick " + str(count) + ". Avbryter.")
    return text.replace(old, new, 1)

# Full preflight: verify every expected anchor before creating backups or writing files.
checks = [
    ("backend/main.py", "from backend.engine.pipeline import scan_market as pipeline_scan_market\n"),
    ("backend/main.py", '@app.get("/api/agents")'),
    ("backend/main.py", '@app.get("/api/scan")'),
    ("backend/main.py", '    try:\n        data = pipeline_scan_market(limit=min(limit, 25))\n    except Exception as e:\n        return {"ok": False, "error": f"Scanner-fel: {e}", "results": []}\n'),
    ("backend/engine/pipeline.py", "from backend.engine.influencer import (\n"),
    ("backend/engine/pipeline.py", "def _discovery_symbols(fh):\n    symbols = []\n"),
    ("backend/engine/pipeline.py", "    result = score_candidate(c)\n"),
    ("frontend/app.js", "function agentCard(a){\n  const load = Math.min(100, Number(a.load||0)*10);"),
    ("frontend/index.html", '<div class="eyebrow">LIVE ACTIVITY</div><h2>ATLAS uppgiftslogg</h2>'),
]
for filename, anchor in checks:
    content = Path(filename).read_text(encoding="utf-8")
    if content.count(anchor) != 1:
        raise RuntimeError(f"Förkontroll misslyckades i {filename}. Ingen fil har ändrats.")

# Replace fake endpoints in main.py.
p = Path("backend/main.py")
s = p.read_text(encoding="utf-8")
backup(p)
s = replace_once(s,
    "from backend.engine.pipeline import scan_market as pipeline_scan_market\n",
    "from backend.engine.pipeline import scan_market as pipeline_scan_market\nfrom backend.engine.agent_runtime import snapshot as agent_snapshot, activity as agent_activity, begin_scan, finish_scan\n",
    "main import")
a = s.index('@app.get("/api/agents")')
b = s.index('@app.get("/api/scan")', a)
s = s[:a] + '@app.get("/api/agents")\ndef agents():\n    return agent_snapshot()\n\n\n@app.get("/api/activity")\ndef activity(limit: int = Query(40, ge=1, le=100)):\n    return agent_activity(limit)\n\n\n' + s[b:]
old = '    try:\n        data = pipeline_scan_market(limit=min(limit, 25))\n    except Exception as e:\n        return {"ok": False, "error": f"Scanner-fel: {e}", "results": []}\n'
new = '    if not begin_scan():\n        return {"ok": False, "running": True, "error": "En scan pågår redan.", "results": []}\n    try:\n        data = pipeline_scan_market(limit=min(limit, 25))\n    except Exception as e:\n        finish_scan(e)\n        return {"ok": False, "error": f"Scanner-fel: {e}", "results": []}\n    finish_scan()\n'
s = replace_once(s, old, new, "scan lifecycle")
p.write_text(s, encoding="utf-8")

# Add event hooks to actual stages in pipeline.py.
p = Path("backend/engine/pipeline.py")
s = p.read_text(encoding="utf-8")
backup(p)
s = replace_once(s, "from backend.engine.influencer import (\n",
    "from backend.engine.agent_runtime import set_agent\nfrom backend.engine.influencer import (\n", "pipeline import")
s = replace_once(s, "def _discovery_symbols(fh):\n    symbols = []\n",
    'def _discovery_symbols(fh):\n    symbols = []\n    set_agent("HUNTER", "ARBETAR", "Söker efter emissioner och filingar")\n', "HUNTER start")
s = replace_once(s, "    except Exception:\n        issuance = []\n\n    try:\n        news = discover_news_candidates(\n",
    '    except Exception:\n        issuance = []\n    set_agent("HUNTER", "KLAR", f"Emissionssökning klar: {len(issuance)} poster")\n    set_agent("SPECTRA", "ARBETAR", "Söker färska nyheter och catalysts")\n\n    try:\n        news = discover_news_candidates(\n', "SPECTRA start")
s = replace_once(s, "    except Exception:\n        news = []\n\n    for item in issuance + news:\n",
    '    except Exception:\n        news = []\n    set_agent("SPECTRA", "KLAR", f"Nyhetssökning klar: {len(news)} poster")\n\n    for item in issuance + news:\n', "SPECTRA finish")
s = replace_once(s, "    # 1. Fresh market discovery\n    # ------------------------------------------------------------\n    discovered_symbols, issuance, discovered_news = _discovery_symbols(fh)\n",
    '    # 1. Fresh market discovery\n    # ------------------------------------------------------------\n    set_agent("NOVA", "ARBETAR", "Bygger kandidatuniversum från upptäckter och bevakningslista")\n    discovered_symbols, issuance, discovered_news = _discovery_symbols(fh)\n', "NOVA start")
s = replace_once(s, "    try:\n        (\n            web_discovery_symbols,\n            influencer_raw_first_pass,\n            influencer_meta_first_pass,\n        ) = discover_explicit_tickers(max_articles_per_source=8)\n    except Exception:\n        web_discovery_symbols = []\n        influencer_raw_first_pass = []\n        influencer_meta_first_pass = {}\n",
    '    set_agent("SCOUT", "ARBETAR", "Läser offentliga investerar- och influencersidor")\n    try:\n        (\n            web_discovery_symbols,\n            influencer_raw_first_pass,\n            influencer_meta_first_pass,\n        ) = discover_explicit_tickers(max_articles_per_source=8)\n    except Exception:\n        web_discovery_symbols = []\n        influencer_raw_first_pass = []\n        influencer_meta_first_pass = {}\n    set_agent("SCOUT", "KLAR", f"Offentliga webbkällor gav {len(web_discovery_symbols)} tickers")\n', "SCOUT stage")
s = replace_once(s, "    # 3. Small-cap validation\n    # ------------------------------------------------------------\n    filtered = []\n",
    '    # 3. Small-cap validation\n    # ------------------------------------------------------------\n    set_agent("NOVA", "KLAR", f"Kandidatupptäckt klar: {len(ordered)} symboler")\n    filtered = []\n', "NOVA finish")
s = replace_once(s, "    try:\n        metrics = fh.metrics(symbol)\n    except Exception:\n        metrics = {}\n\n    fund = fundamental_snapshot(metrics, profile)\n    tfs = timeframe_data(fh, symbol)\n    tech = tfs.get(\"D\", {})\n",
    '    set_agent("VECTOR", "ARBETAR", f"Hämtar bolagsdata för {symbol}")\n    try:\n        metrics = fh.metrics(symbol)\n    except Exception:\n        metrics = {}\n    fund = fundamental_snapshot(metrics, profile)\n    set_agent("VECTOR", "KLAR", f"Bolagsdata klar för {symbol}")\n    set_agent("ORION", "ARBETAR", f"Analyserar momentum och volym för {symbol}")\n    tfs = timeframe_data(fh, symbol)\n    tech = tfs.get("D", {})\n    set_agent("ORION", "KLAR", f"Teknisk analys klar för {symbol}")\n', "VECTOR ORION")
s = replace_once(s, "    try:\n        raw_news = fh.company_news(symbol, 7)\n",
    '    set_agent("SPECTRA", "ARBETAR", f"Kontrollerar nyheter för {symbol}")\n    try:\n        raw_news = fh.company_news(symbol, 7)\n', "SPECTRA ticker start")
s = replace_once(s, "    except Exception:\n        news = list(discovered_news or [])\n\n    try:\n        rec = fh.recommendation_trends(symbol)[:3]\n",
    '    except Exception:\n        news = list(discovered_news or [])\n    set_agent("SPECTRA", "KLAR", f"Nyhetsanalys klar för {symbol}: {len(news)} träffar")\n\n    try:\n        rec = fh.recommendation_trends(symbol)[:3]\n', "SPECTRA ticker finish")
s = replace_once(s, "    result = score_candidate(c)\n",
    '    set_agent("CLOSER", "ARBETAR", f"Beräknar score och riskplan för {symbol}")\n    result = score_candidate(c)\n    set_agent("CLOSER", "KLAR", f"Risk- och signalbedömning klar för {symbol}")\n', "CLOSER scoring")
p.write_text(s, encoding="utf-8")

# Update dashboard rendering to show real status and tasks.
p = Path("frontend/app.js")
s = p.read_text(encoding="utf-8")
backup(p)
old = 'function agentCard(a){\n  const load = Math.min(100, Number(a.load||0)*10);'
new = 'function agentCard(a){\n  const working = a.status === "ARBETAR";\n  const load = working ? 100 : 0;'
s = replace_once(s, old, new, "agent card start")
s = replace_once(s, '<span class="agent-status">● ${a.status}</span>',
    '<span class="agent-status ${a.status === "FEL" ? "down" : (working ? "up" : "")}">● ${a.status}</span>', "agent status")
s = replace_once(s, '<div class="load"><span>Aktuell belastning</span><b>${a.load}/10</b></div>',
    '<div class="load"><span>${a.task || "Inväntar arbetssteg"}</span><b>${working ? "AKTIV" : "—"}</b></div>', "agent task")
s = replace_once(s, '  if(d.ok) $("agents").innerHTML = d.agents.map(agentCard).join("");',
    '  if(d.ok){\n    $("agents").innerHTML = d.agents.map(agentCard).join("");\n    $("activeAgents").textContent = `${d.agents.filter(a => a.status === "ARBETAR").length}/8`;\n    $("sideStatus").textContent = d.running ? "Scan pågår" : "Väntar på scan";\n    $("status").textContent = d.running ? "SCANNING" : "IDLE";\n  }', "agent count")
s = replace_once(s, '  const t = new Date(x.time*1000).toLocaleTimeString("sv-SE",{hour:"2-digit",minute:"2-digit"});',
    '  const t = new Date(x.time*1000).toLocaleTimeString("sv-SE",{hour:"2-digit",minute:"2-digit",second:"2-digit"});', "activity time")
s = replace_once(s, '<div class="activity-top"><b>ATLAS</b><span>→</span><b>${x.agent}</b><span class="badge">${x.status}</span></div>',
    '<div class="activity-top"><b>${x.agent}</b><span class="badge">${x.status}</span></div>', "activity agent")
s = replace_once(s, '  setInterval(loadActivity, 30000);',
    '  setInterval(async()=>{ await loadAgents(); await loadActivity(); }, 3000);', "live polling")
p.write_text(s, encoding="utf-8")

# Rename the activity panel to Mission Control.
p = Path("frontend/index.html")
s = p.read_text(encoding="utf-8")
backup(p)
s = replace_once(s, '<div class="eyebrow">LIVE ACTIVITY</div><h2>ATLAS uppgiftslogg</h2>',
    '<div class="eyebrow">MISSION CONTROL • LIVE EVENTS</div><h2>Agenternas aktivitetslogg</h2>', "Mission Control label")
p.write_text(s, encoding="utf-8")

# Install runtime module last, after all guarded source edits succeeded.
Path("backend/engine/agent_runtime.py").write_text(
    Path(__file__).with_name("agent_runtime.py").read_text(encoding="utf-8"), encoding="utf-8")

print("Patch applicerad. Backupfiler skapades med suffix .before-agent-network.bak.")
print("Kör compileall och kontrollera /api/agents och /api/activity före push/deploy.")
