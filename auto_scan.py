import os
from datetime import datetime, timezone

import requests

from backend.daytrading_source import get_daytrading_signal
from backend.scoring import analyze

API_KEY = os.getenv("FINNHUB_API_KEY", "")
BASE_URL = "https://finnhub.io/api/v1"

def _request(path, params=None, timeout=15):
    if not API_KEY:
        raise RuntimeError("FINNHUB_API_KEY saknas")
    p = dict(params or {})
    p["token"] = API_KEY
    r = requests.get(f"{BASE_URL}{path}", params=p, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data["error"]))
    return data

def get_daily_volume(symbol):
    """Volym är ett extra datapunkt. Den får aldrig stoppa en kandidat från att visas."""
    try:
        now = int(datetime.now(timezone.utc).timestamp())
        data = _request("/stock/candle", {
            "symbol": symbol,
            "resolution": "D",
            "from": now - 7 * 86400,
            "to": now,
        }, timeout=10)
        volumes = data.get("v") or []
        return volumes[-1] if volumes else None
    except Exception:
        return None

def get_market_movers(direction="gainers"):
    """
    Finnhub har inte en universell top-gainers-endpoint i samma form som tidigare kod.
    Vi hämtar US-symboluniversum och kontrollerar ett begränsat antal quote-data.
    """
    symbols = _request("/stock/symbol", {"exchange": "US"})
    stocks = []

    for item in symbols[:80]:
        symbol = item.get("symbol")
        if not symbol:
            continue
        try:
            quote = _request("/quote", {"symbol": symbol}, timeout=8)
            price = quote.get("c")
            prev = quote.get("pc")
            if price is None or prev in (None, 0):
                continue
            change = (float(price) - float(prev)) / float(prev) * 100
            if direction == "gainers" and change <= 0:
                continue
            if direction == "losers" and change >= 0:
                continue
            stocks.append({
                "symbol": symbol,
                "company_name": item.get("description") or "",
                "last": price,
                "percent_change": change,
                "volume": get_daily_volume(symbol),
            })
        except Exception:
            continue

    stocks.sort(
        key=lambda x: x.get("percent_change", 0),
        reverse=(direction == "gainers"),
    )
    return stocks[:25]

def scan_market():
    candidates = []

    for stock in get_market_movers("gainers"):
        change = float(stock.get("percent_change", 0))
        # Behåll den konservativa ramen från projektet: +0 till +100%.
        if not (0 < change <= 100):
            continue

        candidate = {
            "symbol": stock["symbol"],
            "company_name": stock.get("company_name") or "",
            "price": stock.get("last"),
            "change_pct": change,
            "volume": stock.get("volume"),
            "detected_at": datetime.now(timezone.utc).isoformat(),
        }

        result = analyze(candidate)

        try:
            # EXTRA expertlager – påverkar inte TradePilots grundscore.
            result["daytrading"] = get_daytrading_signal(
                candidate.get("symbol"),
                candidate.get("company_name"),
            )
        except Exception as exc:
            result["daytrading"] = {
                "source": "Daytrading.se",
                "available": False,
                "error": str(exc),
                "expert_score": 0,
                "signal": "NEUTRAL",
                "mentioned": False,
            }

        result.update(candidate)
        candidates.append(result)

    candidates.sort(key=lambda item: item.get("score", 0), reverse=True)
    return {
        "ok": True,
        "source": "Finnhub",
        "count": len(candidates),
        "results": candidates,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
    }
