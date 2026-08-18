
import os, math, time
from datetime import datetime, timezone
from typing import Optional
import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="TradePilot AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ALPHA_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

# Real backend: no fake stock prices. If the data key is missing, the API explicitly says so.
def av(function, **params):
    if not ALPHA_KEY:
        raise HTTPException(503, "ALPHAVANTAGE_API_KEY saknas. Lägg in din marknadsdata-nyckel.")
    params.update({"function": function, "apikey": ALPHA_KEY})
    r = requests.get("https://www.alphavantage.co/query", params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    if "Error Message" in data or "Note" in data:
        raise HTTPException(502, str(data))
    return data

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "market_data": bool(ALPHA_KEY),
        "ai": bool(OPENAI_KEY),
        "time": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/quote/{symbol}")
def quote(symbol: str):
    return av("GLOBAL_QUOTE", symbol=symbol.upper())

@app.get("/api/intraday/{symbol}")
def intraday(symbol: str, interval: str = "5min"):
    return av("TIME_SERIES_INTRADAY", symbol=symbol.upper(), interval=interval, outputsize="compact")

@app.get("/api/gainers")
def gainers():
    # US top gainers/losers endpoint. Global discovery is added through the exchange universe
    # and IPO calendar provider in the production deployment.
    return av("TOP_GAINERS_LOSERS")

class Chat(BaseModel):
    message: str
    context: Optional[dict] = None

@app.post("/api/chat")
def chat(body: Chat):
    if not OPENAI_KEY:
        return {"answer": "AI-nyckel saknas. Appen är redo för OpenAI API, men ingen API-nyckel är installerad ännu."}

    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content":
             "Du är TradePilot AI, ett personligt beslutsstöd för kortsiktig aktiehandel. "
             "Analysera data som ges till dig. Hitta inte på priser, nyheter eller signaler. "
             "Säg tydligt när data saknas. Ge köp/behåll/sälj som beslutsstöd, inte som garanti. "
             "Prioritera risk, likviditet, spread, stop-loss och risk/reward."},
            {"role": "user", "content": body.message + "\nKONTEXT:\n" + str(body.context or {})}
        ]
    }
    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {OPENAI_KEY}", "Content-Type": "application/json"},
        json=payload, timeout=30
    )
    r.raise_for_status()
    data = r.json()
    return {"answer": data.get("output_text", "AI:n gav inget textsvar.")}

@app.get("/api/scan")
def scan():
    data = av("TOP_GAINERS_LOSERS")
    gainers = data.get("top_gainers", [])
    # Conservative scanner: only flags 10–30% daily gainers; other risk filters are calculated
    # by the next scoring layer after intraday/volume data is fetched.
    rows = []
    for x in gainers:
        try:
            pct = float(str(x.get("change_percentage", "0")).replace("%",""))
        except ValueError:
            continue
        if 10 <= pct <= 30:
            rows.append({
                "symbol": x.get("ticker"),
                "price": x.get("price"),
                "change_pct": pct,
                "volume": x.get("volume"),
                "source": "Alpha Vantage"
            })
    return {"count": len(rows), "results": rows[:50]}
