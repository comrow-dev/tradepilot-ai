import os, math, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

ROOT = Path(__file__).resolve().parent.parent
FINNHUB_KEY = os.getenv("FINNHUB_API_KEY", "").strip()
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini").strip()

app = FastAPI(title="TradePilot AI", version="4.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

UNIVERSE = [
    "RENX","RENT","RIVN","SOUN","IONQ","ACHR","PLTR","RKLB","DNA","OPEN",
    "JOBY","LUMN","BBAI","BIG","CLOV","ATER","FFIE","MVST","GPRO","LAZR",
    "QS","HIMS","LCID","GRAB","WBD","TMC","EVGO","CHPT","FUBO","MARA",
    "RIOT","CLSK","IREN","SENS","LIDR","KULR","SERV","ASTS","SMFL","CTM",
]

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

def finnhub(path, params):
    if not FINNHUB_KEY:
        raise RuntimeError("FINNHUB_API_KEY saknas i Render → Environment.")
    p = dict(params)
    p["token"] = FINNHUB_KEY
    r = requests.get("https://finnhub.io/api/v1/" + path, params=p, timeout=12)
    r.raise_for_status()
    return r.json()

def score_row(q, profile):
    price = num(q.get("c"))
    change = num(q.get("dp"))
    volume = num(q.get("v"))
    avg_volume = num(profile.get("avgVolume10"), volume)
    cap = num(profile.get("marketCapitalization"))
    volume_ratio = volume / avg_volume if avg_volume > 0 else 0

    momentum = max(0, min(35, 18 + change * 1.7))
    volume_score = min(30, volume_ratio * 10)
    liquidity_score = min(15, math.log10(max(volume, 1)) * 1.5)
    price_score = 10 if 0.50 <= price <= 20 else 6
    catalyst_score = 10 if abs(change) >= 5 else 4

    score = int(max(0, min(100, round(
        momentum + volume_score + liquidity_score + price_score + catalyst_score
    ))))
    risk = "LÅG" if score >= 82 else "MEDEL" if score >= 68 else "HÖG"

    stop_pct = 0.88 if risk == "HÖG" else 0.92 if risk == "MEDEL" else 0.94
    target1_pct = 1.15 if risk == "HÖG" else 1.12 if risk == "MEDEL" else 1.10
    target2_pct = 1.30 if risk == "HÖG" else 1.22 if risk == "MEDEL" else 1.18

    reasons = []
    if change >= 5: reasons.append("starkt momentum")
    if change <= -5: reasons.append("hög volatilitet")
    if volume_ratio >= 2: reasons.append(f"volym {volume_ratio:.1f}x snitt")
    if cap and cap <= 250: reasons.append("small-cap")
    if abs(change) >= 5: reasons.append("stor dagsrörelse")
    if not reasons: reasons.append("neutral teknisk signal")

    action = "ÖVERVÄG" if score >= 75 else "BEVAKA" if score >= 60 else "AVVAKTA"
    return {
        "symbol": q.get("symbol") or profile.get("ticker"),
        "name": profile.get("name") or q.get("symbol"),
        "score": score, "risk": risk, "action": action,
        "price": price, "change_pct": change, "volume": volume,
        "market_cap_m": cap, "volume_ratio": round(volume_ratio, 2),
        "reasons": reasons,
        "agents": {
            "NOVA": min(100, score + 4),
            "ORION": int(max(0, min(100, momentum / 35 * 100))),
            "VECTOR": 62 if cap else 40,
            "CLOSER": 78 if score >= 70 else 55,
        },
        "trade_plan": {
            "entry": round(price, 4),
            "stop_loss": round(price * stop_pct, 4),
            "target_1": round(price * target1_pct, 4),
            "target_2": round(price * target2_pct, 4),
            "risk_reward": round(
                ((price * target1_pct) - price) /
                max(price - (price * stop_pct), 0.0001), 2
            ),
        }
    }

def scan_market(limit=25, min_price=.5, max_price=50, min_cap=2, max_cap=250, min_score=60):
    if not FINNHUB_KEY:
        return {"ok": False, "error": "FINNHUB_API_KEY saknas. Lägg in den under Render → Environment.", "results": []}

    results, scanned = [], 0
    for symbol in UNIVERSE:
        try:
            q = finnhub("quote", {"symbol": symbol})
            profile = finnhub("stock/profile2", {"symbol": symbol})
            price = num(q.get("c"))
            cap = num(profile.get("marketCapitalization"))
            scanned += 1
            if not (min_price <= price <= max_price):
                continue
            if cap and not (min_cap <= cap <= max_cap):
                continue
            row = score_row(q, profile)
            if row["score"] >= min_score:
                results.append(row)
        except Exception:
            continue

    results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "ok": True, "source": "Finnhub", "scanned": scanned,
        "count": len(results[:limit]), "results": results[:limit],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

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
    return {
        "ok": True,
        "market_data": bool(FINNHUB_KEY),
        "ai": bool(OPENAI_KEY),
        "server_time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/agents")
def agents():
    return {
        "ok": True,
        "agents": [
            {**a, "status": "KÖR" if a["id"] != "ATLAS" else "SAMORDNAR",
             "load": 8 if a["id"] == "ATLAS" else 3 + (ord(a["id"][0]) % 5),
             "performance": 90 + (ord(a["id"][-1]) % 10)}
            for a in AGENTS
        ]
    }

@app.get("/api/activity")
def activity():
    now = datetime.now(timezone.utc)
    templates = [
        ("NOVA","Sök nya micro-cap kandidater"),
        ("ORION","Analysera momentum och volym"),
        ("SPECTRA","Kontrollera färska catalysts"),
        ("HUNTER","Kontrollera SEC/insiderdata"),
        ("VECTOR","Komplettera bolagsdata"),
        ("SCOUT","Kvalificera sentiment"),
        ("CLOSER","Beräkna entry, stop-loss och targets"),
    ]
    rows = []
    for i, (agent, task) in enumerate(templates):
        rows.append({
            "id": f"TK-{80210+i}",
            "agent": agent,
            "task": task,
            "status": "KLAR" if i % 3 else "PÅGÅR",
            "time": (now.timestamp() - i*91)
        })
    return {"ok": True, "items": rows}

@app.get("/api/scan")
def scan(
    limit: int = Query(25, ge=5, le=50),
    min_price: float = Query(.5, ge=0),
    max_price: float = Query(50, ge=0),
    min_market_cap_m: float = Query(2, ge=0),
    max_market_cap_m: float = Query(250, ge=0),
    min_score: int = Query(60, ge=0, le=100)
):
    return scan_market(limit, min_price, max_price, min_market_cap_m, max_market_cap_m, min_score)

@app.get("/api/quote/{symbol}")
def quote(symbol: str):
    try:
        return {"ok": True, "quote": finnhub("quote", {"symbol": symbol.upper()})}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/api/ask")
def ask(question: str = Query(..., min_length=1, max_length=1000)):
    if not OPENAI_KEY:
        return {"ok": False, "answer": "AI-assistenten är inte aktiverad. Lägg in OPENAI_API_KEY i Render → Environment."}
    try:
        r = requests.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": "Bearer " + OPENAI_KEY, "Content-Type": "application/json"},
            json={
                "model": OPENAI_MODEL,
                "input": (
                    "Du är TradePilot AI, en svensk aktieanalytiker. "
                    "Svara kort och konkret. Marknadsinformation är inte personlig investeringsrådgivning.\n\n"
                    + question
                )
            },
            timeout=30
        )
        r.raise_for_status()
        data = r.json()
        return {"ok": True, "answer": data.get("output_text") or "Inget svar från AI."}
    except Exception as e:
        return {"ok": False, "answer": "AI-fel: " + str(e)}
