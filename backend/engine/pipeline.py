from datetime import datetime, timezone
import os

from backend.engine.data import Finnhub
from backend.engine.technical import technical_snapshot
from backend.engine.intelligence import (
    market_regime,
    news_catalysts,
    fundamental_snapshot,
)
from backend.engine.scoring import score_candidate
from backend.engine.learning import record_signal
from backend.daytrading_source import get_daytrading_signal
from backend.engine.news_discovery import discover_news_candidates


SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
}


DEFAULT_SCAN_SYMBOLS = [
    "CDNA", "CARG", "MYRG", "MSGE", "NUTX",
    "PRAA", "FET", "GPRO", "EOSE", "LAB",
    "BIAF", "PPBT", "AEHR", "HIMX", "NTCT",
    "ARLO", "SEPN", "NUVB", "RXRX", "KOD",
    "IMNM", "CRBU", "HUMA", "TARS", "SOUN",
    "BBAI", "ACHR", "JOBY", "LUNR", "ENVX",
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

    try:
        candles = fh.candles(symbol, "D", 400)
        out["D"] = technical_snapshot(candles)
    except Exception:
        out["D"] = {"available": False}

    out["60"] = {"available": False, "deferred": True}
    out["15"] = {"available": False, "deferred": True}
    return out


def candidate(fh, symbol, market, discovered_news=None):
    q = fh.quote(symbol)

    price = q.get("c")
    prev = q.get("pc")

    if not price or not prev:
        return None

    try:
        price = float(price)
        prev = float(prev)
    except Exception:
        return None

    if price <= 0 or prev <= 0:
        return None

    change = (price - prev) / prev * 100

    try:
        profile = fh.company_profile(symbol)
    except Exception:
        profile = {}

    try:
        metrics = fh.metrics(symbol)
    except Exception:
        metrics = {}

    fund = fundamental_snapshot(metrics, profile)
    tfs = timeframe_data(fh, symbol)
    tech = tfs.get("D", {})

    try:
        raw_news = fh.company_news(symbol, 7)
        combined_news = list(discovered_news or []) + list(raw_news or [])
        news = news_catalysts(
            combined_news,
            price_change_pct=change,
            rvol=tech.get("rvol20"),
        )
    except Exception:
        news = list(discovered_news or [])

    try:
        rec = fh.recommendation_trends(symbol)[:3]
    except Exception:
        rec = []

    try:
        insider = fh.insider_transactions(symbol)
    except Exception:
        insider = []

    try:
        dt = get_daytrading_signal(symbol, profile.get("name"))
    except Exception:
        dt = {}

    intelligence = {
        "ok": False,
        "symbol": symbol,
        "count": 0,
        "items": [],
        "errors": [],
        "source_summary": {},
        "deferred": True,
    }

    sector = sector_from_profile(profile)
    sector_change = (market.get("sector_changes_pct") or {}).get(sector)

    m = dict(market)
    m["sector"] = sector
    m["sector_strength"] = (
        float(sector_change) if sector_change is not None else 0
    )

    data_points = [
        price,
        prev,
        tech.get("rsi14"),
        tech.get("rvol20"),
        tech.get("atr14"),
        tech.get("trend"),
        fund.get("revenue_growth"),
        sector_change,
    ]

    c = {
        "symbol": symbol,
        "company_name": profile.get("name") or symbol,
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
        "intelligence": intelligence,
        "data_completeness": (
            sum(value is not None for value in data_points) / len(data_points)
        ),
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }

    result = score_candidate(c)

    for key in [
        "symbol", "company_name", "price", "change_pct", "volume",
        "technical", "timeframes", "fundamentals", "catalysts",
        "analyst_trends", "insider", "daytrading", "intelligence",
        "detected_at",
    ]:
        result[key] = c[key]

    result["market"] = m

    if result.get("signal") in ("KÖPSETUP", "ÖVERVÄG"):
        try:
            result["signal_id"] = record_signal(result)
        except Exception:
            result["signal_id"] = None
    else:
        result["signal_id"] = None

    return result


def scan_market(limit=25, universe_limit=None):
    deep_limit = int(os.getenv("TRADEPILOT_DEEP_LIMIT", "3"))
    deep_limit = max(1, min(deep_limit, 30))

    symbols_env = os.getenv("TRADEPILOT_SCAN_SYMBOLS", "").strip()

    if symbols_env:
        wanted = [
            symbol.strip().upper()
            for symbol in symbols_env.split(",")
            if symbol.strip()
        ]
    else:
        wanted = list(DEFAULT_SCAN_SYMBOLS)

    if universe_limit:
        wanted = wanted[:int(universe_limit)]

    if not wanted:
        return {
            "ok": False,
            "source": "TradePilot Intelligence",
            "count": 0,
            "results": [],
            "error": "Inget scan-universum.",
        }

    day_key = int(datetime.now(timezone.utc).strftime("%Y%m%d"))
    offset = day_key % len(wanted)
    ordered = wanted[offset:] + wanted[:offset]
    batch = ordered[:deep_limit]

    fh = Finnhub()

    try:
        market = market_context(fh)
    except Exception:
        market = {"regime": "NEUTRAL", "sector_changes_pct": {}}

    # News Discovery is an additional candidate source.
    # It does not bypass the normal scoring/risk/volume rules.
    discovered_news = []
    try:
        discovery_limit = int(
            os.getenv("TRADEPILOT_NEWS_DISCOVERY_LIMIT", "2")
        )
        discovery_limit = max(0, min(discovery_limit, 5))

        if discovery_limit:
            discovery = discover_news_candidates(
                fh,
                days=2,
                limit=discovery_limit,
            )
            discovered_news = discovery.get("results", []) or []
    except Exception:
        discovered_news = []

    discovered_by_symbol = {}
    for item in discovered_news:
        symbol = str(item.get("symbol") or "").upper()
        if symbol:
            discovered_by_symbol.setdefault(symbol, []).append(item)

    results = []

    for symbol in batch:
        try:
            result = candidate(
                fh,
                symbol,
                market,
                discovered_news=discovered_by_symbol.get(symbol),
            )
            if result:
                results.append(result)
        except Exception:
            continue

    # Analyze discovered small-cap candidates through the exact same
    # pipeline as curated candidates, but avoid duplicates.
    existing_symbols = {
        str(x.get("symbol") or "").upper()
        for x in results
    }

    for item in discovered_news:
        symbol = str(item.get("symbol") or "").upper()

        if not symbol or symbol in existing_symbols:
            continue

        try:
            result = candidate(
                fh,
                symbol,
                market,
                discovered_news=[item],
            )
            if result:
                results.append(result)
                existing_symbols.add(symbol)
        except Exception:
            continue

    results.sort(
        key=lambda x: (x.get("score", 0), x.get("confidence", 0)),
        reverse=True,
    )

    return {
        "ok": True,
        "source": "Finnhub + TradePilot Intelligence + News Discovery",
        "selection": (
            "curated small-cap rotation plus news-discovered candidates"
        ),
        "count": len(results[:limit]),
        "results": results[:limit],
        "market": market,
        "news_discovery": {
            "enabled": True,
            "count": len(discovered_news),
            "symbols": [
                x.get("symbol")
                for x in discovered_news
            ],
        },
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "universe_considered": len(wanted),
        "deep_analyzed": len(batch),
    }
