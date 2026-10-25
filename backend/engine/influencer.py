from __future__ import annotations

import html as html_lib
import os
import re
import time
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = os.getenv(
    "TRADEPILOT_USER_AGENT",
    "TradePilotAI/1.2 (+public-market-research)",
)

# Public sources only. No login, paywall, CAPTCHA or access-control bypassing.
# The list deliberately mixes Swedish investor/blogger sources with broader
# market-analysis sources. A source is never treated as a trading instruction.
SOURCE_CONFIG = [
    {
        "url": "https://tradevenue.se/aktietips",
        "name": "TradeVenue – aktietips/aktiebloggare",
        "kind": "influencer",
        "weight": 1.00,
    },
    {
        "url": "https://hernhag.se/category/aktietips/",
        "name": "Marcus Hernhag",
        "kind": "influencer",
        "weight": 1.15,
    },
    {
        "url": "https://samuelssonsrapport.se/category/aktier-guider/",
        "name": "Samuelssons Rapport",
        "kind": "influencer",
        "weight": 1.00,
    },
    {
        "url": "https://www.stockblogs.se/bloggar/",
        "name": "StockBlogs – aktiebloggar",
        "kind": "influencer_directory",
        "weight": 0.85,
    },
    {
        "url": "https://aktiefeed.se/",
        "name": "AktieFeed",
        "kind": "influencer",
        "weight": 0.85,
    },
    {
        "url": "https://www.stockrobber.com/",
        "name": "Stockrobber",
        "kind": "influencer",
        "weight": 0.85,
    },
    {
        "url": "https://www.placera.se/",
        "name": "Placera",
        "kind": "market_expert",
        "weight": 0.90,
    },
    {
        "url": "https://www.stockpicker.se/aktier",
        "name": "Stockpicker",
        "kind": "market_expert",
        "weight": 0.90,
    },
]

DEFAULT_SOURCES = [x["url"] for x in SOURCE_CONFIG]
SOURCE_NAMES = {x["url"]: x["name"] for x in SOURCE_CONFIG}
SOURCE_KINDS = {x["url"]: x["kind"] for x in SOURCE_CONFIG}
SOURCE_WEIGHTS = {x["url"]: x["weight"] for x in SOURCE_CONFIG}

POSITIVE_WORDS = {
    "köp", "köpvärd", "köpläge", "köper", "köpte", "köpt", "köptips",
    "köpsignal", "köpläge", "bullish", "hausse", "uppsida", "rally",
    "breakout", "stiger", "stiga", "stark", "starkt", "positiv", "positivt",
    "potential", "potentialen", "raket", "intressant", "favorit", "aktiefynd",
    "vändning", "case", "lovande", "trigger", "katalysator", "återhämtning",
}

NEGATIVE_WORDS = {
    "sälj", "säljläge", "säljer", "sålde", "bearish", "svag", "svagt",
    "negativ", "negativt", "rasar", "ras", "nedgång", "risk", "övervärderad",
    "varning", "avstår", "säljorder", "problem", "vinstvarning", "pressad",
    "osäker", "osäkerhet", "förlust", "skuld", "utspädning",
}

TICKER_RE = re.compile(
    r"(?:(?:NASDAQ|NYSE|AMEX|OTC|STO|NGM|XETRA)\s*[:/]\s*|\$)"
    r"([A-Z][A-Z0-9.-]{1,7})\b"
)
BARE_TICKER_RE = re.compile(
    r"(?<![A-Za-zÅÄÖåäö])([A-ZÅÄÖ][A-Z0-9ÅÄÖ.-]{1,6})"
    r"(?![A-Za-zÅÄÖåäö])"
)

COMMON_WORDS = {
    "THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "SOM", "DET", "ATT",
    "OCH", "MED", "FÖR", "TILL", "ELLER", "DEN", "DOM", "HAR", "HAD", "ALL",
    "NEW", "USA", "USD", "SEK", "EUR", "CEO", "IPO", "AI", "AB", "SA", "INC",
    "LTD", "PLC", "Q1", "Q2", "Q3", "Q4", "EBIT", "EPS", "ETF", "ESG", "MKR",
    "MSEK", "MN", "MIO", "MILJ", "LIVE", "NEWS", "STOCK", "MARKET", "NASDAQ",
    "NYSE", "AMEX", "OTC", "STO", "NGM", "XETRA", "PDF", "URL", "HTTPS", "HTTP",
    "READ", "MORE", "BLOG", "AKTIE", "AKTIER", "BÖRS", "RAPPORT",
}

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
})


