import json
import os
from pathlib import Path

from backend.intelligence.sources import (
    collect_discovery,
    gdelt_search,
    rss_search,
)


BASE_DIR = Path(__file__).resolve().parents[1]
CONFIG_FILE = BASE_DIR / "config" / "influencers.json"


DEFAULT_RSS_FEEDS = [
    {
        "name": "SEC",
        "url": "https://www.sec.gov/news/pressreleases.rss",
    },
    {
        "name": "PR Newswire",
        "url": "https://www.prnewswire.com/rss/news-releases-list.rss",
    },
    {
        "name": "GlobeNewswire",
        "url": "https://www.globenewswire.com/RssFeed/subjectcode/20-Mergers%20and%20Acquisitions/feedTitle/Mergers%20and%20Acquisitions",
    },
]


GLOBAL_TOPICS = [
    "small cap stock",
    "micro cap stock",
    "undervalued small company",
    "hidden gem stock",
    "small company breakthrough",
    "small cap catalyst",
    "turnaround stock",
    "distressed company investment",
    "company restructuring stock",
    "new contract small cap",
    "major contract company shares",
    "acquisition takeover small cap",
    "strategic partnership small cap",
    "insider buying small cap",
    "institutional investor small cap",
    "activist investor small company",
    "biotech catalyst small cap",
    "biotech breakthrough company",
    "technology breakthrough small cap",
    "AI small cap",
    "defense small cap",
    "energy small cap",
    "mining small cap",
    "new technology company stock",
    "company debt restructuring",
    "company capital raise",
    "company financing small cap",
    "company turnaround investment",
]


DEFAULT_INFLUENCERS = [
    {
        "name": "Metro Finans",
        "type": "market_community",
        "country": "SE",
        "specialties": [
            "aktier",
            "trading",
            "teknisk analys",
            "fundamental analys",
            "makro",
            "småbolag",
        ],
        "weight": 1.0,
        "enabled": True,
    },
    {
        "name": "Professor Kalkyl",
        "type": "investor_analyst",
        "country": "SE",
        "specialties": [
            "small caps",
            "tillväxtbolag",
            "aktieanalys",
        ],
        "weight": 1.0,
        "enabled": True,
    },
    {
        "name": "Västkustinvesteraren",
        "type": "investor",
        "country": "SE",
        "specialties": [
            "aktier",
            "investeringar",
            "tillväxtbolag",
            "småbolag",
        ],
        "weight": 0.9,
        "enabled": True,
    },
    {
        "name": "Cornucopia",
        "type": "market_commentator",
        "country": "SE",
        "specialties": [
            "makro",
            "ekonomi",
            "börs",
            "samhällsekonomi",
        ],
        "weight": 0.9,
        "enabled": True,
    },
    {
        "name": "Nicklas Andersson / Investeraren",
        "type": "investor_commentator",
        "country": "SE",
        "specialties": [
            "aktier",
            "investeringar",
            "sparande",
            "bolag",
        ],
        "weight": 0.9,
        "enabled": True,
    },
    {
        "name": "Morgan Housel",
        "type": "investor_writer",
        "country": "US",
        "specialties": [
            "behavioral finance",
            "investing",
            "long term investing",
        ],
        "weight": 0.8,
        "enabled": True,
    },
    {
        "name": "Liz Ann Sonders",
        "type": "macro_strategist",
        "country": "US",
        "specialties": [
            "macro",
            "markets",
            "market data",
            "economy",
        ],
        "weight": 0.9,
        "enabled": True,
    },
    {
        "name": "Ben Carlson",
        "type": "investor_writer",
        "country": "US",
        "specialties": [
            "markets",
            "investing",
            "asset allocation",
            "behavior",
        ],
        "weight": 0.8,
        "enabled": True,
    },
    {
        "name": "Brian Feroldi",
        "type": "stock_analyst",
        "country": "US",
        "specialties": [
            "stocks",
            "fundamental analysis",
            "financial statements",
            "growth companies",
        ],
        "weight": 1.0,
        "enabled": True,
    },
    {
        "name": "Tadas Viskanta",
        "type": "financial_research_curator",
        "country": "US",
        "specialties": [
            "financial research",
            "markets",
            "investing",
            "research curation",
        ],
        "weight": 0.9,
        "enabled": True,
    },
]


def _load_config():
    if not CONFIG_FILE.exists():
        return {
            "influencers": DEFAULT_INFLUENCERS,
            "platforms": [],
        }

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)

        influencers = config.get(
            "influencers",
            DEFAULT_INFLUENCERS,
        )

        return {
            "influencers": influencers,
            "platforms": config.get("platforms", []),
        }

    except Exception:
        return {
            "influencers": DEFAULT_INFLUENCERS,
            "platforms": [],
        }


def _enabled_influencers():
    config = _load_config()

    result = []

    for person in config.get("influencers", []):
        if person.get("enabled", True):
            result.append(person)

    return result


def _normalise_influencer(person):
    name = (person.get("name") or "").strip()

    handle = (
        person.get("handle")
        or person.get("username")
        or ""
    ).strip()

    platform = (
        person.get("platform")
        or ""
    ).strip().lower()

    return {
        "name": name,
        "handle": handle,
        "platform": platform,
        "type": person.get("type", ""),
        "country": person.get("country", ""),
        "specialties": person.get("specialties", []),
        "weight": person.get("weight", 1.0),
    }


