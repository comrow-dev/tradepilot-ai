"""TradePilot SentiSense sentiment adapter.

Set SENTISENSE_API_KEY in the environment. Never store the API key in source.
"""
from __future__ import annotations
import os
from typing import Any, Dict, Optional
import requests

BASE_URL = "https://app.sentisense.ai/api/v1/stocks"
DEFAULT_TIMEOUT = 10

def _api_key() -> Optional[str]:
    return os.getenv("SENTISENSE_API_KEY")

def get_sentiment(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch SentiSense sentiment for a ticker; return None when unavailable."""
    symbol = (symbol or "").strip().upper()
    key = _api_key()
    if not symbol or not key:
        return None
    try:
        r = requests.get(
            f"{BASE_URL}/{symbol}/sentiment",
            headers={"X-SentiSense-API-Key": key},
            timeout=DEFAULT_TIMEOUT,
        )
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    try:
        payload = r.json()
    except ValueError:
        return None
    data = payload.get("data", payload)
    if not isinstance(data, dict):
        return None
    return {
        "symbol": symbol,
        "as_of": data.get("asOf"),
        "sentisense_score": data.get("sentisenseScore"),
        "sentisense_score_avg30d": data.get("sentisenseScoreAvg30d"),
        "sentisense_score_delta30d": data.get("sentisenseScoreDelta30d"),
        "score_label": data.get("scoreLabel"),
        "direction": data.get("direction"),
        "latest_direction": data.get("latestDirection"),
        "trend": data.get("trend"),
        "mentions": data.get("mentions"),
        "mentions_avg30d": data.get("mentionsAvg30d"),
        "social_dominance": data.get("socialDominance"),
        "by_source": data.get("bySource", []),
        "related_tickers": data.get("relatedTickers", []),
        "drivers": data.get("drivers", []),
        "narrative": data.get("narrative"),
    }
