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
from backend.engine.issuance_discovery import discover_issuance_candidates
from backend.engine.influencer import scan_sources, build_signal_map


# TradePilot ska i första hand leta efter mindre bolag och nya katalysatorer.
# Stora/ledande bolag ska inte dominera scan-resultatet.
DEFAULT_SCAN_SYMBOLS = [
    "BBAI", "KOD", "IMNM", "CRBU", "HUMA", "TARS", "NUTX", "PPBT",
    "BIAF", "SEPN", "NUVB", "AEHR", "GPRO", "EOSE", "LAB", "FET",
    "CDNA", "CARG", "PRAA", "MYRG", "MSGE", "ARLO", "RXRX",
    "ACHR", "LUNR", "ENVX", "SOUN", "JOBY", "ASTS", "ONDS",
    "CTM", "MVST", "OPTT", "CYN", "VERB", "ATNF", "TNXP",
    "FFIE", "MULN", "BBIG", "TTOO", "AULT", "SINT", "ILAG",
]

MIN_MARKET_CAP_M = float(os.getenv("TRADEPILOT_SCAN_MIN_MARKET_CAP_M", "2"))
MAX_MARKET_CAP_M = float(os.getenv("TRADEPILOT_SCAN_MAX_MARKET_CAP_M", "250"))
MIN_PRICE = float(os.getenv("TRADEPILOT_SCAN_MIN_PRICE", "0.50"))
MAX_PRICE = float(os.getenv("TRADEPILOT_SCAN_MAX_PRICE", "50"))
DEEP_LIMIT = int(os.getenv("TRADEPILOT_DEEP_LIMIT", "10"))
DISCOVERY_LIMIT = int(os.getenv("TRADEPILOT_DISCOVERY_LIMIT", "30"))

SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
}


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


def _market_cap(profile):
    try:
        value = float((profile or {}).get("marketCapitalization"))
        return value if value > 0 else None
    except (TypeError, ValueError):
        return None


def _is_excluded_company(profile):
    name = str((profile or {}).get("name") or "").upper()
    industry = str((profile or {}).get("finnhubIndustry") or "").lower()

    excluded_words = (
        " ETF", " TRUST", " FUND", " FUNDS", " MUTUAL",
        " BANK", " BANCORP", " INSURANCE", " CAPITAL MANAGEMENT",
        " ASSET MANAGEMENT", " INVESTMENT TRUST",
    )

    if any(word in f" {name}" for word in excluded_words):
        return True

    excluded_industries = (
        "banks", "regional banks", "diversified banks",
        "investment banking", "asset management",
        "insurance", "investment trusts",
    )

    return any(term in industry for term in excluded_industries)


def _small_cap_profile(fh, symbol):
    try:
        profile = fh.company_profile(symbol) or {}
    except Exception:
        return None

    if _is_excluded_company(profile):
        return None

    cap = _market_cap(profile)
    if cap is None:
        return None

    if cap < MIN_MARKET_CAP_M or cap > MAX_MARKET_CAP_M:
        return None

    return profile


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


def candidate(
    fh,
    symbol,
    market,
    discovered_news=None,
    profile=None,
    influencer=None,
):
    symbol = str(symbol or "").upper().strip()
    if not symbol:
        return None

    profile = profile if profile is not None else _small_cap_profile(fh, symbol)
    if not profile:
        return None

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

    if price < MIN_PRICE or price > MAX_PRICE:
        return None

    change = (price - prev) / prev * 100

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

    influencer = influencer or {
        "ticker": symbol,
        "influencer_sentiment_score": 0.0,
        "mentions": 0,
        "source_count": 0,
        "sources": [],
    }

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

    cap = _market_cap(profile)

    data_points = [
        price,
        prev,
        tech.get("rsi14"),
        tech.get("rvol20"),
        tech.get("atr14"),
        tech.get("trend"),
        fund.get("revenue_growth"),
        sector_change,
        cap,
    ]

    c = {
        "symbol": symbol,
        "company_name": profile.get("name") or symbol,
        "market_cap_m": cap,
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
        "influencer": influencer,
        "intelligence": intelligence,
        "data_completeness": (
            sum(value is not None for value in data_points) / len(data_points)
        ),
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }

    result = score_candidate(c)

    for key in [
        "symbol", "company_name", "market_cap_m", "price", "change_pct", "volume",
        "technical", "timeframes", "fundamentals", "catalysts",
        "analyst_trends", "insider", "daytrading", "influencer",
        "intelligence", "detected_at",
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


def _discovery_symbols(fh):
    symbols = []
    issuance = []
    news = []

    try:
        issuance = discover_issuance_candidates(
            days=7,
            limit=min(DISCOVERY_LIMIT, 50),
        ).get("results", []) or []
    except Exception:
        issuance = []

    try:
        news = discover_news_candidates(
            fh,
            days=2,
            limit=min(DISCOVERY_LIMIT, 50),
        ).get("results", []) or []
    except Exception:
        news = []

    for item in issuance + news:
        symbol = str(item.get("symbol") or "").upper().strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)

    return symbols, issuance, news


