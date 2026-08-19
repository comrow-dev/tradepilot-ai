import os
import requests
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="TradePilot AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALPHA_VANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
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
        "market_data": bool(ALPHA_VANTAGE_KEY),
        "ai": bool(OPENAI_KEY),
        "time": datetime.now(timezone.utc).isoformat(),
    }


def alpha_vantage(function, **params):
    if not ALPHA_VANTAGE_KEY:
        raise HTTPException(
            status_code=503,
            detail="ALPHAVANTAGE_API_KEY saknas.",
        )

    params["function"] = function
    params["apikey"] = ALPHA_VANTAGE_KEY

    response = requests.get(
        "https://www.alphavantage.co/query",
        params=params,
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if "Error Message" in data:
        raise HTTPException(
            status_code=502,
            detail=data["Error Message"],
        )

    if "Note" in data:
        raise HTTPException(
            status_code=429,
            detail=data["Note"],
        )

    return data


@app.get("/api/quote/{symbol}")
def quote(symbol: str):
    return alpha_vantage(
        "GLOBAL_QUOTE",
        symbol=symbol.upper(),
    )


@app.get("/api/intraday/{symbol}")
def intraday(
    symbol: str,
    interval: str = "5min",
):
    return alpha_vantage(
        "TIME_SERIES_INTRADAY",
        symbol=symbol.upper(),
        interval=interval,
        outputsize="compact",
    )


@app.get("/api/gainers")
def gainers():
    return alpha_vantage("TOP_GAINERS_LOSERS")


@app.get("/api/scan")
def scan():
    data = alpha_vantage("TOP_GAINERS_LOSERS")

    candidates = []

    for stock in data.get("top_gainers", []):
        try:
            change = float(
                str(stock.get("change_percentage", "0"))
                .replace("%", "")
            )
        except ValueError:
            continue

        if 10 <= change <= 30:
            candidates.append(
                {
                    "symbol": stock.get("ticker"),
                    "price": stock.get("price"),
                    "change_pct": change,
                    "volume": stock.get("volume"),
                }
            )

    candidates.sort(
        key=lambda x: x["change_pct"],
        reverse=True,
    )

    return {
        "count": len(candidates),
        "results": candidates[:50],
    }


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
