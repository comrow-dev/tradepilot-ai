import os
import math
from datetime import datetime, timezone
from pathlib import Path

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.engine.pipeline import scan_market as pipeline_scan_market

ROOT = Path(__file__).resolve().parent.parent
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()

app = FastAPI(title="TradePilot AI", version="4.1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

AGENTS = [
    {"id":"ATLAS","role":"Chief AI","label":"Samordning","description":"Prioriterar kandidater och sammanför agenternas fynd."},
    {"id":"NOVA","role":"Market Scanner","label":"Scanning","description":"Letar micro-cap och small-cap kandidater."},
    {"id":"ORION","role":"Momentum","label":"Teknisk","description":"Analyserar prisrörelse, momentum och volym."},
    {"id":"SPECTRA","role":"News & Catalyst","label":"Nyheter","description":"Letar färska nyheter och möjliga catalysts."},
    {"id":"HUNTER","role":"SEC / Filings","label":"SEC","description":"Kontrollerar emissioner, filingar och insiderdata."},
    {"id":"VECTOR","role":"Fundamentals","label":"Bolagsdata","description":"Kompletterar bolags- och värderingsdata."},
    {"id":"SCOUT","role":"Sentiment","label":"Sentiment","description":"Bedömer marknadens ton och signalstyrka."},
    {"id":"CLOSER","role":"Risk Manager","label":"Risk","description":"Beräknar entry, stop-loss, targets och risk/reward."},
]

def num(x, default=0.0):
    try:
        v = float(x)
        return default if math.isnan(v) or math.isinf(v) else v
    except Exception:
        return default

@app.get("/")
def home():
    return FileResponse(ROOT / "frontend" / "index.html")

@app.get("/style.css")
def css():
    return FileResponse(ROOT / "frontend" / "style.css", media_type="text/css")

@app.get("/app.js")
def js():
    return FileResponse(ROOT / "frontend" / "app.js", media_type="application/javascript")

@app.get("/api/health")
def health():
    return {"ok": True, "market_data": bool(FINNHUB_KEY), "ai": bool(OPENAI_KEY), "server_time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/agents")
def agents():
    return {"ok": True, "agents": [{**a, "status": "KÖR" if a["id"] != "ATLAS" else "SAMORDNAR", "load": 8 if a["id"] == "ATLAS" else 3 + (ord(a["id"][0]) % 5), "performance": 90 + (ord(a["id"][-1]) % 10)} for a in AGENTS]}

@app.get("/api/activity")
def activity():
    now = datetime.now(timezone.utc)
    templates = [("NOVA","Sök nya micro-cap kandidater"),("ORION","Analysera momentum och volym"),("SPECTRA","Kontrollera färska catalysts"),("HUNTER","Kontrollera SEC/insiderdata"),("VECTOR","Komplettera bolagsdata"),("SCOUT","Kvalificera sentiment"),("CLOSER","Beräkna entry, stop-loss och targets")]
    rows = []
    for i, (agent, task) in enumerate(templates):
        rows.append({"id": f"TK-{80210+i}", "agent": agent, "task": task, "status": "KLAR" if i % 3 else "PÅGÅR", "time": now.timestamp() - i * 91})
    return {"ok": True, "items": rows}

@app.get("/api/scan")
def scan(limit: int = Query(25, ge=5, le=50), min_price: float = Query(.5, ge=0), max_price: float = Query(50, ge=0), min_market_cap_m: float = Query(2, ge=0), max_market_cap_m: float = Query(250, ge=0), min_score: int = Query(60, ge=0, le=100)):
    try:
        data = pipeline_scan_market(limit=min(limit, 25))
    except Exception as e:
        return {"ok": False, "error": f"Scanner-fel: {e}", "results": []}
    if not data.get("ok"):
        return data
    filtered = []
    for row in data.get("results", []):
        price = num(row.get("price"), -1); cap = num(row.get("market_cap_m"), -1); score = num(row.get("score"), 0)
        if min_price <= price <= max_price and min_market_cap_m <= cap <= max_market_cap_m and score >= min_score:
            filtered.append(row)
    filtered.sort(key=lambda x: (num(x.get("score")), num(x.get("confidence")), -num(x.get("market_cap_m"), 999999)), reverse=True)
    data["results"] = filtered[:limit]
    data["count"] = len(data["results"])
    data["timestamp"] = data.get("scanned_at") or datetime.now(timezone.utc).isoformat()
    return data

@app.get("/api/quote/{symbol}")
def quote(symbol: str):
    try:
        from backend.engine.data import Finnhub
        return {"ok": True, "quote": Finnhub().quote(symbol.upper())}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/ask")
def ask(question: str = Query(..., min_length=1, max_length=1000)):
    if not OPENAI_KEY:
        return {"ok": False, "answer": "AI-assistenten är inte aktiverad. Lägg in OPENAI_API_KEY i Render → Environment."}
    try:
        r = requests.post("https://api.openai.com/v1/responses", headers={"Authorization": "Bearer " + OPENAI_KEY, "Content-Type": "application/json"}, json={"model": OPENAI_MODEL, "input": "Du är TradePilot AI, en svensk aktieanalytiker. Svara kort och konkret. Marknadsinformation är inte personlig investeringsrådgivning.\n\n" + question}, timeout=30)
        r.raise_for_status(); data = r.json()
        return {"ok": True, "answer": data.get("output_text") or "Inget svar från AI."}
    except Exception as e:
        return {"ok": False, "answer": "AI-fel: " + str(e)}
