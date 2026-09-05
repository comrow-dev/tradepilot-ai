from datetime import datetime, timezone
import os
from backend.engine.data import Finnhub
from backend.engine.technical import technical_snapshot
from backend.engine.intelligence import market_regime, news_catalysts, fundamental_snapshot
from backend.engine.scoring import score_candidate
from backend.engine.learning import record_signal
from backend.daytrading_source import get_daytrading_signal

SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
}

DEFAULT_SCAN_SYMBOLS = [
    "NVDA","AMD","TSLA","AAPL","MSFT","AMZN","META","GOOGL","NFLX","AVGO",
    "PLTR","MU","AMAT","SMCI","CRWD","COIN","MSTR","JPM","XOM","LLY"
]

def market_context(fh):
    snap = fh.market_snapshot()
    ctx = market_regime(snap)
    sectors = {}
    for name, etf in SECTOR_ETFS.items():
        try:
            sectors[name] = fh.quote(etf).get("dp")
        except Exception:
            sectors[name] = None
    ctx["sector_changes_pct"] = sectors
    return ctx

def sector_from_profile(profile):
    ind = (profile or {}).get("finnhubIndustry", "").lower()
    mapping = {
        "Technology": ["technology", "semiconductor", "software"],
        "Financials": ["bank", "financial", "insurance"],
        "Healthcare": ["healthcare", "biotech", "drug"],
        "Energy": ["oil", "gas", "energy"],
        "Industrials": ["industrial", "machinery", "aerospace"],
        "Consumer Discretionary": ["retail", "automotive", "leisure"],
        "Communication Services": ["media", "telecom"],
        "Consumer Staples": ["food", "beverage", "household"],
        "Utilities": ["utility"],
        "Real Estate": ["real estate", "reit"],
        "Materials": ["material", "chemical", "mining"],
    }
    for sector, keys in mapping.items():
        if any(k in ind for k in keys):
            return sector
    return None

def timeframe_data(fh, symbol):
    out = {}
    for res, days in (("D", 400), ("60", 60), ("15", 20)):
        try:
            out[res] = technical_snapshot(fh.candles(symbol, res, days))
        except Exception:
            out[res] = {"available": False}
    return out

def candidate(fh, item, market):
    s = item.get("symbol")
    q = fh.quote(s)
    price = q.get("c")
    prev = q.get("pc")
    if not price or not prev or float(price) <= 0:
        return None

    change = (float(price) - float(prev)) / float(prev) * 100
    profile = fh.company_profile(s)
    metrics = fh.metrics(s)
    fund = fundamental_snapshot(metrics, profile)
    tfs = timeframe_data(fh, s)
    tech = tfs.get("D", {})
    news = news_catalysts(fh.company_news(s, 7))

    try:
        rec = fh.recommendation_trends(s)[:3]
    except Exception:
        rec = []

    try:
        insider = fh.insider_transactions(s)
    except Exception:
        insider = []

    dt = get_daytrading_signal(s, item.get("description"))
    sector = sector_from_profile(profile)
    sector_change = (market.get("sector_changes_pct") or {}).get(sector)

    m = dict(market)
    m["sector"] = sector
    m["sector_strength"] = float(sector_change) if sector_change is not None else 0

    data_points = [
        price, prev, tech.get("rsi14"), tech.get("rvol20"),
        fund.get("revenue_growth"), sector_change
    ]

    c = {
        "symbol": s,
        "company_name": item.get("description") or profile.get("name") or s,
        "price": price,
        "change_pct": change,
        "volume": q.get("v"),
        "technical": tech,
        "timeframes": tfs,
        "fundamentals": fund,
        "market": m,
        "catalysts": news,
        "analyst_trends": rec,
        "insider": insider,
        "daytrading": dt,
        "data_completeness": sum(v is not None for v in data_points) / len(data_points),
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }

    result = score_candidate(c)
    for k in [
        "symbol","company_name","price","change_pct","volume","technical",
        "timeframes","fundamentals","catalysts","analyst_trends","insider",
        "daytrading","detected_at"
    ]:
        result[k] = c[k]
    result["market"] = m
    result["signal_id"] = record_signal(result)
    return result

def scan_market(limit=25, universe_limit=None):
    deep_limit = min(max(1, limit), int(os.getenv("TRADEPILOT_DEEP_LIMIT", "2")))

    symbols_env = os.getenv("TRADEPILOT_SCAN_SYMBOLS", "").strip()
    wanted = (
        [s.strip().upper() for s in symbols_env.split(",") if s.strip()]
        if symbols_env else DEFAULT_SCAN_SYMBOLS
    )
    wanted = wanted[:max(deep_limit * 5, 10)]

    fh = Finnhub()
    market = market_context(fh)

    try:
        available = {x.get("symbol"): x for x in fh.symbols("US")}
    except Exception:
        available = {}

    items = []
    for s in wanted:
        item = available.get(s, {"symbol": s, "description": s})
        try:
            q = fh.quote(s)
            c = q.get("c")
            pc = q.get("pc")
            if c and pc and float(c) > 1:
                change = (float(c) - float(pc)) / float(pc) * 100
                items.append((item, change))
        except Exception:
            continue

    movers = sorted(items, key=lambda x: x[1], reverse=True)[:deep_limit]

    results = []
    for item, _ in movers:
        try:
            r = candidate(fh, item, market)
            if r:
                results.append(r)
        except Exception:
            continue

    results.sort(
        key=lambda x: (x.get("score", 0), x.get("confidence", 0)),
        reverse=True
    )

    return {
        "ok": True,
        "source": "Finnhub",
        "count": len(results[:limit]),
        "results": results[:limit],
        "market": market,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "universe_considered": len(wanted),
        "prefiltered": len(movers),
    }
