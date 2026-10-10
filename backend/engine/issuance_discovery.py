import os
import re
import html
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "TradePilotAI research contact@example.com")
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

OFFERING_FORMS = {
    "S-1", "S-1/A", "S-3", "S-3/A", "F-1", "F-1/A", "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424B8",
}
MAX_MARKET_CAP_M = float(os.getenv("TRADEPILOT_ISSUANCE_MAX_MARKET_CAP_M", "500"))
MIN_MARKET_CAP_M = float(os.getenv("TRADEPILOT_ISSUANCE_MIN_MARKET_CAP_M", "1"))
MAX_PROFILE_CHECKS = int(os.getenv("TRADEPILOT_ISSUANCE_PROFILE_CHECKS", "40"))
MAX_FILING_CHECKS = int(os.getenv("TRADEPILOT_ISSUANCE_FILING_CHECKS", "25"))
PROFILE_WORKERS = int(os.getenv("TRADEPILOT_ISSUANCE_PROFILE_WORKERS", "4"))

_ticker_map = None
_profile_cache = {}
_filing_cache = {}


def _headers():
    return {"User-Agent": SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}


def _get_ticker_map():
    global _ticker_map
    if _ticker_map is not None:
        return _ticker_map
    r = requests.get(TICKERS_URL, headers=_headers(), timeout=20)
    r.raise_for_status()
    mapping = {}
    for row in r.json().values():
        try:
            cik = str(row["cik_str"]).zfill(10)
            ticker = str(row["ticker"]).upper().strip()
            if ticker:
                mapping[cik] = {
                    "ticker": ticker,
                    "company_name": str(row.get("title") or "").strip(),
                }
        except Exception:
            continue
    _ticker_map = mapping
    return mapping


