import os
import time
import requests
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from scanner_state import get_state, save_scan
from auto_scan import scan_market
from scoring import analyze

app = FastAPI(title="TradePilot AI")

MARKET_CACHE = None
MARKET_CACHE_TIME = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

@app.get("/")

def home():
    return {
        "app": "TradePilot AI",
        "status": "online",
        "message": "TradePilot AI backend fungerar."
    }

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "market_data": bool(TWELVE_DATA_KEY),
        "ai": bool(OPENAI_KEY),
        "time": datetime.now(timezone.utc).isoformat(),
    }


def twelve_data(endpoint, **params):
    if not TWELVE_DATA_KEY:
        raise HTTPException(
            status_code=503,
            detail="TWELVE_DATA_API_KEY saknas."
        )

    params["apikey"] = TWELVE_DATA_KEY

    response = requests.get(
        f"https://api.twelvedata.com/{endpoint}",
        params=params,
        timeout=20
    )

    response.raise_for_status()

    data = response.json()

    if data.get("status") == "error":
        raise HTTPException(
            status_code=502,
            detail=data.get("message", "Twelve Data API-fel")
        )

    return data
def scan_market():
    global MARKET_CACHE, MARKET_CACHE_TIME

    now = datetime.now(timezone.utc)

    # Cache i 15 minuter
    if MARKET_CACHE is not None and MARKET_CACHE_TIME is not None:
        age = (now - MARKET_CACHE_TIME).total_seconds()

        if age < 900:
            return MARKET_CACHE

    # Aktier som TradePilot ska analysera
    symbols = [
        "AAPL",
        "MSFT",
        "NVDA",
        "AMZN",
        "META",
        "GOOGL",
        "TSLA",
        "AMD",
        "AVGO",
        "NFLX",
        "JPM",
        "V",
        "MA",
        "COST",
        "WMT",
        "ORCL",
        "CRM",
        "ADBE",
        "QCOM",
        "INTC",
        "MU",
        "PLTR",
        "COIN",
        "UBER",
        "SHOP"
    ]

    # Hämta quotes i ett batch-anrop
    # Hämta quotes i batchar om max 8 aktier
    
    data = {}
    
    for i in range(0, len(symbols), 4):
        batch = symbols[i:i + 4]

        batch_data = twelve_data(
            "quote",
            symbol=",".join(batch)
        )

        if isinstance(batch_data, dict):
            data.update(batch_data)

        if i + 4 < len(symbols):
            time.sleep(61)

    candidates = []

    for symbol in symbols:
        try:
            stock = data.get(symbol)

            if not stock or stock.get("status") == "error":
                continue

            change = float(
                stock.get("percent_change", 0)
            )

            price = float(
                stock.get("close", 0)
            )

            volume = int(
                float(stock.get("volume", 0))
            )

            if price <= 0:
                continue

            score = 50

            # Momentum
            if change >= 5:
                score += 15
            elif change >= 2:
                score += 8
            elif change < 0:
                score -= 10

            # Volym
            if volume >= 1_000_000:
                score += 15
            elif volume >= 100_000:
                score += 8

            # Begränsa score till 0-100
            score = max(0, min(100, score))

            # Signal
            if score >= 80:
                signal = "KÖP"
            elif score >= 65:
                signal = "AVVAKTA"
            else:
                signal = "UNDVIK"

            # Risknivåer
            buy_low = round(price * 0.98, 2)
            buy_high = round(price * 1.01, 2)
            target = round(price * 1.10, 2)
            stop_loss = round(price * 0.95, 2)

            candidates.append({
                "symbol": symbol,
                "price": price,
                "change_pct": change,
                "volume": volume,
                "score": score,
                "signal": signal,
                "buy_zone": {
                    "low": buy_low,
                    "high": buy_high
                },
                "target": target,
                "stop_loss": stop_loss
            })

        except (TypeError, ValueError):
            continue

    # Bästa aktierna först
    candidates.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    result = {
        "count": len(candidates),
        "results": candidates[:50]
    }

    MARKET_CACHE = result
    MARKET_CACHE_TIME = now

    return result
    
@app.get("/api/intraday/{symbol}")
def intraday(
    symbol: str,
    interval: str = "5min"
):
    return twelve_data(
    "time_series",
    symbol=symbol.upper(),
    interval=interval,
    outputsize=100
        
    )

@app.get("/api/gainers")
def gainers():
    return alpha_vantage("TOP_GAINERS_LOSERS")

@app.get("/api/scan")
def scan():
    try:
        result = scan_market()
        return result
    except Exception as error:
        return {
            "ok": False,
            "error": str(error),
            "results": []
        }
@app.get("/api/auto-scan")
def auto_scan():
    try:
        result = scan_market()
        save_scan(
            result.get("results", []),
            result.get("error")
        )
        return result
    except Exception as error:
        save_scan([], str(error))
        return {
            "ok": False,
            "error": str(error),
            "results": [],
        }

@app.get("/api/scanner-state")
def scanner_state():
    return get_state()


class ChatRequest(BaseModel):
    message: str
    context: Optional[dict] = None

@app.post("/api/chat")
def chat(request: ChatRequest):

    if not OPENAI_KEY:
        return {
            "answer": (
                "AI-chatten är redo, men OPENAI_API_KEY "
                "är inte konfigurerad ännu."
            )
        }

    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-5.6-luna",
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Du är TradePilot AI, en personlig "
                        "tradingassistent. Analysera endast "
                        "data som du faktiskt får. Hitta inte "
                        "på aktiekurser eller nyheter. "
                        "Prioritera riskhantering, likviditet, "
                        "spread, stop-loss och risk/reward. "
                        "Köp, behåll och sälj är beslutsstöd "
                        "och ingen garanti för framtida resultat."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        request.message
                        + "\n\nKONTEXT:\n"
                        + str(request.context or {})
                    ),
                },
            ],
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    return {
        "answer": data.get(
            "output_text",
            "AI:n gav inget textsvar.",
        )
  }
