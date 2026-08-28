import os
import requests
from datetime import datetime, timezone

from backend.scoring import analyze


API_KEY = os.getenv("FINNHUB_API_KEY")
BASE_URL = "https://finnhub.io/api/v1"


def get_daily_volume(symbol):
    # Finnhub-kontot saknar åtkomst till /stock/candle.
    # Volym används inte längre som krav i scanningen.
    return None

def get_market_movers(direction):
    if not API_KEY:
        return {
            "ok": False,
            "error": "FINNHUB_API_KEY saknas",
            "results": [],
        }

    try:
        response = requests.get(
            f"{BASE_URL}/stock/symbol",
            params={
                "exchange": "US",
                "token": API_KEY,
            },
            timeout=30,
        )

        response.raise_for_status()
        symbols = response.json()

        stocks = []

        for item in symbols[:50]:
            symbol = item.get("symbol")

            if not symbol:
                continue

            try:
                quote_response = requests.get(
                    f"{BASE_URL}/quote",
                    params={
                        "symbol": symbol,
                        "token": API_KEY,
                    },
                    timeout=10,
                )

                quote_response.raise_for_status()
                quote = quote_response.json()

                change = float(quote.get("dp", 0))
                price = quote.get("c")

                if price is None:
                    continue

                if direction == "gainers" and change <= 0:
                    continue

                if direction == "losers" and change >= 0:
                    continue

                stocks.append({
                    "symbol": symbol,
                    "last": price,
                    "percent_change": change,
                    "volume": get_daily_volume(symbol),
                })

            except Exception:
                continue

        stocks.sort(
            key=lambda x: x.get("percent_change", 0),
            reverse=(direction == "gainers"),
        )

        return stocks[:50]

    except Exception as error:
        return {
            "ok": False,
            "error": str(error),
            "results": [],
        }


def scan_market():
    if not API_KEY:
        return {
            "ok": False,
            "error": "FINNHUB_API_KEY saknas",
            "results": [],
        }

    try:
        gainers = get_market_movers("gainers")

        if isinstance(gainers, dict):
            return gainers

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

            if 0 < change <= 100 and stock.get("last") is not None:
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
