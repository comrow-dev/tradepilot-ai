import os
import re
from datetime import datetime, timezone
from functools import lru_cache

import requests
from bs4 import BeautifulSoup

SOURCE_URL = os.getenv(
    "DAYTRADING_SOURCE_URL",
    "https://www.daytrading.se/varldensbastaaktier",
)

POSITIVE_TERMS = (
    "köp", "köpläge", "köpvärd", "positiv", "uppsida", "bullish",
    "stark", "potential", "vinnare", "tillväxt", "momentum",
)
NEGATIVE_TERMS = (
    "sälj", "svag", "risk", "övervärderad", "bearish", "nedgång",
    "pressad", "varning",
)

def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip()

def _fetch():
    r = requests.get(
        SOURCE_URL,
        headers={"User-Agent": "TradePilotAI/1.0"},
        timeout=15,
    )
    r.raise_for_status()
    return r.text

@lru_cache(maxsize=1)
def fetch_daytrading_source():
    """Hämtar sidan en gång per process och returnerar ett neutralt expertunderlag."""
    html = _fetch()
    soup = BeautifulSoup(html, "html.parser")
    title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    headings = [_clean(x.get_text(" ", strip=True)) for x in soup.find_all(["h1", "h2", "h3"])]
    text = _clean(soup.get_text(" ", strip=True))

    # Behåll sidan som källa men försök inte hitta på ett företagsnamn.
    experts = []
    for h in headings:
        if len(h) > 2 and len(h) < 120:
            experts.append(h)

    return {
        "title": title,
        "headings": headings[:80],
        "text": text[:50000],
        "source_url": SOURCE_URL,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "experts": experts[:30],
    }

def get_daytrading_signal(symbol, company_name=None):
    """
    Separat expertlager.
    Returnerar expert_score 0..100 men ersätter aldrig TradePilots score.
    """
    base = {
        "source": "Daytrading.se",
        "symbol": symbol,
        "available": False,
        "mentioned": False,
        "expert_score": 0,
        "signal": "NEUTRAL",
        "positive_hits": 0,
        "negative_hits": 0,
        "experts": [],
        "source_url": SOURCE_URL,
    }

    try:
        data = fetch_daytrading_source()
    except Exception as exc:
        base["error"] = str(exc)
        return base

    symbol_l = str(symbol or "").lower().strip()
    company_l = str(company_name or "").lower().strip()
    text = data.get("text", "").lower()
    terms = [x for x in (symbol_l, company_l) if x]

    mentioned = any(term and term in text for term in terms)
    if not mentioned:
        base.update({
            "available": True,
            "reason": "Aktien/företaget hittades inte tydligt i den hämtade artikeln.",
            "fetched_at": data.get("fetched_at"),
        })
        return base

    # Begränsa bedömningen till en lokal textzon runt första träffen.
    idx = next((text.find(t) for t in terms if t and text.find(t) >= 0), -1)
    zone = text[max(0, idx - 1800): idx + 2500] if idx >= 0 else text[:4000]

    pos = sum(zone.count(term) for term in POSITIVE_TERMS)
    neg = sum(zone.count(term) for term in NEGATIVE_TERMS)

    raw = 50 + (pos - neg) * 8
    score = max(0, min(100, raw))

    if score >= 65:
        signal = "POSITIV"
    elif score <= 35:
        signal = "NEGATIV"
    else:
        signal = "NEUTRAL"

    base.update({
        "available": True,
        "mentioned": True,
        "expert_score": score,
        "signal": signal,
        "positive_hits": pos,
        "negative_hits": neg,
        "experts": data.get("experts", [])[:10],
        "source_url": data.get("source_url"),
        "fetched_at": data.get("fetched_at"),
    })
    return base
