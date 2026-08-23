import os
import requests
import re
from datetime import datetime, timezone
from typing import List, Dict


ALPHA_KEY = os.getenv("ALPHAVANTAGE_API_KEY")

ALPHA_URL = "https://www.alphavantage.co/query"

# TradePilot ska leta efter mindre / mer spekulativa bolag.
# Detta är startuniversum och kommer senare att ersättas
# av automatisk upptäckt.
WATCHLIST = [
    "BBAI",
    "SOUN",
    "AI",
    "RXRX",
    "PLUG",
    "OPEN",
    "IONQ",
    "LUNR",
    "RKLB",
    "ASTS",
    "ACHR",
    "JOBY",
    "DNA",
    "EVGO",
    "LCID",
    "RIVN",
    "HIMS",
    "NU",
    "GRAB",
    "HOOD",
]


def number(value, default=0.0):
    try:
        return float(
            str(value)
            .replace("%", "")
            .replace(",", "")
            .replace("$", "")
        )
    except (TypeError, ValueError):
        return default


def alpha_quote(symbol):
    if not ALPHA_KEY:
        return None

    response = requests.get(
        ALPHA_URL,
        params={
            "function": "GLOBAL_QUOTE",
            "symbol": symbol,
            "apikey": ALPHA_KEY,
        },
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    return data.get("Global Quote", {})


def calculate_score(stock):
    price = number(stock.get("price"))
    change = number(stock.get("change_pct"))
    volume = number(stock.get("volume"))

    score = 0

    # Momentum
    if 3 <= change < 8:
        score += 20
    elif 8 <= change < 15:
        score += 24
    elif 15 <= change < 25:
        score += 18
    elif change >= 25:
        score += 8

    # Volym
    if volume >= 5_000_000:
        score += 20
    elif volume >= 1_000_000:
        score += 16
    elif volume >= 250_000:
        score += 10
    elif volume >= 50_000:
        score += 5

    # Låg aktiekurs är INTE automatiskt bra,
    # men kan vara intressant för vårt small-cap-universum.
    if 1 <= price <= 20:
        score += 10
    elif 20 < price <= 50:
        score += 5

    # Undvik att jaga extrema spikes
    if change > 40:
        score -= 15

    return max(0, min(100, score))


def detect_signal(score):
    if score >= 75:
        return "STARK KANDIDAT"
    elif score >= 60:
        return "BEVAKA"
    elif score >= 45:
        return "SVAG KANDIDAT"

    return "AVSTÅ"


def scan_small_caps():
    """
    Första versionen av TradePilot Small Cap Scanner.

    Målet är att senare kombinera:

    1. Pris
    2. Momentum
    3. Volym
    4. Nya listningar
    5. Kapitalanskaffningar
    6. Emissioner
    7. Insiderköp
    8. Nyheter
    9. Forumdiskussioner
    10. Social momentum

    Den här versionen bygger bara på marknadsdata.
    """

    results = []

    if not ALPHA_KEY:
        return {
            "ok": False,
            "error": "ALPHAVANTAGE_API_KEY saknas.",
            "results": [],
        }

    for symbol in WATCHLIST:

        try:
            quote = alpha_quote(symbol)

            if not quote:
                continue

            price = number(
                quote.get("05. price")
            )

            change = number(
                quote.get("10. change percent")
            )

            volume = number(
                quote.get("06. volume")
            )

            if price <= 0:
                continue

            stock = {
                "symbol": symbol,
                "price": price,
                "change_pct": change,
                "volume": int(volume),
                "detected_at": datetime.now(
                    timezone.utc
                ).isoformat(),
            }

            score = calculate_score(stock)

            stock["score"] = score
            stock["signal"] = detect_signal(score)

            results.append(stock)

        except Exception as error:

            print(
                f"TradePilot scanner error {symbol}: {error}"
            )

    results.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return {
        "ok": True,
        "scanner": "small-cap-v1",
        "scanned_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "count": len(results),
        "results": results[:50],
    }


if __name__ == "__main__":

    result = scan_small_caps()

    print(
        result
    )