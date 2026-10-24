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
    "TradePilotAI/1.1 (+public-market-research)",
)

# Public pages only. No login/paywall/CAPTCHA bypassing.
DEFAULT_SOURCES = [
    "https://tradevenue.se/aktienyheter",
    "https://tradevenue.se/aktiebloggare",
    "https://hernhag.se/category/aktietips/",
    "https://samuelssonsrapport.se/category/aktier-guider/",
    "https://www.stockrobber.com/",
    "https://aktiefeed.se/",
]

SOURCE_NAMES = {
    "https://tradevenue.se/aktienyheter": "TradeVenue – aktienyheter",
    "https://tradevenue.se/aktiebloggare": "TradeVenue – aktiebloggare",
    "https://hernhag.se/category/aktietips/": "Marcus Hernhag",
    "https://samuelssonsrapport.se/category/aktier-guider/": "Samuelssons Rapport",
    "https://www.stockrobber.com/": "Stockrobber",
    "https://aktiefeed.se/": "AktieFeed",
}

POSITIVE_WORDS = {
    "köp", "köpvärd", "köpläge", "köper", "köpte", "köpt", "köptips",
    "bullish", "hausse", "uppsida", "rally", "breakout", "stiger", "stiga",
    "stark", "starkt", "positiv", "positivt", "potential", "potentialen",
    "raket", "intressant", "favorit", "aktiefynd", "vändning", "case",
}

NEGATIVE_WORDS = {
    "sälj", "säljläge", "säljer", "sålde", "bearish", "svag", "svagt",
    "negativ", "negativt", "rasar", "ras", "nedgång", "risk", "övervärderad",
    "varning", "avstår", "säljorder", "problem", "vinstvarning",
}

# Explicit ticker forms first; the bare-uppercase fallback is intentionally strict.
TICKER_RE = re.compile(
    r"(?:(?:NASDAQ|NYSE|AMEX|OTC|STO|NGM|XETRA)\s*[:/]\s*|\$)([A-Z][A-Z0-9.-]{1,7})\b"
)
BARE_TICKER_RE = re.compile(
    r"(?<![A-Za-zÅÄÖåäö])([A-ZÅÄÖ][A-Z0-9ÅÄÖ.-]{1,6})(?![A-Za-zÅÄÖåäö])"
)

COMMON_WORDS = {
    "THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "SOM", "DET", "ATT",
    "OCH", "MED", "FÖR", "TILL", "ELLER", "DEN", "DOM", "HAR", "HAD", "ALL",
    "NEW", "USA", "USD", "SEK", "EUR", "CEO", "IPO", "AI", "AB", "SA", "INC",
    "LTD", "PLC", "Q1", "Q2", "Q3", "Q4", "EBIT", "EPS", "ETF", "ESG", "MKR",
    "MSEK", "MN", "MIO", "MILJ", "LIVE", "NEWS", "STOCK", "MARKET", "NASDAQ",
    "NYSE", "AMEX", "OTC", "STO", "NGM", "XETRA", "PDF", "URL", "HTTPS", "HTTP",
}


def _fetch(url: str, timeout: int = 15) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"},
        timeout=timeout,
        allow_redirects=True,
    )
    response.raise_for_status()
    return response.text


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


def _company_aliases(company_map: dict[str, Any] | None) -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    for ticker, value in (company_map or {}).items():
        profile = value if isinstance(value, dict) else {"name": value}
        name = str(profile.get("name") or "").strip()
        if not name:
            continue
        normal = _normalise_name(name)
        if len(normal) >= 4:
            aliases.append((normal, ticker.upper()))
            # AB suffix is often omitted in articles.
            if normal.endswith(" ab"):
                aliases.append((normal[:-3].strip(), ticker.upper()))
    return sorted(aliases, key=lambda x: len(x[0]), reverse=True)


def _extract_article_links(base_url: str, html: str, limit: int = 20) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(base_url).netloc.lower()
    links: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "javascript:")):
            continue
        url = urljoin(base_url, href).split("#", 1)[0]
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or parsed.netloc.lower() != host:
            continue
        if url in seen or url == base_url:
            continue
        label = " ".join(a.stripped_strings).strip().lower()
        path = parsed.path.lower()
        # Prefer article-like links. Keep category pages as a fallback.
        looks_article = any(k in path for k in ("/20", "/article", "/aktie", "/blog", "/nyhet", "/analys", "/inlägg"))
        if looks_article or len(label) > 25:
            seen.add(url)
            links.append(url)
        if len(links) >= limit:
            break
    return links


