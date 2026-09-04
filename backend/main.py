import os
from datetime import datetime, timezone
from typing import Optional
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.engine.data import Finnhub
from backend.engine.pipeline import scan_market
from backend.engine.backtest import backtest_symbol
from backend.engine.validation import walk_forward
from backend.engine.sec import SEC
from backend.engine.learning import summary, close_signal
from backend.daytrading_source import SOURCE_URL

app=FastAPI(title="TradePilot AI", version="2.0")
origins=[x.strip() for x in os.getenv("TRADEPILOT_CORS_ORIGINS","http://localhost:3000,http://localhost:5173,http://127.0.0.1:5500").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_methods=["GET","POST"],allow_headers=["Content-Type","Authorization"])
OPENAI_KEY=os.getenv("OPENAI_API_KEY",""); OPENAI_MODEL=os.getenv("OPENAI_MODEL","")

@app.get("/api/health")
def health():
    return {"ok":True,"market_data":bool(os.getenv("FINNHUB_API_KEY")),"ai":bool(OPENAI_KEY),"model_configured":bool(OPENAI_MODEL),"daytrading_source":SOURCE_URL,"learning":summary(),"time":datetime.now(timezone.utc).isoformat()}

@app.get("/api/quote/{symbol}")
def quote(symbol:str):
    try:return Finnhub().quote(symbol.upper())
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/scan")
def scan(limit:int=Query(25,ge=5,le=50)):
    try:return scan_market(limit=limit)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/auto-scan")
def auto_scan(limit:int=Query(25,ge=5,le=50)):
    try:return scan_market(limit=limit)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/backtest/{symbol}")
def backtest(symbol:str,lookback:int=Query(250,ge=60,le=1000)):
    try:return backtest_symbol(Finnhub(),symbol.upper(),lookback)
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/walk-forward/{symbol}")
def walk_forward(symbol:str,lookback:int=Query(750,ge=300,le=2000),train_days:int=Query(400,ge=100,le=1000),test_days:int=Query(100,ge=30,le=500),step:int=Query(100,ge=20,le=500)):
    try:return walk_forward(Finnhub(),symbol.upper(),lookback,train_days,test_days,step)
    except Exception as e: raise HTTPException(502,str(e))

@app.post("/api/signals/{signal_id}/close")
def close(signal_id:int,outcome:str,exit_price:float,pnl_pct:float):
    try:return close_signal(signal_id,outcome.upper(),exit_price,pnl_pct)
    except ValueError as e: raise HTTPException(400,str(e))

@app.get("/api/sec/{symbol}")
def sec(symbol:str):
    try:return SEC().submissions(symbol.upper())
    except Exception as e: raise HTTPException(502,str(e))

@app.get("/api/performance")
def performance(): return summary()

class Chat(BaseModel):
    message:str
    context:Optional[dict]=None

@app.post("/api/chat")
def chat(body:Chat):
    if not OPENAI_KEY or not OPENAI_MODEL:
        return {"answer":"AI är inte konfigurerad. TradePilot kan fortfarande analysera marknadsdata."}
    prompt=("Du är TradePilot AI. Använd endast strukturerad kontext. Hitta aldrig på data. "
            "TradePilots egen score är huvudbedömningen. Externa källor är separata och ska märkas. "
            "Beskriv risk, osäkerhet och varför en signal uppstår. Om data saknas, säg det.")
    payload={"model":OPENAI_MODEL,"input":[{"role":"system","content":prompt},{"role":"user","content":body.message+"\nKONTEXT:\n"+str(body.context or {})}]}
    try:
        r=requests.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {OPENAI_KEY}","Content-Type":"application/json"},json=payload,timeout=30); r.raise_for_status(); d=r.json(); return {"answer":d.get("output_text","AI:n gav inget textsvar.")}
    except requests.HTTPError as e:
        raise HTTPException(502,f"AI API-fel: {e.response.text[:500] if e.response is not None else str(e)}")
    except Exception as e: raise HTTPException(502,str(e))