def scan_market(limit=25, universe_limit=None):
    limit = max(1, min(int(limit), 50))
    deep_limit = max(3, min(DEEP_LIMIT, 25))

    symbols_env = os.getenv("TRADEPILOT_SCAN_SYMBOLS", "").strip()

    if symbols_env:
        curated = [
            symbol.strip().upper()
            for symbol in symbols_env.split(",")
            if symbol.strip()
        ]
    else:
        curated = list(DEFAULT_SCAN_SYMBOLS)

    if universe_limit:
        curated = curated[:int(universe_limit)]

    fh = Finnhub()

    try:
        market = market_context(fh)
    except Exception:
        market = {"regime": "NEUTRAL", "sector_changes_pct": {}}

    discovered_symbols, issuance, discovered_news = _discovery_symbols(fh)

    # Fresh discovery first, curated list second.
    ordered = []
    for symbol in discovered_symbols + curated:
        if symbol not in ordered:
            ordered.append(symbol)

    fresh_count = len(discovered_symbols)
    if fresh_count < len(ordered):
        tail = ordered[fresh_count:]
        if tail:
            day_key = int(datetime.now(timezone.utc).strftime("%Y%m%d"))
            offset = day_key % len(tail)
            ordered = ordered[:fresh_count] + tail[offset:] + tail[:offset]

    filtered = []
    rejected = {
        "market_cap_missing": 0,
        "below_min_market_cap": 0,
        "above_max_market_cap": 0,
        "excluded_financial_vehicle": 0,
        "price_out_of_range": 0,
    }

    for symbol in ordered:
        if len(filtered) >= max(deep_limit * 3, 30):
            break

        try:
            profile = fh.company_profile(symbol) or {}

            if _is_excluded_company(profile):
                rejected["excluded_financial_vehicle"] += 1
                continue

            cap = _market_cap(profile)
            if cap is None:
                rejected["market_cap_missing"] += 1
                continue

            if cap < MIN_MARKET_CAP_M:
                rejected["below_min_market_cap"] += 1
                continue

            if cap > MAX_MARKET_CAP_M:
                rejected["above_max_market_cap"] += 1
                continue

            try:
                q = fh.quote(symbol)
                price = float(q.get("c") or 0)
                if price < MIN_PRICE or price > MAX_PRICE:
                    rejected["price_out_of_range"] += 1
                    continue
            except Exception:
                continue

            filtered.append((symbol, profile))
        except Exception:
            continue

    # Build a candidate universe first, then use company names + tickers to match
    # public web/influencer articles. This prevents the collector from guessing tickers
    # from random uppercase words and lets it discover mentions by company name.
    company_map = {symbol: profile for symbol, profile in filtered}
    try:
        influencer_raw = scan_sources(company_map=company_map, max_articles_per_source=12)
        influencer_by_symbol = build_signal_map(influencer_raw)
    except Exception:
        influencer_raw = []
        influencer_by_symbol = {}

    batch = filtered[:deep_limit]

    discovered_by_symbol = {}
    for item in discovered_news:
        symbol = str(item.get("symbol") or "").upper()
        if symbol:
            discovered_by_symbol.setdefault(symbol, []).append(item)

    results = []

    for symbol, profile in batch:
        try:
            result = candidate(
                fh,
                symbol,
                market,
                discovered_news=discovered_by_symbol.get(symbol),
                profile=profile,
                influencer=influencer_by_symbol.get(symbol),
            )
            if result:
                results.append(result)
        except Exception:
            continue

    results.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("confidence", 0),
            -float(x.get("market_cap_m") or MAX_MARKET_CAP_M),
        ),
        reverse=True,
    )

    return {
        "ok": True,
        "source": (
            "TradePilot Small-Cap Scanner + SEC Issuance Discovery + "
            "News Discovery + Public Influencer/Web Signals + Finnhub"
        ),
        "selection": (
            f"micro/small-cap operating companies; "
            f"market cap {MIN_MARKET_CAP_M:g}-{MAX_MARKET_CAP_M:g}M USD; "
            "fresh issuance/news candidates prioritized; banks/funds excluded"
        ),
        "filters": {
            "min_market_cap_m": MIN_MARKET_CAP_M,
            "max_market_cap_m": MAX_MARKET_CAP_M,
            "min_price": MIN_PRICE,
            "max_price": MAX_PRICE,
            "deep_limit": deep_limit,
        },
        "count": len(results[:limit]),
        "results": results[:limit],
        "market": market,
        "discovery": {
            "issuance_candidates": len(issuance),
            "news_candidates": len(discovered_news),
            "fresh_symbols": len(discovered_symbols),
            "influencer_mentions": len(
                [
                    x for x in influencer_raw
                    if x.get("signal_type") == "public_web_influencer_mention"
                ]
            ),
            "influencer_sources": len(
                {str(x.get("source")) for x in influencer_raw if x.get("source")}
            ),
        },
        "rejected": rejected,
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "universe_considered": len(ordered),
        "small_cap_candidates": len(filtered),
        "deep_analyzed": len(batch),
    }
