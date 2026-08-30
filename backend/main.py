import os
from datetime import datetime, timezone
from typing import Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.auto_scan import scan_market, _request
from backend.daytrading_source import SOURCE_URL

app = FastAPI(title="TradePilot AI")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

@app.get("/api/health")
def health():
    return {
        "ok": True,
        "market_data": bool(os.getenv("FINNHUB_API_KEY")),
        "ai": bool(OPENAI_KEY),
        "daytrading_source": SOURCE_URL,
        "time": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/api/quote/{symbol}")
def quote(symbol: str):
    try:
        return _request("/quote", {"symbol": symbol.upper()})
    except Exception as exc:
        raise HTTPException(502, str(exc))

@app.get("/api/scan")
def scan():
    try:
        return scan_market()
    except Exception as exc:
        raise HTTPException(502, str(exc))

class Chat(BaseModel):
    message: str
    context: Optional[dict] = None

@app.post("/api/chat")
def chat(body: Chat):
    if not OPENAI_KEY:
        return {
            "answer": "AI-nyckel saknas. Marknadsscannern kan ändå köras med Finnhub.",
        }

    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {
                "role": "system",
                "content": (
                    "Du är TradePilot AI. Använd bara data som finns i kontexten. "
                    "Hitta inte på priser, nyheter eller signaler. TradePilots egen "
                    "scoring är huvudbedömningen. Daytrading.se är endast ett separat "
                    "expertlager. Var tydlig med risk och osäkerhet."
                ),
            },
            {
                "role": "user",
                "content": body.message + "\nKONTEXT:\n" + str(body.context or {}),
            },
        ],
    }

    r = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {OPENAI_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    return {"answer": data.get("output_text", "AI:n gav inget textsvar.")}
