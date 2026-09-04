from dataclasses import dataclass, asdict
from typing import Optional
import re


@dataclass
class Tip:
    symbol: str
    company: str
    source: str
    source_url: str
    author: str
    published_at: str
    headline: str
    tip_text: str
    tip_type: str
    target_price: Optional[float] = None


# Ord som hjälper TradePilot hitta aktietips
TIP_KEYWORDS = [
    "köp",
    "köpvärd",
    "köpläge",
    "köpråd",
    "intressant aktie",
    "favoritaktie",
    "potential",
    "uppsida",
    "riktkurs",
    "mål",
    "aktietips",
    "case",
]


# Ord som hjälper TradePilot hitta nyemissioner
EMISSION_KEYWORDS = [
    "nyemission",
    "emission",
    "företrädesemission",
    "riktad emission",
    "teckningskurs",
    "teckningsrätter",
    "teckna",
    "kapitalanskaffning",
]


def detect_tip_type(text: str) -> str:
    """
    Försöker avgöra vilken typ av finansiell signal texten innehåller.
    """

    text_lower = text.lower()

    if any(word in text_lower for word in EMISSION_KEYWORDS):
        return "nyemission"

    if any(word in text_lower for word in TIP_KEYWORDS):
        return "aktietips"

    return "nyhet"


def extract_target_price(text: str) -> Optional[float]:
    """
    Försöker hitta ett målpris/riktkurs i texten.

    Exempel:
    'riktkurs 125 kr'
    'mål 125 kronor'
    """

    patterns = [
        r"(?:riktkurs|målpris|mål)\s*(?:på|är)?\s*(\d+(?:[.,]\d+)?)\s*(?:kr|kronor)?",
        r"(\d+(?:[.,]\d+)?)\s*(?:kr|kronor)\s*(?:i\s*)?(?:riktkurs|mål)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            try:
                return float(match.group(1).replace(",", "."))
            except ValueError:
                pass

    return None


def create_tip(
    symbol: str,
    company: str,
    source: str,
    source_url: str,
    author: str,
    published_at: str,
    headline: str,
    tip_text: str,
) -> Tip:

    return Tip(
        symbol=symbol,
        company=company,
        source=source,
        source_url=source_url,
        author=author,
        published_at=published_at,
        headline=headline,
        tip_text=tip_text,
        tip_type=detect_tip_type(
            headline + " " + tip_text
        ),
        target_price=extract_target_price(
            headline + " " + tip_text
        ),
    )


def validate_tip(tip: Tip) -> dict:
    """
    Kontrollerar att tipset innehåller tillräckligt
    med information för AI-analysen.
    """

    warnings = []

    if not tip.symbol:
        warnings.append("Aktiesymbol saknas")

    if not tip.company:
        warnings.append("Bolagsnamn saknas")

    if not tip.source:
        warnings.append("Källa saknas")

    if not tip.tip_text:
        warnings.append("Själva tipset saknas")

    if not tip.source_url:
        warnings.append("Originalkälla saknas")

    return {
        "valid": len(warnings) == 0,
        "warnings": warnings,
        "tip": asdict(tip),
    }


def prepare_for_ai(tip: Tip) -> dict:
    """
    Förbereder informationen som senare skickas
    till TradePilots AI-analys.
    """

    return {
        "symbol": tip.symbol,
        "company": tip.company,
        "source": tip.source,
        "author": tip.author,
        "published_at": tip.published_at,
        "headline": tip.headline,
        "tip_text": tip.tip_text,
        "tip_type": tip.tip_type,
        "target_price": tip.target_price,
    }


if __name__ == "__main__":

    # TEST 1: vanligt aktietips
    tip1 = create_tip(
        symbol="TEST",
        company="Testbolaget",
        source="Metro Finans",
        source_url="https://example.com/test",
        author="Testprofil",
        published_at="2026-08-25",
        headline="Testbolaget har stor potential",
        tip_text="Aktien bedöms ha en uppsida och riktkurs 12 kr."
    )

    # TEST 2: nyemission
    tip2 = create_tip(
        symbol="EMIS",
        company="Emissionsbolaget",
        source="Finansnyheter",
        source_url="https://example.com/emission",
        author="Analytiker",
        published_at="2026-08-25",
        headline="Emissionsbolaget genomför nyemission",
        tip_text="Företrädesemission med teckningskurs 5 kr."
    )

    print("\n--- TEST 1: AKTIETIPS ---")
    print(validate_tip(tip1))
    print("\nAI-DATA:")
    print(prepare_for_ai(tip1))

    print("\n--- TEST 2: NYEMISSION ---")
    print(validate_tip(tip2))
    print("\nAI-DATA:")
    print(prepare_for_ai(tip2))
