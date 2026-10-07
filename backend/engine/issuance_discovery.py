"""
TradePilot AI - Issuance Discovery v10

Purpose
-------
Detect genuine aggregate/gross financing or offering amounts from filing/news
text without confusing per-share prices, exercise prices, fees, commissions,
or generic "up to $X" language with an issuance amount.

Key v10 rules
-------------
1. Only explicit aggregate/gross offering/proceeds/financing amounts are
   accepted as an issuance amount.
2. Generic "up to $X" is NOT enough by itself.
3. Per-share, exercise/strike price, warrant price, option price, fees and
   commissions are blocked.
4. If the amount cannot be verified, offering_amount_m is None and
   dilution_risk is "OKÄND".
5. Evidence is returned so downstream code can see the text that supported
   the amount.
6. Existing callers can use analyze_issuance(text), discover_issuance(text),
   or extract_offering_amount(text).
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Regex building blocks
# ---------------------------------------------------------------------------

_CURRENCY = r"(?:US\$|\$|USD)\s*"
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_AMOUNT = rf"{_CURRENCY}{_NUMBER}(?:\s*(?:million|mn|m|billion|bn|b|thousand|k))?"

# Explicit aggregate/proceeds language. The wording around the amount is
# intentionally restrictive: this is the main protection against taking
# "$0.08 per share" or "$0.08 exercise price" as a $0.08M issuance.
_AGGREGATE_PATTERNS = [
    re.compile(
        rf"(?P<context>\b(?:aggregate|gross|total)\s+"
        rf"(?:offering|purchase|financing|transaction|proceeds?|consideration)"
        rf"(?:\s+(?:amount|price|value))?\b"
        rf".{{0,90}}?(?P<amount>{_AMOUNT}))",
        re.I | re.S,
    ),
    re.compile(
        rf"(?P<context>\b(?:gross|aggregate|total)\s+proceeds?\b"
        rf".{{0,90}}?(?P<amount>{_AMOUNT}))",
        re.I | re.S,
    ),
    re.compile(
        rf"(?P<context>\b(?:raised|raising|funding|financing|funded)"
        rf"\b.{{0,90}}?(?P<amount>{_AMOUNT}))",
        re.I | re.S,
    ),
    re.compile(
        rf"(?P<context>\b(?:offering|private\s+placement|registered\s+direct|"
        rf"direct\s+offering|public\s+offering)\b.{{0,90}}?"
        rf"(?:for|of|in\s+the\s+amount\s+of)\s*(?P<amount>{_AMOUNT}))",
        re.I | re.S,
    ),
]

# These phrases invalidate an otherwise nearby amount. They cover the most
# common cases where a small number is a price rather than an issuance value.
_BLOCKED_CONTEXT = re.compile(
    r"""
    (?:per\s+share|
       per-share|
       per\s+unit|
       per-unit|
       exercise\s+price|
       strike\s+price|
       purchase\s+price\s+per|
       warrant\s+exercise|
       option\s+exercise|
       conversion\s+price|
       conversion\s+rate|
       subscription\s+price|
       offering\s+price\s+per|
       share\s+price|
       common\s+stock\s+at|
       commission|
       commissions|
       fee|
       fees|
       expense|
       expenses|
       legal\s+fees|
       placement\s+agent\s+fee|
       transaction\s+costs?)
    """,
    re.I | re.X,
)

# A generic "up to $X" statement is not sufficient to establish aggregate
# proceeds. It may describe a facility ceiling, purchase price, or maximum
# number of securities.
_UP_TO = re.compile(r"\bup\s+to\s+" + _AMOUNT, re.I)

# Explicit evidence that an "up to" amount is actually a financing facility
# or aggregate commitment. This is intentionally stricter than merely seeing
# "up to $X".
_UP_TO_VALID = re.compile(
    rf"\b(?:up\s+to)\s+(?P<amount>{_AMOUNT}).{{0,100}}?"
    rf"\b(?:aggregate|gross|total)\s+"
    rf"(?:principal|commitment|proceeds?|financing|facility|purchase)\b",
    re.I | re.S,
)

# Number/unit normalization.
_UNIT_MULTIPLIERS = {
    "k": 0.001,
    "thousand": 0.001,
    "m": 1.0,
    "mn": 1.0,
    "million": 1.0,
    "b": 1000.0,
    "bn": 1000.0,
    "billion": 1000.0,
}


def _normalize_text(text: Any) -> str:
    if text is None:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


def _parse_amount(raw: str) -> Optional[float]:
    """Return USD millions from a currency amount string."""
    if not raw:
        return None

    value_match = re.search(_NUMBER, raw.replace("$", ""))
    if not value_match:
        return None

    try:
        value = float(value_match.group(0).replace(",", ""))
    except ValueError:
        return None

    lower = raw.lower()
    multiplier = 0.001  # plain dollars -> millions

    for unit, factor in sorted(
        _UNIT_MULTIPLIERS.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if re.search(rf"\b{re.escape(unit)}\b", lower):
            multiplier = factor
            break

    return value * multiplier


def _evidence_window(text: str, start: int, end: int, radius: int = 150) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return text[left:right].strip()


def _is_blocked(text: str, start: int, end: int) -> Tuple[bool, Optional[str]]:
    window = text[max(0, start - 110): min(len(text), end + 110)]

    match = _BLOCKED_CONTEXT.search(window)
    if match:
        return True, match.group(0).strip()

    # Stronger guard for "X per share" appearing immediately after/before the
    # amount.
    local = text[max(0, start - 50): min(len(text), end + 50)]
    if re.search(r"\bper[- ](?:share|unit)\b", local, re.I):
        return True, "per share/unit"

    return False, None


def _valid_candidate(text: str, match: re.Match[str]) -> Optional[Dict[str, Any]]:
    amount_raw = match.group("amount")
    amount_m = _parse_amount(amount_raw)
    if amount_m is None:
        return None

    blocked, reason = _is_blocked(text, match.start("amount"), match.end("amount"))
    if blocked:
        return None

    evidence = _evidence_window(text, match.start(), match.end())
    return {
        "offering_amount_m": round(amount_m, 6),
        "currency": "USD",
        "evidence": evidence,
        "matched_amount": amount_raw,
        "evidence_type": "explicit_aggregate_or_gross",
    }


def extract_offering_amount(text: Any) -> Optional[Dict[str, Any]]:
    """
    Extract one verified aggregate/gross offering amount.

    Returns None when the text does not contain sufficient evidence.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return None

    candidates: List[Dict[str, Any]] = []

    for pattern in _AGGREGATE_PATTERNS:
        for match in pattern.finditer(normalized):
            candidate = _valid_candidate(normalized, match)
            if candidate:
                candidates.append(candidate)

    # "up to" is only accepted when the same sentence/nearby text explicitly
    # identifies it as aggregate/gross financing/commitment/proceeds.
    for match in _UP_TO_VALID.finditer(normalized):
        candidate = _valid_candidate(normalized, match)
        if candidate:
            candidate["evidence_type"] = "explicit_aggregate_up_to"
            candidates.append(candidate)

    if not candidates:
        return None

    # Prefer the strongest explicit aggregate evidence.
    rank = {
        "explicit_aggregate_or_gross": 2,
        "explicit_aggregate_up_to": 1,
    }
    candidates.sort(
        key=lambda x: (
            rank.get(x.get("evidence_type", ""), 0),
            x.get("offering_amount_m", 0),
        ),
        reverse=True,
    )
    return candidates[0]


