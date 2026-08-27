import os
import requests
from datetime import datetime, timezone

from scoring import analyze

API_KEY = os.getenv("TWELVE_DATA_API_KEY")
BASE_URL = "https://api.twelvedata.com"


def get_market_movers(direction):
    if not API_KEY:
        return {
            "ok": False,
            "error": "TWELVE_DATA_API_KEY saknas",
            "results": [],
        }

    response = requests.get(
        f"{BASE_URL}/market_movers/stocks",
        params={
            "direction": direction,
            "outputsize": 50,
            "country": "USA",
            "apikey": API_KEY,
        },
        timeout=30,
    )

    response.raise_for_status()
    data = response.json()

    if data.get("status") == "error":
        return {
            "ok": False,
            "error": data.get("message", "Twelve Data API-fel"),
            "results": [],
        }

    return data.get("values", [])


def scan_market():
    if not API_KEY:
        return {
            "ok": False,
            "error": "TWELVE_DATA_API_KEY saknas",
            "results": [],
        }

    try:
        gainers = get_market_movers("gainers")

        candidates = []
        seen = set()

        for stock in gainers:
            try:
                change = float(stock.get("percent_change", 0))
            except (TypeError, ValueError):
                continue

            ticker = stock.get("symbol")

            if not ticker or ticker in seen:
                continue

            # Endast positiva rörelser upp till 100 %.
            if 0 < change <= 100:
                seen.add(ticker)

                candidate = {
                    "symbol": ticker,
                    "price": stock.get("last"),
                    "change_pct": change,
                    "volume": stock.get("volume"),
                    "detected_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }

                candidates.append(analyze(candidate))

        candidates.sort(
            key=lambda item: item.get("score", 0),
            reverse=True,
        )

        return {
            "ok": True,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "count": len(candidates),
            "results": candidates[:50],
        }

    except Exception as error:
        return {
            "ok": False,
            "error": str(error),
            "results": [],
        }


def auto_scan_market():
    return scan_market()
