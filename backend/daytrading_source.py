import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

SOURCE_URL = "https://www.daytrading.se/varldensbastaaktier"
TAG_URL = "https://www.daytrading.se/tag/aktieraket/"

EXPERTS = [
    {
        "name": "Espen Teigland",
        "country": "Norge",
        "style": "momentum"
    },
    {
        "name": "Gary Brode",
        "country": "USA",
        "style": "growth"
    },
    {
        "name": "Mads Christiansen",
        "country": "Danmark",
        "style": "technology"
    },
    {
        "name": "Swen Lorenz",
        "country": "Tyskland",
        "style": "undervalued"
    },
    {
        "name": "Lars Tvede",
        "country": "Danmark",
        "style": "macro"
    },
    {
        "name": "Erik Bork",
        "country": "Danmark",
        "style": "analyst_consensus"
    },
    {
        "name": "Christian Jain Kongsted",
        "country": "Danmark",
        "style": "algorithmic"
    }
]


def fetch_daytrading_source(url=SOURCE_URL):
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={
                "User-Agent": "TradePilot-AI/1.0"
            }
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        title = soup.title.get_text(
            strip=True
        ) if soup.title else ""

        headings = []

        for tag in soup.find_all(
            ["h1", "h2", "h3"]
        ):
            text = tag.get_text(
                " ",
                strip=True
            )

            if text:
                headings.append(text)

        return {
            "ok": True,
            "source": "Daytrading.se",
            "url": url,
            "title": title,
            "headings": headings[:100],
            "experts": EXPERTS,
            "fetched_at": datetime.now(
                timezone.utc
            ).isoformat()
        }

    except Exception as exc:
        return {
            "ok": False,
            "source": "Daytrading.se",
            "url": url,
            "error": str(exc),
            "experts": EXPERTS,
            "headings": []
        }


def get_daytrading_signal(symbol):
    """
    Daytrading.se används som informationskälla.
    Den ska inte ensam skapa en köp/sälj-signal.
    """

    data = fetch_daytrading_source()

    if not data["ok"]:
        return {
            "source": "Daytrading.se",
            "symbol": symbol,
            "available": False,
            "score": 0,
            "signal": "NEUTRAL",
            "reason": data.get("error")
        }

    text = " ".join(
        data.get("headings", [])
    ).lower()

    symbol_lower = symbol.lower()

    mentioned = symbol_lower in text

    return {
        "source": "Daytrading.se",
        "symbol": symbol,
        "available": True,
        "mentioned": mentioned,
        "score": 1 if mentioned else 0,
        "signal": "POSITIV" if mentioned else "NEUTRAL",
        "experts": data["experts"],
        "source_url": SOURCE_URL,
        "fetched_at": data["fetched_at"]
    }


if __name__ == "__main__":
    import json

    print(
        json.dumps(
            fetch_daytrading_source(),
            ensure_ascii=False,
            indent=2
        )
    )