def analyze_issuance(text: Any) -> Dict[str, Any]:
    """
    Analyze issuance evidence and return a stable result object.

    Important: an unverifiable amount is represented by None, never by 0.
    """
    normalized = _normalize_text(text)

    result: Dict[str, Any] = {
        "issuance_detected": False,
        "offering_amount_m": None,
        "currency": "USD",
        "dilution_risk": "OKÄND",
        "evidence": None,
        "evidence_type": None,
        "matched_amount": None,
        "reason": "Ingen verifierad aggregerad emissions-/finansieringssumma hittades.",
    }

    if not normalized:
        result["reason"] = "Tom text."
        return result

    candidate = extract_offering_amount(normalized)
    if candidate is None:
        if _UP_TO.search(normalized):
            result["reason"] = (
                'Texten innehåller "up to", men beloppet kan inte verifieras '
                "som en aggregerad/gross emissions- eller finansieringssumma."
            )
        return result

    result.update(
        {
            "issuance_detected": True,
            "offering_amount_m": candidate["offering_amount_m"],
            "currency": candidate["currency"],
            "evidence": candidate["evidence"],
            "evidence_type": candidate["evidence_type"],
            "matched_amount": candidate["matched_amount"],
            "dilution_risk": "OKÄND",
            "reason": "Verifierad explicit aggregerad/gross summa.",
        }
    )
    return result


def discover_issuance(
    text: Any = None,
    documents: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """
    Convenience wrapper for one text value or multiple documents.

    Each document may be a string or a dict containing a text-like field
    (text/body/content/summary/headline). Results include evidence.
    """
    chunks: List[str] = []

    if text is not None:
        chunks.append(_normalize_text(text))

    if documents is not None:
        for doc in documents:
            if isinstance(doc, dict):
                value = (
                    doc.get("text")
                    or doc.get("body")
                    or doc.get("content")
                    or doc.get("summary")
                    or doc.get("headline")
                    or ""
                )
                chunks.append(_normalize_text(value))
            else:
                chunks.append(_normalize_text(doc))

    combined = " ".join(x for x in chunks if x)

    result = analyze_issuance(combined)
    result["documents_checked"] = len(chunks)
    return result


def is_verified_issuance(text: Any) -> bool:
    """Small boolean helper for callers that only need a yes/no answer."""
    return bool(analyze_issuance(text).get("issuance_detected"))


# ---------------------------------------------------------------------------
# Regression examples for the exact failure mode this version addresses.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    examples = {
        # MUST NOT become $0.08M.
        "per_share": "The securities were sold at $0.08 per share.",
        "exercise": "The warrants have an exercise price of $0.08 per share.",
        "generic_up_to": "The company may issue up to $0.08 million of securities.",
        # MUST be accepted.
        "aggregate": "The aggregate gross proceeds of the offering were $12 million.",
        "gross": "Gross proceeds from the financing were approximately $25.5 million.",
        "raised": "The company raised $8 million in the financing.",
    }

    for name, sample in examples.items():
        print(name, "=>", analyze_issuance(sample))
