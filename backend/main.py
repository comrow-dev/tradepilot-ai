import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.engine.data import Finnhub
from backend.engine.pipeline import scan_market
from backend.engine.news_discovery import discover_news_candidates
from backend.engine.issuance_discovery import discover_issuance_candidates
from backend.engine.backtest import backtest_symbol
from backend.engine.validation import walk_forward as run_walk_forward
from backend.engine.sec import SEC
from backend.engine.learning import summary, close_signal, open_signals
from backend.engine.sentisense_adapter import get_sentiment
from backend.daytrading_source import SOURCE_URL

app = FastAPI(title="TradePilot AI", version="2.0")

origins = [
    x.strip()
    for x in os.getenv(
        "TRADEPILOT_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    ).split(",")
    if x.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_KEY = os.getenv("OPENAI_API_KEY", os.getenv("OPENAI_KEY", ""))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")


@app.get("/")
def root():
    frontend_index = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "frontend",
        "index.html",
    )
    if os.path.exists(frontend_index):
        return FileResponse(frontend_index)

    return {
        "ok": True,
        "name": "TradePilot AI",
        "version": "2.0",
        "message": "API is running",
        "docs": "/docs",
    }


frontend_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "frontend",
)

if os.path.isdir(frontend_dir):
    app.mount("/frontend", StaticFiles(directory=frontend_dir), name="frontend")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "market_data": bool(os.getenv("FINNHUB_API_KEY")),
        "ai": bool(OPENAI_KEY),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/quote/{symbol}")
def quote(symbol: str):
    try:
        return Finnhub().quote(symbol.upper())
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.head("/api/scan")
def scan_head():
    return None


@app.get("/api/scan")
def scan(limit: int = Query(25, ge=5, le=50)):
    try:
        return scan_market(limit=limit)
    except TypeError:
        try:
            return scan_market(limit)
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/news-discovery")
def news_discovery(
    days: int = Query(7, ge=1, le=7),
    limit: int = Query(25, ge=1, le=50),
):
    try:
        return discover_news_candidates(Finnhub(), days=days, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/issuance-discovery")
def issuance_discovery(
    days: int = Query(7, ge=1, le=14),
    limit: int = Query(25, ge=1, le=50),
):
    try:
        return discover_issuance_candidates(days=days, limit=limit)
    except TypeError:
        try:
            return discover_issuance_candidates(
                Finnhub(), days=days, limit=limit
            )
        except Exception as e:
            raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/backtest/{symbol}")
def backtest(symbol: str):
    try:
        return backtest_symbol(symbol.upper())
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/validation/{symbol}")
def validation(symbol: str):
    try:
        return run_walk_forward(symbol.upper())
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/sentiment/{symbol}")
def sentiment(symbol: str):
    try:
        return {
            "symbol": symbol.upper(),
            "sentiment": get_sentiment(symbol.upper()),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/learning/summary")
def learning_summary():
    try:
        return summary()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/learning/open-signals")
def learning_open_signals():
    try:
        return open_signals()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


class SignalPayload(BaseModel):
    symbol: str
    action: Optional[str] = None
    score: Optional[float] = None
    entry: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None


@app.post("/api/learning/close-signal")
def learning_close_signal(payload: SignalPayload):
    try:
        try:
            return close_signal(payload.model_dump())
        except AttributeError:
            return close_signal(payload.dict())
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/sec")
def sec():
    try:
        return SEC().status()
    except AttributeError:
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/source")
def source():
    return {"source": SOURCE_URL}


@app.get("/api")
def api_root():
    return {
        "ok": True,
        "name": "TradePilot AI",
        "version": "2.0",
        "endpoints": [
            "/api/health",
            "/api/scan",
            "/api/quote/{symbol}",
            "/api/news-discovery",
            "/api/issuance-discovery",
            "/api/backtest/{symbol}",
            "/api/validation/{symbol}",
            "/api/sentiment/{symbol}",
            "/api/learning/summary",
            "/api/learning/open-signals",
            "/api/learning/close-signal",
            "/api/sec",
            "/api/source",
        ],
    }