def _quarter(date_obj):
    return ((date_obj.month - 1) // 3) + 1


def _index_url(date_obj):
    return (
        f"https://www.sec.gov/Archives/edgar/daily-index/"
        f"{date_obj.year}/QTR{_quarter(date_obj)}/"
        f"master.{date_obj.strftime('%Y%m%d')}.idx"
    )


def _parse_master_index(text):
    rows, started = [], False
    for line in text.splitlines():
        if line.startswith("----"):
            started = True
            continue
        if not started or not line.strip():
            continue
        parts = line.split("|")
        if len(parts) != 5:
            continue
        cik, company, form, filing_date, filename = [p.strip() for p in parts]
        rows.append({
            "cik": cik.zfill(10),
            "company_name": company,
            "form": form.upper(),
            "filing_date": filing_date,
            "filename": filename,
        })
    return rows


def _score(form):
    score, reasons = 0, []
    if form.startswith(("S-1", "F-1")):
        score += 30
        reasons.append("nyregistrering")
    if form.startswith(("S-3", "F-3")):
        score += 20
        reasons.append("shelf/registrering")
    if form.startswith("424B"):
        score += 45
        reasons.append("prospekt/erbjudande")
    if form in {"424B4", "424B5"}:
        score += 10
        reasons.append("erbjudandeprospekt")
    return min(score, 100), reasons


def _looks_like_fund(company_name):
    name = company_name.upper()
    return any(x in name for x in (
        " ETF", " TRUST", " FUND", " FUNDS", " MUTUAL", " INCOME OPPORTUNITIES",
        " EXCHANGE TRADED"
    ))


def _looks_like_bank_or_financial_vehicle(company_name, industry=""):
    """Exclude obvious banks and passive financial vehicles from this small-cap scan.

    Keep this conservative: generic words such as 'financial' alone are not enough
    to exclude a company, because small fintech and operating companies can use them.
    """
    name = re.sub(r"[^A-Z0-9]+", " ", str(company_name or "").upper()).strip()
    industry_text = str(industry or "").strip().lower()
    bank_name_patterns = (
        r"\bBANK OF ", r"\bBANKING CORP", r"\bBANCORP\b",
        r"\bCOMMERCIAL BANK\b", r"\bSAVINGS BANK\b",
        r"\bCREDIT UNION\b", r"\bIMPERIAL BANK\b",
    )
    if any(re.search(pattern, name) for pattern in bank_name_patterns):
        return True
    excluded_industries = (
        "banks", "regional banks", "diversified banks", "investment banking",
        "asset management", "insurance", "investment trusts",
    )
    return any(term in industry_text for term in excluded_industries)


def _profile(symbol):
    if symbol in _profile_cache:
        return _profile_cache[symbol]
    if not FINNHUB_API_KEY:
        _profile_cache[symbol] = None
        return None
    try:
        r = requests.get(
            f"{FINNHUB_BASE_URL}/stock/profile2",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json()
        _profile_cache[symbol] = data if isinstance(data, dict) else None
    except Exception:
        _profile_cache[symbol] = None
    return _profile_cache[symbol]


def _market_cap_m(profile):
    try:
        return float(profile.get("marketCapitalization")) if profile else None
    except (TypeError, ValueError):
        return None


def _filing_url(filing_path):
    return f"https://www.sec.gov/Archives/{filing_path}"


def _clean_filing_text(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text))


# ---------------------------------------------------------------------------
# V10 issuance amount protection
# ---------------------------------------------------------------------------

_CURRENCY = r"(?:US\$|\$|USD)\s*"
_NUMBER = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
_AMOUNT = rf"{_CURRENCY}{_NUMBER}(?:\s*(?:million|mn|m|billion|bn|b|thousand|k))?"

_AGGREGATE_PATTERNS = [
    re.compile(
        rf"\b(?:aggregate|gross|total)\s+"
        rf"(?:offering|purchase|financing|transaction|proceeds?|consideration)"
        rf"(?:\s+(?:amount|price|value))?[^.!?;]{{0,90}}?(?P<amount>{_AMOUNT})",
        re.I | re.S,
    ),
    re.compile(
        rf"\b(?:gross|aggregate|total)\s+proceeds?\b"
        rf"[^.!?;]{{0,90}}?(?P<amount>{_AMOUNT})",
        re.I | re.S,
    ),
    re.compile(
        rf"\b(?:raised|raising|funding|financing|funded)\b"
        rf"[^.!?;]{{0,90}}?(?P<amount>{_AMOUNT})",
        re.I | re.S,
    ),
    re.compile(
        rf"\b(?:offering|private\s+placement|registered\s+direct|"
        rf"direct\s+offering|public\s+offering)\b[^.!?;]{{0,90}}?"
        rf"(?:for|of|in\s+the\s+amount\s+of)\s*(?P<amount>{_AMOUNT})",
        re.I | re.S,
    ),
]

_BLOCKED_CONTEXT = re.compile(
    r"(?:per\s+share|per-share|per\s+unit|per-unit|exercise\s+price|"
    r"strike\s+price|purchase\s+price\s+per|warrant\s+exercise|"
    r"option\s+exercise|conversion\s+price|conversion\s+rate|"
    r"subscription\s+price|offering\s+price\s+per|share\s+price|"
    r"commission|commissions|fee|fees|expense|expenses|legal\s+fees|"
    r"placement\s+agent\s+fee|transaction\s+costs?)",
    re.I,
)

_UP_TO = re.compile(r"\bup\s+to\s+" + _AMOUNT, re.I)
_UP_TO_VALID = re.compile(
    rf"\bup\s+to\s+(?P<amount>{_AMOUNT}).{{0,100}}?"
    rf"\b(?:aggregate|gross|total)\s+"
    rf"(?:principal|commitment|proceeds?|financing|facility|purchase)\b",
    re.I | re.S,
)

_UNIT_MULTIPLIERS = {
    "k": 0.001, "thousand": 0.001,
    "m": 1.0, "mn": 1.0, "million": 1.0,
    "b": 1000.0, "bn": 1000.0, "billion": 1000.0,
}


def _parse_amount(raw):
    """Convert a USD amount to USD millions.

    Explicit k/thousand, m/mn/million and b/bn/billion suffixes are honored.
    A currency amount with no suffix is interpreted as dollars and divided by
    one million. Suffix matching supports both "$12m" and "$12 m".
    """
    cleaned = str(raw or "").replace(",", "").strip()
    match = re.search(r"\d+(?:\.\d+)?", cleaned)
    if not match:
        return None
    try:
        value = float(match.group(0))
    except ValueError:
        return None

    suffix = cleaned[match.end():].strip().lower()
    suffix = re.sub(r"^[\s\-]+", "", suffix)
    if suffix.startswith(("billion", "bn", "b")):
        multiplier = 1000.0
    elif suffix.startswith(("million", "mn", "m")):
        multiplier = 1.0
    elif suffix.startswith(("thousand", "k")):
        multiplier = 0.001
    else:
        # No scale suffix: the value is in dollars, not millions.
        multiplier = 0.000001
    return value * multiplier


def _candidate(text, match):
    raw = match.group("amount")
    amount_m = _parse_amount(raw)
    if amount_m is None or amount_m <= 0:
        return None
    window = text[max(0, match.start("amount") - 120):min(len(text), match.end("amount") + 120)]
    if _BLOCKED_CONTEXT.search(window):
        return None
    # Do not mistake public-sector appropriations or unrelated legislation for
    # company financing. Keep this sentence-local so nearby filing language
    # cannot lend false context to an unrelated amount.
    left = max(text.rfind(mark, 0, match.start("amount")) for mark in ".!?;\n")
    right_candidates = [text.find(mark, match.end("amount")) for mark in ".!?;\n"]
    right_candidates = [pos for pos in right_candidates if pos >= 0]
    sentence = text[left + 1:min(right_candidates) if right_candidates else len(text)].lower()
    # Reject amounts that belong to government appropriations, financial
    # statement summaries, or clearly historical transactions rather than the
    # current offering described by the filing. These phrases frequently occur
    # in prospectus supplements but are not evidence of new proceeds.
    if re.search(
        r"\b(?:appropriation(?:s)?|national defense authorization act|"
        r"department of defense|defense department|federal budget|"
        r"government funding|drone systems|military procurement)\b",
        sentence,
    ):
        return None
    # Acquisition consideration is not issuance proceeds, even when the filing
    # contains words such as aggregate consideration or a securities purchase
    # agreement elsewhere. Do not let it become the displayed offering amount.
    if re.search(
        r"\b(?:aggregate consideration|purchase consideration|consideration for the acquisition|"
        r"consideration payable|purchase price for|acquisition price|acquire(?:d)? the shares|"
        r"sale and purchase agreement|business combination consideration)\b",
        sentence,
    ):
        return None
    historical_or_financial_summary = re.search(
        r"\b(?:net cash generated from financing activities|cash flows? from financing|"
        r"during the (?:year|quarter|period) ended|for the fiscal year|"
        r"previously raised|previous offering|prior offering|historical proceeds|"
        r"in prior periods|in the prior year|year-over-year)\b",
        sentence,
    )
    explicit_current_offering = re.search(
        r"\b(?:this offering|the offering|under the (?:terms of the )?sales agreement|"
        r"gross proceeds of the offering|aggregate offering price|"
        r"proceeds from this offering)\b",
        sentence,
    )
    if historical_or_financial_summary and not explicit_current_offering:
        return None
    evidence = text[max(0, match.start() - 220):min(len(text), match.end() + 220)].strip()
    evidence_lower = evidence.lower()
    sentence_lower = sentence.lower()
    is_capacity = bool(re.search(
        r"\bup to\b|\bfrom time to time\b|\bmay offer\b|\bmay sell\b|"
        r"\bwill offer and sell\b|\bat[- ]the[- ]market\b|\batm sales agreement\b|"
        r"\bmaximum\b|\bavailable for future sales\b",
        evidence_lower,
    ))
    is_reported_proceeds = bool(re.search(
        r"\b(?:gross|net|aggregate) proceeds\b.{0,100}\b(?:were|was|totaled|totalled|amounted to)\b|"
        r"\b(?:has|have) raised\b|\braised\b.{0,80}\b(?:in|through|from) (?:the|this) financing\b|"
        r"\bproceeds received\b|\bcompany received\b.{0,80}\bproceeds\b",
        sentence_lower,
    ))
    amount_kind = "capacity" if is_capacity else "reported_proceeds" if is_reported_proceeds else "transaction_amount"
    return {
        "offering_amount_m": round(amount_m, 6),
        "currency": "USD",
        "evidence": evidence,
        "matched_amount": raw,
        "evidence_type": "explicit_aggregate_or_gross",
        "amount_kind": amount_kind,
    }


def extract_offering_amount(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return None
    candidates = []
    for pattern in _AGGREGATE_PATTERNS:
        for match in pattern.finditer(text):
            item = _candidate(text, match)
            if item:
                candidates.append(item)
    for match in _UP_TO_VALID.finditer(text):
        item = _candidate(text, match)
        if item:
            item["evidence_type"] = "explicit_aggregate_up_to"
            candidates.append(item)
    if not candidates:
        return None
    # Prefer explicit reported-proceeds language over a large shelf/ATM ceiling.
    # A capacity amount must never win merely because its number is larger.
    kind_rank = {"reported_proceeds": 3, "transaction_amount": 2, "capacity": 1}
    evidence_rank = {"explicit_aggregate_or_gross": 2, "explicit_aggregate_up_to": 1}
    return sorted(
        candidates,
        key=lambda x: (
            kind_rank.get(x.get("amount_kind"), 0),
            evidence_rank.get(x["evidence_type"], 0),
            x["offering_amount_m"],
        ),
        reverse=True,
    )[0]


def analyze_issuance(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    result = {
        "issuance_detected": False,
        "offering_amount_m": None,
        "currency": "USD",
        "dilution_risk": "OKÄND",
        "evidence": None,
        "evidence_type": None,
        "matched_amount": None,
        "reason": "Ingen verifierad aggregerad emissions-/finansieringssumma hittades.",
    }
    if not text:
        result["reason"] = "Tom text."
        return result
    item = extract_offering_amount(text)
    if not item:
        if _UP_TO.search(text):
            result["reason"] = 'Texten innehåller "up to", men beloppet kan inte verifieras som en aggregerad/gross summa.'
        return result
    result.update({
        "issuance_detected": True,
        "offering_amount_m": item["offering_amount_m"],
        "currency": item["currency"],
        "evidence": item["evidence"],
        "evidence_type": item["evidence_type"],
        "matched_amount": item["matched_amount"],
        "reason": "Verifierad explicit aggregerad/gross summa.",
    })
    return result


def discover_issuance(text=None, documents=None):
    chunks = []
    if text is not None:
        chunks.append(str(text))
    for doc in documents or []:
        if isinstance(doc, dict):
            chunks.append(str(
                doc.get("text") or doc.get("body") or doc.get("content") or
                doc.get("summary") or doc.get("headline") or ""
            ))
        else:
            chunks.append(str(doc))
    result = analyze_issuance(" ".join(chunks))
    result["documents_checked"] = len(chunks)
    return result


def is_verified_issuance(text):
    return bool(analyze_issuance(text).get("issuance_detected"))


def _extract_shares_offered(text):
    patterns = [
        r"(?:we are|we're)\s+offering\s+([\d,]+)\s+(?:shares|ordinary shares)",
        r"offering\s+(?:of|up to)\s+([\d,]+)\s+(?:shares|ordinary shares)",
        r"up to\s+([\d,]+)\s+(?:shares|ordinary shares)",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, flags=re.I)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except ValueError:
                pass
    return None


def _classify_offering_status(text, form, amount):
    """Conservatively classify the filing; a prospectus or historic proceeds is not proof of a completed sale."""
    lower = re.sub(r"\s+", " ", str(text or "")).lower()
    potential = bool(re.search(
        r"\bat[- ]the[- ]market\b|\batm sales agreement\b|"
        r"\bfrom time to time\b|\bmay offer\b|\bmay sell\b|"
        r"\bup to an aggregate\b|\bsubject to market conditions\b|"
        r"\bwill offer and sell\b|\bavailable for future sales\b|"
        r"\bproceeds will depend on\b|\bdepending on the number of shares\b",
        lower,
    ))
    # Only explicit completion language counts as confirmed. Generic references to
    # aggregate proceeds can describe an earlier transaction elsewhere in the filing.
    completed = bool(re.search(
        r"\b(?:has|have) completed (?:the|its|this) (?:public |registered direct |private placement )?offering\b|"
        r"\b(?:closed|completed) (?:the|its|this) (?:public |registered direct |private placement )?offering\b|"
        r"\bthe offering (?:was|has been) completed\b|"
        r"\bthe company (?:has )?(?:received|raised) (?:net |gross )?proceeds from (?:the|this) offering\b|"
        r"\b(?:net|gross) proceeds from (?:the|this) offering (?:were|was|totaled|totalled)\b",
        lower,
    ))
    # Future-program language takes precedence: an ATM or shelf can coexist with
    # historical financing references in the same prospectus.
    if potential:
        return "potential", "Möjligt eller framtida erbjudande; belopp kan vara ett tak"
    if completed:
        return "confirmed", "Dokumentet innehåller uttrycklig text om genomförd emission/erhållna intäkter"
    if form.startswith(("S-", "F-", "424B")) or amount:
        return "registered", "Registrerat/dokumenterat erbjudande; genomförande ej bekräftat"
    return "registered", "Inlämning identifierad; genomförande ej bekräftat"


def _signal_tier(item):
    """Human-readable triage tier; not a buy/sell recommendation."""
    analysis = item.get("filing_analysis") or {}
    status = analysis.get("event_status", "unknown")
    amount_status = analysis.get("offering_amount_status", "not_found")
    score = item.get("event_priority_score", 0)
    if status == "confirmed" and amount_status == "reported_proceeds" and score >= 45:
        return "high_relevance", "Explicit completed-event wording and reported proceeds; verify filing details"
    if status == "potential":
        return "watch", "Possible future/program offering; do not treat maximum capacity as completed financing"
    return "low_relevance", "Registration or disclosure without clear evidence of completed financing"


def _analyze_filing(item):
    key = item["filing_path"]
    if key in _filing_cache:
        return _filing_cache[key]
    try:
        r = requests.get(_filing_url(key), headers=_headers(), timeout=12)
        r.raise_for_status()
        text = _clean_filing_text(r.text)
    except Exception:
        _filing_cache[key] = None
        return None

    lower = text.lower()
    atm = bool(re.search(r"at[- ]the[- ]market|atm sales agreement", lower))
    pre_funded = "pre-funded warrant" in lower or "prefunded warrant" in lower
    warrants = bool(re.search(r"\bwarrants?\b", lower))
    purchase_agreement = "securities purchase agreement" in lower
    registered_direct = "registered direct offering" in lower
    public_offering = "public offering" in lower
    rights_offering = "rights offering" in lower
    amount = extract_offering_amount(text)
    event_status, event_status_reason = _classify_offering_status(text, item.get("form", ""), amount)
    amount_evidence = amount["evidence"] if amount else None
    amount_is_ceiling = bool(amount and amount.get("amount_kind") == "capacity")
    analysis = {
        "verified": True,
        "event_status": event_status,
        "event_status_reason": event_status_reason,
        "offering_amount_status": (
            "maximum_or_program_capacity" if amount_is_ceiling
            else "reported_proceeds" if event_status == "confirmed" and amount and amount.get("amount_kind") == "reported_proceeds"
            else "disclosed_amount_not_confirmed" if amount else "not_found"
        ),
        "amount_kind": amount.get("amount_kind") if amount else None,
        "offering_type": [],
        "offering_amount_m": amount["offering_amount_m"] if amount else None,
        "offering_evidence": amount["evidence"] if amount else None,
        "shares_offered": _extract_shares_offered(text),
        "pre_funded_warrants": pre_funded,
        "warrants": warrants,
        "atm": atm,
        "registered_direct": registered_direct,
        "public_offering": public_offering,
        "rights_offering": rights_offering,
        "purchase_agreement": purchase_agreement,
        "dilution_language": bool(re.search(r"\bdilution\b|diluted", lower)),
    }
    if registered_direct: analysis["offering_type"].append("registered_direct")
    if public_offering: analysis["offering_type"].append("public_offering")
    if atm: analysis["offering_type"].append("atm")
    if rights_offering: analysis["offering_type"].append("rights_offering")
    if purchase_agreement: analysis["offering_type"].append("purchase_agreement")
    _filing_cache[key] = analysis
    return analysis


def _issuance_quality(filing, analysis):
    if not analysis:
        return 0, ["filing ej verifierad"], "OKÄND"
    market_cap_m = filing.get("market_cap_m")
    amount_m = analysis.get("offering_amount_m")
    amount_is_realized = (
        analysis.get("event_status") == "confirmed"
        and analysis.get("offering_amount_status") == "reported_proceeds"
    )
    ratio = amount_m / market_cap_m if amount_is_realized and market_cap_m and amount_m is not None else None
    score, reasons = 0, []
    if analysis.get("event_status") == "confirmed" and (
        analysis.get("registered_direct") or analysis.get("purchase_agreement") or analysis.get("rights_offering")
    ):
        score += 25
        reasons.append("bekräftad kapitalanskaffning")
    elif analysis.get("registered_direct") or analysis.get("purchase_agreement") or analysis.get("rights_offering"):
        score += 8
        reasons.append("finansieringsvillkor identifierade; genomförande ej bekräftat")
    if analysis.get("atm"):
        score += 5
        reasons.append("ATM")
    if analysis.get("pre_funded_warrants"):
        score -= 10
        reasons.append("pre-funded warrants")
    if analysis.get("warrants"):
        score -= 5
        reasons.append("warrants")
    if ratio is not None:
        if ratio >= 1.0:
            score -= 20
            reasons.append("emission stor jämfört med market cap")
        elif ratio >= 0.5:
            score -= 12
            reasons.append("hög potentiell utspädning")
        elif ratio >= 0.2:
            score -= 6
            reasons.append("måttlig potentiell utspädning")
    dilution = "OKÄND" if ratio is None else ("HÖG" if ratio >= 0.5 else "MEDEL" if ratio >= 0.2 else "LÅG")
    return score, reasons, dilution



def _event_priority(item):
    """Rank actionable, recent financing events above speculative program capacity.

    This is a screening priority, not a prediction of share-price performance.
    """
    analysis = item.get("filing_analysis") or {}
    status = analysis.get("event_status", "unknown")
    amount_status = analysis.get("offering_amount_status", "not_found")
    score = 0
    reasons = []

    status_points = {"confirmed": 35, "potential": 18, "registered": 8, "unknown": 0}
    score += status_points.get(status, 0)
    if status == "confirmed":
        reasons.append("textually confirmed financing event")
    elif status == "potential":
        reasons.append("potential/future financing; not confirmed as completed")
    elif status == "registered":
        reasons.append("registration filing only; sale not confirmed")

    if amount_status == "reported_proceeds":
        score += 20
        reasons.append("reported proceeds stated")
    elif amount_status == "maximum_or_program_capacity":
        score -= 12
        reasons.append("maximum/program amount discounted")
    elif amount_status == "disclosed_amount_not_confirmed":
        score += 3
        reasons.append("disclosed amount not confirmed as raised")

    # A filing with explicit transaction terms is more useful than a generic shelf.
    if analysis.get("registered_direct") or analysis.get("purchase_agreement") or analysis.get("rights_offering"):
        score += 8
        reasons.append("specific financing terms detected")
    if analysis.get("atm"):
        score -= 8
        reasons.append("ATM capacity may be sold over time")

    cap = item.get("market_cap_m")
    amount = analysis.get("offering_amount_m")
    amount_is_realized = (
        status == "confirmed" and amount_status == "reported_proceeds"
    )
    if isinstance(cap, (int, float)) and cap > 0:
        if cap <= 100:
            score += 8
            reasons.append("micro-cap focus")
        elif cap <= 500:
            score += 4
            reasons.append("small-cap focus")
        if amount_is_realized and isinstance(amount, (int, float)) and amount > 0:
            ratio = amount / cap
            # Very large ratios are important risk flags, not automatically better opportunities.
            if ratio >= 1:
                score -= 12
                reasons.append("very large stated amount relative to market cap; verify terms")
            elif ratio >= 0.5:
                score -= 6
                reasons.append("large stated amount relative to market cap")

    try:
        filing_date = str(item.get("filing_date", "")).strip()
        filed = None
        for date_format in ("%Y%m%d", "%Y-%m-%d"):
            try:
                filed = datetime.strptime(filing_date, date_format).date()
                break
            except ValueError:
                continue
        if filed is None:
            raise ValueError("Unsupported filing date format")

        age = max(0, (datetime.now(timezone.utc).date() - filed).days)
        recency_points = max(0, 10 - min(age, 10))
        score += recency_points
        if recency_points:
            reasons.append("recent SEC filing")
    except (TypeError, ValueError):
        pass

    return max(0, min(100, score)), reasons

def discover_issuance_candidates(days=7, limit=25):
    """Main API used by backend.main. Conservatively ranks realized proceeds above program ceilings."""
    days = max(1, min(int(days), 14))
    limit = max(1, min(int(limit), 50))
    ticker_map = _get_ticker_map()
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)
    by_ticker, errors, days_checked = {}, [], 0

    for offset in range(days + 1):
        day = start + timedelta(days=offset)
        if day >= today or day.weekday() >= 5:
            continue
        try:
            r = requests.get(_index_url(day), headers=_headers(), timeout=12)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            rows = _parse_master_index(r.text)
            days_checked += 1
        except Exception as exc:
            errors.append(f"{day.isoformat()}: {exc}")
            continue

        for row in rows:
            if row["form"] not in OFFERING_FORMS:
                continue
            identity = ticker_map.get(row["cik"])
            if not identity or not identity["ticker"] or len(identity["ticker"]) > 8:
                continue
            if _looks_like_fund(identity["company_name"]):
                continue
            score, reasons = _score(row["form"])
            item = {
                "symbol": identity["ticker"],
                "company_name": identity["company_name"],
                "cik": row["cik"],
                "form": row["form"],
                "filing_date": row["filing_date"],
                "filing_path": row["filename"],
                "issuance_score": score,
                "issuance_reasons": reasons,
                "source": "SEC EDGAR daily index",
            }
            old = by_ticker.get(item["symbol"])
            if old is None or (item["issuance_score"], item["filing_date"]) > (old["issuance_score"], old["filing_date"]):
                by_ticker[item["symbol"]] = item

    sec_candidates = sorted(
        by_ticker.values(),
        key=lambda x: (x["issuance_score"], x["filing_date"] or ""),
        reverse=True,
    )
    profile_candidates = sec_candidates[:MAX_PROFILE_CHECKS]
    market_caps = {}

    if FINNHUB_API_KEY:
        with ThreadPoolExecutor(max_workers=max(1, min(PROFILE_WORKERS, len(profile_candidates)))) as pool:
            futures = {pool.submit(_market_cap_m, _profile(x["symbol"])): x["symbol"] for x in profile_candidates}
            for f in as_completed(futures):
                try:
                    market_caps[futures[f]] = f.result()
                except Exception:
                    pass

    candidates = []
    excluded_by_filter = {"market_cap_missing": 0, "market_cap_out_of_range": 0, "fund_or_bank": 0}
    for item in profile_candidates:
        profile = _profile(item["symbol"]) if FINNHUB_API_KEY else None
        cap = market_caps.get(item["symbol"])
        if cap is None:
            excluded_by_filter["market_cap_missing"] += 1
            continue
        if cap < MIN_MARKET_CAP_M or cap > MAX_MARKET_CAP_M:
            excluded_by_filter["market_cap_out_of_range"] += 1
            continue
        industry = (profile or {}).get("finnhubIndustry", "")
        if _looks_like_fund(item["company_name"]) or _looks_like_bank_or_financial_vehicle(item["company_name"], industry):
            excluded_by_filter["fund_or_bank"] += 1
            continue
        item["market_cap_m"] = round(cap, 2)
        item["company_industry"] = industry or None
        candidates.append(item)

    filing_candidates = candidates[:MAX_FILING_CHECKS]
    analyses = {}
    if filing_candidates:
        with ThreadPoolExecutor(max_workers=max(1, min(PROFILE_WORKERS, len(filing_candidates)))) as pool:
            futures = {pool.submit(_analyze_filing, x): x["symbol"] for x in filing_candidates}
            for f in as_completed(futures):
                try:
                    analyses[futures[f]] = f.result()
                except Exception:
                    pass

    results = []
    for item in candidates:
        analysis = analyses.get(item["symbol"])
        quality, reasons, dilution = _issuance_quality(item, analysis)
        item["filing_analysis"] = analysis or {"verified": False, "event_status": "unknown"}
        item["issuance_quality_score"] = max(0, min(100, 50 + quality))
        item["dilution_risk"] = dilution
        amount_m = (analysis or {}).get("offering_amount_m")
        cap = item["market_cap_m"]
        analysis_status = (analysis or {}).get("event_status")
        amount_status = (analysis or {}).get("offering_amount_status")
        amount_is_realized = analysis_status == "confirmed" and amount_status == "reported_proceeds"
        ratio_pct = (amount_m / cap * 100.0) if amount_is_realized and amount_m is not None and cap > 0 else None
        item["offering_to_market_cap_pct"] = round(ratio_pct, 2) if ratio_pct is not None else None
        item["dilution_estimate_note"] = (
            "Jämförelse mellan rapporterade intäkter och börsvärde; inte en faktisk utspädningsprognos"
            if ratio_pct is not None else "Inte beräknad: beloppet är inte bekräftade erhållna emissionsintäkter"
        )
        item["issuance_reasons"].extend(reasons)
        if cap <= 100:
            item["issuance_score"] = min(100, item["issuance_score"] + 15)
            item["issuance_reasons"].append("microcap")
        elif cap <= 500:
            item["issuance_score"] = min(100, item["issuance_score"] + 10)
            item["issuance_reasons"].append("smallcap")
        priority_score, priority_reasons = _event_priority(item)
        item["event_priority_score"] = priority_score
        item["event_priority_reasons"] = priority_reasons
        signal_tier, signal_tier_reason = _signal_tier(item)
        item["signal_tier"] = signal_tier
        item["signal_tier_reason"] = signal_tier_reason
        results.append(item)

    # Rank by event quality first, then recency. Raw issuance score remains visible
    # but does not override a weak/uncertain event classification.
    tier_rank = {"high_relevance": 3, "watch": 2, "low_relevance": 1}
    results.sort(key=lambda x: (
        tier_rank.get(x.get("signal_tier", "low_relevance"), 0),
        x.get("event_priority_score", 0),
        x["filing_date"] or "",
        x["issuance_score"],
        -x["market_cap_m"],
    ), reverse=True)
    return {
        "ok": True,
        "source": "SEC EDGAR daily index + Finnhub company profile",
        "selection": "recent offering filings; realized proceeds preferred over program ceilings; filtered for market cap",
        "days": days,
        "days_checked": days_checked,
        "today_index_skipped": True,
        "min_market_cap_m": MIN_MARKET_CAP_M,
        "max_market_cap_m": MAX_MARKET_CAP_M,
        "excluded_by_filter": excluded_by_filter,
        "focus": "small-cap/micro-cap operating companies; obvious banks and funds excluded",
        "unique_sec_candidates": len(by_ticker),
        "profile_checks": len(profile_candidates),
        "filing_checks": len(filing_candidates),
        "filings_verified": sum(1 for x in analyses.values() if x),
        "count": len(results[:limit]),
        "results": results[:limit],
        "errors": errors,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    assert _looks_like_bank_or_financial_vehicle("Canadian Imperial Bank of Commerce")
    assert _looks_like_bank_or_financial_vehicle("Example Corp", "Regional Banks")
    assert not _looks_like_bank_or_financial_vehicle("Example Financial Technologies Inc.", "Software")
    assert _looks_like_fund("Example ETF Trust")
    tests = [
        "The securities were sold at $0.08 per share.",
        "The warrants have an exercise price of $0.08 per share.",
        "The company may issue up to $0.08 million of securities.",
        "The aggregate gross proceeds of the offering were $12 million.",
        "Gross proceeds from the financing were approximately $25.5 million.",
        "The company raised $8 million in the financing.",
        "Net cash generated from financing activities of $16,498,110 was mainly due to proceeds of share issuance.",
        "The National Defense Authorization Act provides up to $33 billion for drone systems.",
        "Under this prospectus supplement, we may offer and sell securities up to an aggregate offering price of $200,000,000.",
    ]
    outputs = [analyze_issuance(sample) for sample in tests]
    assert outputs[0]["issuance_detected"] is False  # per-share amount
    assert outputs[1]["issuance_detected"] is False  # exercise price
    assert outputs[2]["issuance_detected"] is False  # unqualified up-to amount
    assert outputs[3]["offering_amount_m"] == 12.0
    assert outputs[4]["offering_amount_m"] == 25.5
    assert outputs[5]["offering_amount_m"] == 8.0
    assert outputs[6]["issuance_detected"] is False  # financial statement summary
    assert outputs[7]["issuance_detected"] is False  # unrelated government appropriation
    assert outputs[8]["offering_amount_m"] == 200.0  # explicit aggregate program capacity
    print("issuance_discovery self-tests passed")
