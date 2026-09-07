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
from backend.intelligence.collector import build_intelligence_payload


SECTOR_ETFS = {
    "Technology": "XLK",
    "Financials": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
}


# Mindre / mindre kända bolag.
# Detta är startuniversumet för discovery - inte en permanent favoritlista.
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
        "Technology": [
            "technology",
            "semiconductor",
            "software",
        ],
        "Financials": [
            "bank",
            "financial",
            "insurance",
        ],
        "Healthcare": [
            "healthcare",
            "biotech",
            "drug",
        ],
        "Energy": [
            "oil",
            "gas",
            "energy",
        ],
        "Industrials": [
            "industrial",
            "machinery",
            "aerospace",
        ],
        "Consumer Discretionary": [
            "retail",
            "automotive",
            "leisure",
        ],
        "Communication Services": [
            "media",
            "telecom",
        ],
        "Consumer Staples": [
            "food",
            "beverage",
            "household",
        ],
        "Utilities": [
            "utility",
        ],
        "Real Estate": [
            "real estate",
            "reit",
        ],
        "Materials": [
            "material",
            "chemical",
            "mining",
        ],
    }

    for sector, keys in mapping.items():
        if any(k in ind for k in keys):
            return sector

    return None


def timeframe_data(fh, symbol):
    out = {}

    for res, days in (
        ("D", 400),
        ("60", 60),
        ("15", 20),
    ):
        try:
            candles = fh.candles(symbol, res, days)
            out[res] = technical_snapshot(candles)
        except Exception:
            out[res] = {
                "available": False,
            }

    return out


def candidate(fh, symbol, market):
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

    fund = fundamental_snapshot(
        metrics,
        profile,
    )

    tfs = timeframe_data(
        fh,
        symbol,
    )

    tech = tfs.get(
        "D",
        {},
    )

    try:
        raw_news = fh.company_news(
            symbol,
            7,
        )
        news = news_catalysts(
            raw_news,
        )
    except Exception:
        news = []

    try:
        rec = fh.recommendation_trends(
            symbol
        )[:3]
    except Exception:
        rec = []

    try:
        insider = fh.insider_transactions(
            symbol
        )
    except Exception:
        insider = []

    # Daytrading.se är EN extern källa,
    # inte TradePilots beslutsmotor.
    try:
        dt = get_daytrading_signal(
            symbol,
            profile.get("name"),
        )
    except Exception:
        dt = {}

    # Ny globala intelligence-lagret.
    # Artiklar, influencers, nyheter och discovery
    # används som kontext och upptäckt.
    try:
        intelligence = build_intelligence_payload(
            symbol=symbol,
            max_items=50,
        )
    except Exception as exc:
        intelligence = {
            "ok": False,
            "symbol": symbol,
            "count": 0,
            "items": [],
            "errors": [
                {
                    "source": "TradePilot Intelligence",
                    "error": str(exc)[:300],
                }
            ],
            "source_summary": {},
        }

    sector = sector_from_profile(
        profile
    )

    sector_change = (
        market.get("sector_changes_pct") or {}
    ).get(sector)

    m = dict(market)
    m["sector"] = sector
    m["sector_strength"] = (
        float(sector_change)
        if sector_change is not None
        else 0
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
        "company_name": (
            profile.get("name")
            or symbol
        ),
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
            sum(
                value is not None
                for value in data_points
            )
            / len(data_points)
        ),
        "detected_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    # TradePilots egen scoringmotor
    # är fortfarande den som bestämmer signalen.
    result = score_candidate(c)

    for key in [
        "symbol",
        "company_name",
        "price",
        "change_pct",
        "volume",
        "technical",
        "timeframes",
        "fundamentals",
        "catalysts",
        "analyst_trends",
        "insider",
        "daytrading",
        "intelligence",
        "detected_at",
    ]:
        result[key] = c[key]

    result["market"] = m

    try:
        result["signal_id"] = record_signal(
            result
        )
    except Exception:
        result["signal_id"] = None

    return result


def scan_market(
    limit=25,
    universe_limit=None,
):
    # Standard: analysera 10 kandidater.
    # Kan ändras med TRADEPILOT_DEEP_LIMIT.
    deep_limit = int(
        os.getenv(
            "TRADEPILOT_DEEP_LIMIT",
            "10",
        )
    )

    deep_limit = max(
        1,
        min(deep_limit, 30),
    )

    # Använd eget universum om det finns i Render.
    symbols_env = os.getenv(
        "TRADEPILOT_SCAN_SYMBOLS",
        "",
    ).strip()

    if symbols_env:
        wanted = [
            symbol.strip().upper()
            for symbol in symbols_env.split(",")
            if symbol.strip()
        ]
    else:
        wanted = list(
            DEFAULT_SCAN_SYMBOLS
        )

    # Begränsa universum.
    if universe_limit:
        wanted = wanted[
            :int(universe_limit)
        ]

    if not wanted:
        return {
            "ok": False,
            "source": "TradePilot Intelligence",
            "count": 0,
            "results": [],
            "error": "Inget scan-universum.",
        }

    # Daglig rotation.
    # Vi väljer INTE dagens största uppgångar.
    day_key = int(
        datetime.now(
            timezone.utc
        ).strftime("%Y%m%d")
    )

    offset = (
        day_key % len(wanted)
    )

    ordered = (
        wanted[offset:]
        + wanted[:offset]
    )

    batch = ordered[
        :deep_limit
    ]

    fh = Finnhub()

    try:
        market = market_context(
            fh
        )
    except Exception:
        market = {
            "regime": "NEUTRAL",
            "sector_changes_pct": {},
        }

    results = []

    for symbol in batch:
        try:
            result = candidate(
                fh,
                symbol,
                market,
            )

            if result:
                results.append(
                    result
                )

        except Exception:
            # Ett dåligt API-svar ska inte
            # stoppa hela marknadsskanningen.
            continue

    results.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("confidence", 0),
        ),
        reverse=True,
    )

    return {
        "ok": True,
        "source": (
            "Finnhub + "
            "TradePilot Intelligence"
        ),
        "selection": (
            "curated small-cap rotation; "
            "not daily-mover ranking"
        ),
        "count": len(
            results[:limit]
        ),
        "results": results[:limit],
        "market": market,
        "scanned_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "universe_considered": len(
            wanted
        ),
        "deep_analyzed": len(
            batch
        ),
    }