_HTML_CACHE: dict[str, tuple[float, str]] = {}
HTML_CACHE_TTL = float(os.getenv("TRADEPILOT_WEB_CACHE_TTL", "180"))

def _fetch(url: str, timeout: int = 15) -> str:
    now = time.monotonic()
    cached = _HTML_CACHE.get(url)
    if cached and now - cached[0] < HTML_CACHE_TTL:
        return cached[1]

    response = _SESSION.get(url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    html = response.text
    _HTML_CACHE[url] = (now, html)
    return html


def _sentiment(text: str) -> float:
    words = re.findall(r"[A-Za-zÅÄÖåäö]+", text.lower())
    pos = sum(w in POSITIVE_WORDS for w in words)
    neg = sum(w in NEGATIVE_WORDS for w in words)
    total = pos + neg
    return round((pos - neg) / total, 3) if total else 0.0


def _context_sentiment(text: str, start: int, end: int, window: int = 700) -> float:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return _sentiment(text[left:right])


def _normalise_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9åäö ]+", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def _company_aliases(company_map: dict[str, Any] | None):
    aliases = []
    for ticker, value in (company_map or {}).items():
        profile = value if isinstance(value, dict) else {"name": value}
        name = str(profile.get("name") or "").strip()
        if not name:
            continue
        normal = _normalise_name(name)
        if len(normal) >= 4:
            aliases.append((normal, ticker.upper()))
            if normal.endswith(" ab"):
                aliases.append((normal[:-3].strip(), ticker.upper()))
    return sorted(aliases, key=lambda x: len(x[0]), reverse=True)


def _extract_article_links(base_url: str, html: str, limit: int = 20):
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.lower()
    scored = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue

        url = urljoin(base_url, href).split("#", 1)[0]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != host:
            continue
        if url in seen or url.rstrip("/") == base_url.rstrip("/"):
            continue

        label = " ".join(a.stripped_strings).strip()
        path = parsed.path.lower()

        score = 0
        if any(k in path for k in (
            "/20", "/article", "/aktie", "/blog", "/nyhet", "/analys",
            "/inlagg", "/inlägg", "/kommentar", "/tips",
        )):
            score += 5
        if len(label) >= 30:
            score += 3
        if len(label) >= 50:
            score += 2
        if any(k in label.lower() for k in (
            "aktie", "rapport", "köp", "sälj", "analys", "bolag",
            "case", "tips", "portfölj",
        )):
            score += 2

        if score > 0:
            seen.add(url)
            scored.append((score, url))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [url for _score, url in scored[:limit]]


def _article_text(html: str):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    node = soup.find("article") or soup.find("main") or soup.body or soup
    text = " ".join(node.stripped_strings)
    return title, re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _find_tickers(text: str, company_map=None):
    found = []
    seen = set()

    for match in TICKER_RE.finditer(text):
        ticker = match.group(1).upper().rstrip(".")
        if ticker in COMMON_WORDS or ticker.isdigit():
            continue
        if ticker not in seen:
            seen.add(ticker)
            found.append((ticker, match.start(1), match.end(1)))

    normal_text = _normalise_name(text)
    for alias, ticker in _company_aliases(company_map):
        pos = normal_text.find(alias)
        if pos >= 0 and ticker not in seen:
            seen.add(ticker)
            found.append((ticker, pos, pos + len(alias)))

    allowed = {str(k).upper() for k in (company_map or {}).keys()}
    if allowed:
        for match in BARE_TICKER_RE.finditer(text):
            ticker = match.group(1).upper()
            if ticker in allowed and ticker not in seen and ticker not in COMMON_WORDS:
                seen.add(ticker)
                found.append((ticker, match.start(1), match.end(1)))

    return found


def extract_signals(
    html: str,
    source_url: str,
    source_name: str | None = None,
    company_map=None,
    article_url: str | None = None,
    article_title: str | None = None,
):
    title, text = _article_text(html)
    title = article_title or title
    if not text:
        return []

    config = next((x for x in SOURCE_CONFIG if x["url"] == source_url), {})
    source_name = source_name or config.get("name") or source_url
    kind = config.get("kind", "public_web")
    weight = float(config.get("weight", 1.0))
    target_url = article_url or source_url
    now = int(time.time())

    signals = []
    for ticker, start, end in _find_tickers(text, company_map):
        sentiment = _context_sentiment(text, start, end)
        context = text[max(0, start - 300): min(len(text), end + 300)]
        signals.append({
            "ticker": ticker,
            "source": source_name,
            "source_kind": kind,
            "source_weight": weight,
            "url": target_url,
            "title": title[:300],
            "sentiment_score": sentiment,
            "signal_type": "public_web_influencer_mention",
            "context": context[:800],
            "collected_at": now,
        })
    return signals


