"""TradePilot public web / influencer discovery.

Uses public Google News RSS searches to find recent articles from Swedish
investor/blogger sources. No login, CAPTCHA bypass or private content.
"""
from __future__ import annotations

import html
import os
import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests

USER_AGENT = os.getenv(
    "TRADEPILOT_USER_AGENT",
    "TradePilotAI/1.3 (+public-market-research)",
)

WEB_SOURCES = [
    ("TradeVenue", "tradevenue.se", "influencer", 1.00),
    ("Marcus Hernhag", "hernhag.se", "influencer", 1.15),
    ("Samuelssons Rapport", "samuelssonsrapport.se", "influencer", 1.00),
    ("AktieFeed", "aktiefeed.se", "influencer", 0.90),
    ("Stockrobber", "stockrobber.com", "influencer", 0.85),
    ("Placera", "placera.se", "market_expert", 0.90),
    ("Stockpicker", "stockpicker.se", "market_expert", 0.90),
    ("Aktiespararna", "aktiespararna.se", "market_expert", 0.90),
]

POSITIVE = {
    "köp", "köpvärd", "köpläge", "köper", "köptips", "köpsignal",
    "bullish", "hausse", "uppsida", "rally", "breakout", "stiger",
    "stark", "starkt", "positiv", "potential", "raket", "intressant",
    "favorit", "aktiefynd", "vändning", "case", "lovande", "trigger",
    "katalysator", "återhämtning",
}
NEGATIVE = {
    "sälj", "säljläge", "säljer", "bearish", "svag", "negativ", "rasar",
    "ras", "nedgång", "risk", "övervärderad", "varning", "avstår",
    "problem", "vinstvarning", "pressad", "osäker", "förlust", "skuld",
    "utspädning",
}
COMMON = {
    "THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "SOM", "DET",
    "ATT", "OCH", "MED", "FÖR", "TILL", "ELLER", "DEN", "DOM", "HAR",
    "NEW", "USA", "USD", "SEK", "EUR", "CEO", "IPO", "AI", "AB", "SA",
    "INC", "LTD", "PLC", "Q1", "Q2", "Q3", "Q4", "EBIT", "EPS", "ETF",
    "ESG", "MKR", "MSEK", "MIO", "LIVE", "NEWS", "STOCK", "MARKET",
    "NASDAQ", "NYSE", "AMEX", "OTC", "STO", "NGM", "PDF", "URL",
    "HTTP", "HTTPS", "AKTIE", "AKTIER", "BÖRS", "RAPPORT", "SVERIGE",
    "SWEDEN",
}

CASHTAG_RE = re.compile(r"\$([A-Z][A-Z0-9.-]{1,7})\b")
EXCHANGE_RE = re.compile(
    r"\b(?:NASDAQ|NYSE|AMEX|OTC|STO|NGM|XETRA)\s*[:/]\s*"
    r"([A-Z][A-Z0-9.-]{1,7})\b", re.I
)
PAREN_TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.-]{1,7})\)")

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "application/rss+xml, application/xml, text/xml, text/html;q=0.9,*/*;q=0.8",
})
_CACHE = {}
_CACHE_TTL = float(os.getenv("TRADEPILOT_WEB_DISCOVERY_TTL", "300"))


def _fetch(url: str, timeout: int = 12) -> str:
    now = time.monotonic()
    cached = _CACHE.get(url)
    if cached and now - cached[0] < _CACHE_TTL:
        return cached[1]
    response = _SESSION.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    text = response.text
    _CACHE[url] = (now, text)
    return text


