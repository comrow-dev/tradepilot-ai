import os
import requests
from datetime import datetime, timezone

from scoring import analyze


API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"


def scan_market():
    if not API_KEY:
        return {
            "ok": False,
            "error": "ALPHAVANTAGE_API_KEY saknas",
            "results": [],
        }

    response = requests.get(
        BASE_URL,
        params={
            "function": "TOP_GAINERS_LOSERS",
            "apikey": API_KEY,
        },
        timeout=30,
    )

    response.raise_for_status()

    data = response.json()

    candidates = []

    for stock in data.get("top_gainers", []):
        try:
            change = float(
                str(stock.get("change_percentage", "0"))
                .replace("%", "")
            )
        except (TypeError, ValueError):
            continue

        if 5 <= change <= 30:
            candidate = {
                "symbol": stock.get("ticker"),
                "price": stock.get("price"),
                "change_pct": change,
                "volume": stock.get("volume"),
                "detected_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

            candidates.append(
                analyze(candidate)
            )

    candidates.sort(
        key=lambda item: item.get("score", 0),
        reverse=True,
    )

    return {
        "ok": True,
        "scanned_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "count": len(candidates),
        "results": candidates[:50],
    }