def scan_sources(
    sources: list[str] | None = None,
    company_map=None,
    max_articles_per_source: int = 12,
):
    results = []
    errors = []
    stats = []

    for source_url in sources or DEFAULT_SOURCES:
        source_name = SOURCE_NAMES.get(source_url, source_url)
        started = time.perf_counter()
        source_signals = 0
        article_count = 0

        try:
            html = _fetch(source_url)
            landing = extract_signals(
                html, source_url, source_name, company_map
            )
            results.extend(landing)
            source_signals += len(landing)

            links = _extract_article_links(
                source_url, html, max_articles_per_source
            )

            for article_url in links:
                try:
                    article_html = _fetch(article_url, timeout=12)
                    signals = extract_signals(
                        article_html,
                        source_url,
                        source_name,
                        company_map,
                        article_url=article_url,
                    )
                    results.extend(signals)
                    source_signals += len(signals)
                    article_count += 1
                except Exception:
                    continue

            stats.append({
                "source": source_name,
                "url": source_url,
                "kind": SOURCE_KINDS.get(source_url, "public_web"),
                "articles_scanned": article_count,
                "signals": source_signals,
                "seconds": round(time.perf_counter() - started, 2),
                "status": "ok",
            })

        except Exception as exc:
            error = {
                "source": source_name,
                "url": source_url,
                "kind": SOURCE_KINDS.get(source_url, "public_web"),
                "error": f"{type(exc).__name__}: {exc}",
            }
            errors.append(error)
            stats.append({
                **error,
                "articles_scanned": 0,
                "signals": 0,
                "seconds": round(time.perf_counter() - started, 2),
                "status": "error",
            })

    return results, {"sources": stats, "errors": errors}


def discover_explicit_tickers(
    sources: list[str] | None = None,
    max_articles_per_source: int = 8,
):
    """Cheap first pass used to seed the candidate universe from public web pages."""
    raw, meta = scan_sources(
        sources=sources,
        company_map=None,
        max_articles_per_source=max_articles_per_source,
    )
    tickers = []
    for item in raw:
        ticker = str(item.get("ticker") or "").upper().strip()
        if ticker and ticker not in COMMON_WORDS and ticker not in tickers:
            tickers.append(ticker)
    return tickers, raw, meta


def build_signal_map(signals):
    grouped = {}
    for signal in signals:
        ticker = str(signal.get("ticker") or "").upper().strip()
        if ticker and signal.get("signal_type") == "public_web_influencer_mention":
            grouped.setdefault(ticker, []).append(signal)

    output = {}
    for ticker, items in grouped.items():
        unique = []
        seen_urls = set()

        for item in items:
            url = str(item.get("url") or "")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            unique.append(item)

        if not unique:
            continue

        weights = [max(0.1, float(x.get("source_weight", 1.0))) for x in unique]
        sentiments = [float(x.get("sentiment_score", 0)) for x in unique]
        weighted_avg = sum(s * w for s, w in zip(sentiments, weights)) / sum(weights)

        source_names = []
        kinds = []
        for item in unique:
            source = str(item.get("source") or "")
            kind = str(item.get("source_kind") or "public_web")
            if source and source not in source_names:
                source_names.append(source)
            if kind not in kinds:
                kinds.append(kind)

        output[ticker] = {
            "ticker": ticker,
            "influencer_sentiment_score": round(weighted_avg, 3),
            "mentions": len(unique),
            "source_count": len(source_names),
            "sources": unique[:10],
            "source_names": source_names,
            "source_kinds": kinds,
        }

    return output


def influencer_signal_for_ticker(ticker, sources=None, company_map=None):
    ticker = ticker.upper().strip()
    raw, _meta = scan_sources(sources, company_map=company_map)
    signal_map = build_signal_map(raw)
    return signal_map.get(ticker, {
        "ticker": ticker,
        "influencer_sentiment_score": 0.0,
        "mentions": 0,
        "source_count": 0,
        "sources": [],
        "source_names": [],
        "source_kinds": [],
    })


if __name__ == "__main__":
    import json
    raw, meta = scan_sources()
    print(json.dumps({
        "signals": raw[:50],
        "meta": meta,
    }, ensure_ascii=False, indent=2))