def _clean(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sentiment(text: str) -> float:
    words = re.findall(r"[A-Za-zÅÄÖåäö]+", text.lower())
    pos = sum(w in POSITIVE for w in words)
    neg = sum(w in NEGATIVE for w in words)
    total = pos + neg
    return round((pos - neg) / total, 3) if total else 0.0


def _normalise(text: str) -> str:
    text = re.sub(r"[^a-z0-9åäö ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _symbol_aliases(symbol_rows):
    aliases = []
    for row in symbol_rows or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("displaySymbol") or "").upper().strip()
        name = str(row.get("description") or row.get("name") or "").strip()
        if not symbol or not name or len(name) < 4:
            continue
        if any(ch in symbol for ch in ("/", " ")):
            continue
        normal = _normalise(name)
        if len(normal) < 5:
            continue
        aliases.append((normal, symbol))
        if normal.endswith(" ab"):
            aliases.append((normal[:-3].strip(), symbol))
    aliases.sort(key=lambda x: len(x[0]), reverse=True)
    return aliases


def _extract_tickers(text: str, aliases):
    found = []
    seen = set()

    for regex in (CASHTAG_RE, EXCHANGE_RE, PAREN_TICKER_RE):
        for match in regex.finditer(text):
            ticker = match.group(1).upper().rstrip(".")
            if ticker in COMMON or ticker.isdigit() or ticker in seen:
                continue
            seen.add(ticker)
            found.append((ticker, match.start(1), match.end(1)))

    normal = _normalise(text)
    for alias, ticker in aliases:
        if ticker in seen or len(alias) < 5:
            continue
        pos = normal.find(alias)
        if pos >= 0:
            seen.add(ticker)
            found.append((ticker, pos, pos + len(alias)))

    return found


def _rss_items(xml_text: str, source_name: str, domain: str, weight: float):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title") or "")
        link = _clean(item.findtext("link") or "")
        description = _clean(item.findtext("description") or "")
        pub = _clean(item.findtext("pubDate") or "")
        if not title and not description:
            continue
        items.append({
            "source": source_name,
            "domain": domain,
            "weight": weight,
            "title": title,
            "url": link,
            "text": f"{title}. {description}".strip(),
            "published": pub,
        })
    return items


def _google_news_url(domain: str):
    query = quote_plus(
        f"site:{domain} (aktie OR aktier OR börs OR bolag OR köp OR analys)"
    )
    return (
        "https://news.google.com/rss/search?q=" + query
        + "&hl=sv&gl=SE&ceid=SE:sv"
    )


def discover_web_candidates(fh=None, max_items: int = 120):
    aliases = []
    symbol_errors = []

    if fh is not None:
        for exchange in ("US", "STO", "NGM"):
            try:
                aliases.extend(_symbol_aliases(fh.symbols(exchange)))
            except Exception as exc:
                symbol_errors.append({
                    "exchange": exchange,
                    "error": f"{type(exc).__name__}: {exc}",
                })

    results = []
    stats = []
    errors = list(symbol_errors)

    for source_name, domain, kind, weight in WEB_SOURCES:
        started = time.perf_counter()
        source_results = 0
        try:
            rss = _fetch(_google_news_url(domain))
            items = _rss_items(rss, source_name, domain, weight)

            for item in items:
                for ticker, start, end in _extract_tickers(item["text"], aliases):
                    context = item["text"][max(0, start - 250):min(len(item["text"]), end + 450)]
                    results.append({
                        "ticker": ticker,
                        "source": source_name,
                        "source_kind": kind,
                        "source_weight": weight,
                        "url": item["url"],
                        "title": item["title"][:300],
                        "sentiment_score": _sentiment(context),
                        "signal_type": "public_web_influencer_mention",
                        "context": context[:800],
                        "published": item["published"],
                        "collected_at": int(time.time()),
                    })
                    source_results += 1
                    if len(results) >= max_items:
                        break
                if len(results) >= max_items:
                    break

            stats.append({
                "source": source_name,
                "url": f"https://{domain}",
                "kind": kind,
                "articles_scanned": len(items),
                "signals": source_results,
                "seconds": round(time.perf_counter() - started, 2),
                "status": "ok",
                "method": "Google News RSS + company-name/ticker matching",
            })
        except Exception as exc:
            error = {
                "source": source_name,
                "url": f"https://{domain}",
                "kind": kind,
                "error": f"{type(exc).__name__}: {exc}",
            }
            errors.append(error)
            stats.append({
                **error,
                "articles_scanned": 0,
                "signals": 0,
                "seconds": round(time.perf_counter() - started, 2),
                "status": "error",
                "method": "Google News RSS",
            })

        if len(results) >= max_items:
            break

    unique = []
    seen = set()
    for row in results:
        key = (row.get("ticker"), row.get("url"), row.get("source"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)

    unique.sort(
        key=lambda x: (
            abs(float(x.get("sentiment_score") or 0)),
            float(x.get("source_weight") or 0),
        ),
        reverse=True,
    )

    return unique[:max_items], {
        "sources": stats,
        "errors": errors,
        "symbol_universe_aliases": len(aliases),
    }


def discover_explicit_tickers(fh=None, max_items: int = 120):
    rows, meta = discover_web_candidates(fh=fh, max_items=max_items)
    tickers = []
    for row in rows:
        ticker = str(row.get("ticker") or "").upper().strip()
        if ticker and ticker not in tickers and ticker not in COMMON:
            tickers.append(ticker)
    return tickers, rows, meta
