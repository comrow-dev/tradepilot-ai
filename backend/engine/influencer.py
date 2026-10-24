from __future__ import annotations

import os
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup


# TradePilot public web/influencer signal collector.
# It only reads public webpages and does not bypass logins, paywalls,
# CAPTCHAs or other access controls.
USER_AGENT = os.getenv(
    "TRADEPILOT_USER_AGENT",
    "TradePilotAI/1.0 (+public-market-research)",
)

# Public sources chosen for the first live integration.
# These are deliberately public pages rather than private/social feeds.
DEFAULT_SOURCES = [
    "https://tradevenue.se/aktiebloggare",
    "https://tradevenue.se/aktietips",
    "https://hernhag.se/category/aktietips/",
    "https://samuelssonsrapport.se/category/aktier-guider/",
    "https://www.stockrobber.com/",
    "https://aktiefeed.se/",
]

SOURCE_NAMES = {
    "https://tradevenue.se/aktiebloggare": "TradeVenue – aktiebloggare",
    "https://tradevenue.se/aktietips": "TradeVenue – aktietips",
    "https://hernhag.se/category/aktietips/": "Marcus Hernhag",
    "https://samuelssonsrapport.se/category/aktier-guider/": "Samuelssons Rapport",
    "https://www.stockrobber.com/": "Stockrobber",
    "https://aktiefeed.se/": "AktieFeed",
}

POSITIVE_WORDS = {
    "köp", "köpvärd", "köpläge", "köper", "köpte", "köpt",
    "bullish", "hausse", "uppsida", "rally", "breakout",
    "stiger", "stiga", "stark", "starkt", "positiv", "positivt",
    "potential", "potentialen", "raket", "intressant", "favorit",
    "aktiefynd", "köpläge", "köptips",
}

NEGATIVE_WORDS = {
    "sälj", "säljläge", "säljer", "sålde", "bearish", "svag",
    "svagt", "negativ", "negativt", "rasar", "ras", "nedgång",
    "risk", "övervärderad", "varning", "avstår", "säljorder",
}

# 2–6 letters catches most common US/Swedish ticker formats while
# avoiding ordinary words as much as possible.
TICKER_RE = re.compile(
    r"(?<![A-Za-zÅÄÖåäö])\$?([A-ZÅÄÖ]{2,6})(?![A-Za-zÅÄÖåäö])"
)


def _fetch(url: str, timeout: int = 12) -> str:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


def _sentiment(text: str) -> float:
    words = re.findall(r"[A-Za-zÅÄÖåäö]+", text.lower())
    pos = sum(w in POSITIVE_WORDS for w in words)
    neg = sum(w in NEGATIVE_WORDS for w in words)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def _context_sentiment(text: str, start: int, end: int, window: int = 450) -> float:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return _sentiment(text[left:right])


def extract_signals(
    html: str,
    source_url: str,
    source_name: str | None = None,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = " ".join(soup.stripped_strings)

    signals: list[dict[str, Any]] = []
    seen: set[str] = set()
    now = int(time.time())

    for match in TICKER_RE.finditer(text):
        ticker = match.group(1).upper()

        # Avoid common uppercase words that are not useful ticker signals.
        if ticker in {
            "THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT",
            "SOM", "DET", "ATT", "OCH", "MED", "FÖR", "TILL",
            "ELLER", "DEN", "DOM", "HAR", "HAD", "ALL", "NEW",
            "USA", "USD", "SEK", "EUR", "CEO", "IPO", "AI",
        }:
            continue

        key = ticker
        if key in seen:
            continue
        seen.add(key)

        sentiment = _context_sentiment(
            text,
            match.start(),
            match.end(),
        )

        signals.append(
            {
                "ticker": ticker,
                "source": source_name or SOURCE_NAMES.get(source_url, source_url),
                "url": source_url,
                "sentiment_score": sentiment,
                "signal_type": "public_web_influencer_mention",
                "collected_at": now,
            }
        )

    return signals


def scan_sources(
    sources: list[str] | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for url in sources or DEFAULT_SOURCES:
        try:
            html = _fetch(url)
            results.extend(
                extract_signals(
                    html,
                    url,
                    SOURCE_NAMES.get(url),
                )
            )
        except Exception as exc:
            results.append(
                {
                    "source": SOURCE_NAMES.get(url, url),
                    "url": url,
                    "signal_type": "source_error",
                    "error": str(exc),
                }
            )

    return results


def build_signal_map(
    signals: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for signal in signals:
        ticker = str(signal.get("ticker") or "").upper().strip()
        if ticker:
            grouped.setdefault(ticker, []).append(signal)

    output: dict[str, dict[str, Any]] = {}

    for ticker, items in grouped.items():
        valid = [
            item for item in items
            if item.get("signal_type") == "public_web_influencer_mention"
        ]

        if not valid:
            continue

        avg = sum(
            float(item.get("sentiment_score", 0))
            for item in valid
        ) / len(valid)

        output[ticker] = {
            "ticker": ticker,
            "influencer_sentiment_score": round(avg, 3),
            "mentions": len(valid),
            "source_count": len(
                {str(item.get("source")) for item in valid}
            ),
            "sources": valid[:10],
        }

    return output


def influencer_signal_for_ticker(
    ticker: str,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    ticker = ticker.upper().strip()
    signals = [
        s for s in scan_sources(sources)
        if s.get("ticker") == ticker
    ]

    if not signals:
        return {
            "ticker": ticker,
            "influencer_sentiment_score": 0.0,
            "mentions": 0,
            "source_count": 0,
            "sources": [],
        }

    return build_signal_map(signals).get(
        ticker,
        {
            "ticker": ticker,
            "influencer_sentiment_score": 0.0,
            "mentions": 0,
            "source_count": 0,
            "sources": [],
        },
    )


if __name__ == "__main__":
    import json
    print(
        json.dumps(
            scan_sources(),
            ensure_ascii=False,
            indent=2,
        )
    )
