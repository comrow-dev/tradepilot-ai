import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone


SOURCE_URL = "https://www.daytrading.se/varldensbastaaktier/"
TAG_URL = "https://www.daytrading.se/tag/aktieraket/"

EXPERTS = [
    {"name": "Espen Teigland", "country": "Norge", "style": "momentum"},
    {"name": "Gary Brode", "country": "USA", "style": "growth"},
    {"name": "Mads Christiansen", "country": "Danmark", "style": "technology"},
    {"name": "Swen Lorenz", "country": "Tyskland", "style": "undervalued"},
    {"name": "Lars Tvede", "country": "Danmark", "style": "macro"},
    {"name": "Erik Bork", "country": "Danmark", "style": "analyst_consensus"},
    {"name": "Christian Jain Kongsted", "country": "Danmark", "style": "algorithmic"},
]


def _normalize(value):
    return " ".join(str(value or "").lower().split())


def fetch_daytrading_source(url=SOURCE_URL):
    try:
        response = requests.get(
            url,
            timeout=15,
            headers={"User-Agent": "TradePilot-AI/1.0"},
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        title = soup.title.get_text(strip=True) if soup.title else ""

        headings = []
        for tag in soup.find_all(["h1", "h2", "h3"]):
            text = tag.get_text(" ", strip=True)
            if text:
                headings.append(text)

        return {
            "ok": True,
            "source": "Daytrading.se",
            "url": url,
            "title": title,
            "headings": headings[:100],
            "experts": EXPERTS,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        return {
            "ok": False,
            "source": "Daytrading.se",
            "url": url,
            "error": str(exc),
            "experts": EXPERTS,
            "headings": [],
        }


def get_daytrading_signal(symbol, company_name=None):
    """
    Daytrading.se är en extern informationskälla.
    Den påverkar inte TradePilot-score eller trade-plan direkt.
    """

    data = fetch_daytrading_source()

    result = {
        "source": "Daytrading.se",
        "symbol": symbol,
        "company_name": company_name or "",
        "available": bool(data.get("ok")),
        "mentioned": False,
        "score": 0,
        "signal": "NEUTRAL",
        "experts": data.get("experts", EXPERTS),
        "source_url": SOURCE_URL,
        "fetched_at": data.get("fetched_at"),
    }

    if not data.get("ok"):
        result["reason"] = data.get("error")
        return result

    text = _normalize(
        " ".join(
            [data.get("title", "")]
            + data.get("headings", [])
        )
    )

    terms = []
    if symbol:
        terms.append(_normalize(symbol))
    if company_name:
        terms.append(_normalize(company_name))

    # Undvik tomma eller alltför korta söktermer.
    terms = [term for term in terms if len(term) >= 2]

    mentioned_term = next(
        (term for term in terms if term in text),
        None,
    )

    if mentioned_term:
        result["mentioned"] = True
        result["matched_term"] = mentioned_term
        result["score"] = 1
        result["signal"] = "POSITIV"

    return result


if __name__ == "__main__":
    import json
    print(
        json.dumps(
            fetch_daytrading_source(),
            ensure_ascii=False,
            indent=2,
        )
    )
