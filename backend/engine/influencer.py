from __future__ import annotations

import os
import re
import time
from typing import Any

import requests
from bs4 import BeautifulSoup


# TradePilot influencer/web signal collector.
# This module is intentionally conservative:
# - it collects public web pages only
# - it does not bypass logins, paywalls, CAPTCHAs, or access controls
# - it extracts ticker mentions and simple positive/negative language
# - it can be called by pipeline.py as an additional signal source

USER_AGENT = os.getenv(
    "TRADEPILOT_USER_AGENT",
    "TradePilotAI/1.0 (+public-market-research)",
)

DEFAULT_SOURCES = [
    # Add public Swedish sources here as they are verified/allowed.
    # Example:
    # "https://example.se/..."
]

POSITIVE_WORDS = {
    "köp", "köpvärd", "köpläge", "bullish", "hausse", "uppsida",
    "rally", "breakout", "stiger", "stiga", "stark", "starkt",
    "positiv", "positivt", "potential", "potentialen", "raket",
}

NEGATIVE_WORDS = {
    "sälj", "säljläge", "bearish", "svag", "svagt", "negativ",
    "negativt", "rasar", "ras", "nedgång", "risk", "övervärderad",
}

TICKER_RE = re.compile(r"(?<![A-Za-zÅÄÖåäö])\$?([A-ZÅÄÖ]{2,5})(?![A-Za-zÅÄÖåäö])")


def _fetch(url: str, timeout: int = 12) -> str:
    r = requests.get(
        url,
        headers={"User-Agent": USER_AGENT},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.text


def _sentiment(text: str) -> float:
    words = re.findall(r"[A-Za-zÅÄÖåäö]+", text.lower())
    pos = sum(w in POSITIVE_WORDS for w in words)
    neg = sum(w in NEGATIVE_WORDS for w in words)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)


def extract_signals(
    html: str,
    source_url: str,
    source_name: str | None = None,
) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = " ".join(soup.stripped_strings)
    score = _sentiment(text)

    tickers = []
    seen = set()
    for match in TICKER_RE.finditer(text):
        ticker = match.group(1)
        if ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)

    now = int(time.time())
    return [
        {
            "ticker": ticker,
            "source": source_name or source_url,
            "url": source_url,
            "sentiment_score": score,
            "signal_type": "web_influencer_mention",
            "collected_at": now,
        }
        for ticker in tickers
    ]


def scan_sources(sources: list[str] | None = None) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    for url in sources or DEFAULT_SOURCES:
        try:
            html = _fetch(url)
            results.extend(extract_signals(html, url))
        except Exception as exc:
            results.append(
                {
                    "source": url,
                    "signal_type": "source_error",
                    "error": str(exc),
                }
            )

    return results


def influencer_signal_for_ticker(
    ticker: str,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    ticker = ticker.upper()
    signals = [
        s for s in scan_sources(sources)
        if s.get("ticker") == ticker
    ]

    if not signals:
        return {
            "ticker": ticker,
            "influencer_sentiment_score": 0.0,
            "mentions": 0,
            "sources": [],
        }

    avg = sum(float(s.get("sentiment_score", 0)) for s in signals) / len(signals)

    return {
        "ticker": ticker,
        "influencer_sentiment_score": round(avg, 3),
        "mentions": len(signals),
        "sources": signals,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(scan_sources(), ensure_ascii=False, indent=2))