def _article_text(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    # Article/main content gives better signal than a whole navigation page.
    node = soup.find("article") or soup.find("main") or soup.body or soup
    text = " ".join(node.stripped_strings)
    return title, re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _find_tickers(text: str, company_map: dict[str, Any] | None = None) -> list[tuple[str, int, int]]:
    found: list[tuple[str, int, int]] = []
    seen: set[str] = set()

    for match in TICKER_RE.finditer(text):
        ticker = match.group(1).upper().rstrip(".")
        if ticker in COMMON_WORDS or ticker.isdigit():
            continue
        if ticker not in seen:
            seen.add(ticker)
            found.append((ticker, match.start(1), match.end(1)))

    # Company-name matching is much safer than treating every uppercase word as a ticker.
    normal_text = _normalise_name(text)
    for alias, ticker in _company_aliases(company_map):
        pos = normal_text.find(alias)
        if pos >= 0 and ticker not in seen:
            seen.add(ticker)
            found.append((ticker, pos, pos + len(alias)))

    # Bare tickers are accepted only when a candidate universe is supplied.
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
    company_map: dict[str, Any] | None = None,
    article_url: str | None = None,
    article_title: str | None = None,
) -> list[dict[str, Any]]:
    title, text = _article_text(html)
    title = article_title or title
    if not text:
        return []

    signals: list[dict[str, Any]] = []
    now = int(time.time())
    target_url = article_url or source_url

    for ticker, start, end in _find_tickers(text, company_map):
        sentiment = _context_sentiment(text, start, end)
        context = text[max(0, start - 260): min(len(text), end + 260)]
        signals.append({
            "ticker": ticker,
            "source": source_name or SOURCE_NAMES.get(source_url, source_url),
            "url": target_url,
            "title": title[:300],
            "sentiment_score": sentiment,
            "signal_type": "public_web_influencer_mention",
            "context": context[:700],
            "collected_at": now,
        })
    return signals


def scan_sources(
    sources: list[str] | None = None,
    company_map: dict[str, Any] | None = None,
    max_articles_per_source: int = 12,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for source_url in sources or DEFAULT_SOURCES:
        source_name = SOURCE_NAMES.get(source_url, source_url)
        try:
            html = _fetch(source_url)
            # Parse the landing page itself first.
            results.extend(extract_signals(html, source_url, source_name, company_map))
            # Then inspect article links so a homepage mentioning many companies does not
            # become the only signal. This is the key difference from the old collector.
            for article_url in _extract_article_links(source_url, html, max_articles_per_source):
                try:
                    article_html = _fetch(article_url, timeout=12)
                    results.extend(
                        extract_signals(
                            article_html,
                            source_url,
                            source_name,
                            company_map,
                            article_url=article_url,
                        )
                    )
                except Exception:
                    continue
        except Exception as exc:
            results.append({
                "source": source_name,
                "url": source_url,
                "signal_type": "source_error",
                "error": str(exc),
            })
    return results


def build_signal_map(signals: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for signal in signals:
        ticker = str(signal.get("ticker") or "").upper().strip()
        if ticker and signal.get("signal_type") == "public_web_influencer_mention":
            grouped.setdefault(ticker, []).append(signal)

    output: dict[str, dict[str, Any]] = {}
    for ticker, items in grouped.items():
        # Distinct URLs prevent one page from being counted repeatedly.
        unique = []
        seen_urls = set()
        for item in items:
            url = str(item.get("url") or "")
            if url not in seen_urls:
                seen_urls.add(url)
                unique.append(item)

        avg = sum(float(x.get("sentiment_score", 0)) for x in unique) / len(unique)
        sources = {str(x.get("source")) for x in unique if x.get("source")}
        output[ticker] = {
            "ticker": ticker,
            "influencer_sentiment_score": round(avg, 3),
            "mentions": len(unique),
            "source_count": len(sources),
            "sources": unique[:10],
        }
    return output


def influencer_signal_for_ticker(ticker: str, sources: list[str] | None = None, company_map=None):
    ticker = ticker.upper().strip()
    signal_map = build_signal_map(scan_sources(sources, company_map=company_map))
    return signal_map.get(ticker, {
        "ticker": ticker,
        "influencer_sentiment_score": 0.0,
        "mentions": 0,
        "source_count": 0,
        "sources": [],
    })


if __name__ == "__main__":
    import json
    print(json.dumps(scan_sources(), ensure_ascii=False, indent=2))