def collect_global_intelligence():
    """
    Collect broad market intelligence.

    This is discovery only.
    A mention is NOT treated as a buy signal.
    """

    items = []
    errors = []

    timespan = os.getenv(
        "TRADEPILOT_NEWS_TIMESPAN",
        "24h",
    )

    for topic in GLOBAL_TOPICS:
        try:
            found, error = gdelt_search(
                topic,
                maxrecords=15,
                timespan=timespan,
            )

            items.extend(found or [])

            if error:
                errors.append(
                    {
                        "source": "GDELT",
                        "topic": topic,
                        "error": error,
                    }
                )

        except Exception as exc:
            errors.append(
                {
                    "source": "GDELT",
                    "topic": topic,
                    "error": str(exc)[:300],
                }
            )

    return items, errors


def collect_rss_intelligence():
    """
    Collect official/company/news-release information.
    """

    items = []
    errors = []

    for feed in DEFAULT_RSS_FEEDS:
        try:
            found, error = rss_search(
                feed["url"],
                source_name=feed["name"],
                limit=30,
            )

            items.extend(found or [])

            if error:
                errors.append(
                    {
                        "source": feed["name"],
                        "error": error,
                    }
                )

        except Exception as exc:
            errors.append(
                {
                    "source": feed["name"],
                    "error": str(exc)[:300],
                }
            )

    return items, errors


def collect_influencer_intelligence():
    """
    Search around configured investors and market commentators.

    Influencer information is contextual evidence only.
    It does not override TradePilot's own scoring engine.
    """

    influencers = [
        _normalise_influencer(x)
        for x in _enabled_influencers()
    ]

    items = []
    errors = []

    if not influencers:
        return items, errors

    try:
        found, source_errors = collect_discovery(
            influencers=influencers,
            topics=[],
        )

        items.extend(found or [])
        errors.extend(source_errors or [])

    except Exception as exc:
        errors.append(
            {
                "source": "influencers",
                "error": str(exc)[:300],
            }
        )

    return items, errors


def collect_all_intelligence():
    """
    Main intelligence collector.

    Combines:
    - global market discovery
    - official/news sources
    - configured investors and commentators

    No source is allowed to directly create a BUY signal.
    """

    global_items, global_errors = (
        collect_global_intelligence()
    )

    rss_items, rss_errors = (
        collect_rss_intelligence()
    )

    influencer_items, influencer_errors = (
        collect_influencer_intelligence()
    )

    all_items = (
        global_items
        + rss_items
        + influencer_items
    )

    unique = {}

    for item in all_items:
        item_id = (
            item.get("id")
            or item.get("url")
            or item.get("title")
        )

        if not item_id:
            continue

        if item_id not in unique:
            unique[item_id] = item

    items = list(unique.values())

    errors = (
        global_errors
        + rss_errors
        + influencer_errors
    )

    return {
        "ok": True,
        "count": len(items),
        "items": items,
        "errors": errors,
        "influencers": [
            _normalise_influencer(x)
            for x in _enabled_influencers()
        ],
    }


def collect_for_symbol(symbol):
    """
    Symbol-specific intelligence search.

    Used when TradePilot wants to investigate
    a particular stock more deeply.
    """

    symbol = (symbol or "").strip().upper()

    if not symbol:
        return {
            "ok": False,
            "count": 0,
            "items": [],
            "errors": [
                "symbol saknas"
            ],
        }

    queries = [
        f'"{symbol}" stock',
        f'"{symbol}" shares',
        f'"{symbol}" company',
        f'"{symbol}" investor',
        f'"{symbol}" contract',
        f'"{symbol}" acquisition',
        f'"{symbol}" insider',
        f'"{symbol}" financing',
        f'"{symbol}" catalyst',
    ]

    items = []
    errors = []

    for query in queries:
        try:
            found, error = gdelt_search(
                query,
                maxrecords=15,
                timespan=os.getenv(
                    "TRADEPILOT_SYMBOL_TIMESPAN",
                    "72h",
                ),
            )

            items.extend(found or [])

            if error:
                errors.append(
                    {
                        "query": query,
                        "error": error,
                    }
                )

        except Exception as exc:
            errors.append(
                {
                    "query": query,
                    "error": str(exc)[:300],
                }
            )

    unique = {}

    for item in items:
        key = (
            item.get("url")
            or item.get("id")
            or item.get("title")
        )

        if key and key not in unique:
            unique[key] = item

    return {
        "ok": True,
        "symbol": symbol,
        "count": len(unique),
        "items": list(unique.values()),
        "errors": errors,
    }


def source_summary(items):
    """
    Summarise where the intelligence came from.
    """

    summary = {}

    for item in items or []:
        source = (
            item.get("source")
            or "unknown"
        )

        summary[source] = (
            summary.get(source, 0) + 1
        )

    return dict(
        sorted(
            summary.items(),
            key=lambda x: x[1],
            reverse=True,
        )
    )


def filter_recent(items, max_items=100):
    """
    Keep the collected intelligence compact
    before sending it to the AI analyzer.
    """

    if not items:
        return []

    # Sources already return recent material.
    # Preserve source order because it carries relevance
    # from the discovery engine.
    return list(items[:max_items])


def build_intelligence_payload(
    symbol=None,
    max_items=100,
):
    """
    Unified payload used by the intelligence analyzer.
    """

    if symbol:
        result = collect_for_symbol(symbol)
    else:
        result = collect_all_intelligence()

    items = filter_recent(
        result.get("items", []),
        max_items=max_items,
    )

    return {
        "ok": result.get("ok", False),
        "symbol": symbol,
        "count": len(items),
        "items": items,
        "errors": result.get("errors", []),
        "source_summary": source_summary(items),
        "principle": (
            "External sources provide context and discovery. "
            "They never directly create a TradePilot buy signal."
        ),
                }
