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
MAX_MARKET_CAP_M = float(os.getenv("TRADEPILOT_ISSUANCE_MAX_MARKET_CAP_M", "2000"))
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
        " ETF", " TRUST", " FUND", " FUNDS", " MUTUAL", " INCOME OPPORTUNITIES"
    ))


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
        rf"(?:\s+(?:amount|price|value))?.{{0,90}}?(?P<amount>{_AMOUNT})",
        re.I | re.S,
    ),
    re.compile(
        rf"\b(?:gross|aggregate|total)\s+proceeds?\b"
        rf".{{0,90}}?(?P<amount>{_AMOUNT})",
        re.I | re.S,
    ),
    re.compile(
        rf"\b(?:raised|raising|funding|financing|funded)\b"
        rf".{{0,90}}?(?P<amount>{_AMOUNT})",
        re.I | re.S,
    ),
    re.compile(
        rf"\b(?:offering|private\s+placement|registered\s+direct|"
        rf"direct\s+offering|public\s+offering)\b.{{0,90}}?"
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
    match = re.search(_NUMBER, raw.replace("$", ""))
    if not match:
        return None
    try:
        value = float(match.group(0).replace(",", ""))
    except ValueError:
        return None
    lower = raw.lower()
    multiplier = 0.001
    for unit, factor in sorted(_UNIT_MULTIPLIERS.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf"\b{re.escape(unit)}\b", lower):
            multiplier = factor
            break
    return value * multiplier


def _candidate(text, match):
    raw = match.group("amount")
    amount_m = _parse_amount(raw)
    if amount_m is None or amount_m <= 0:
        return None
    window = text[max(0, match.start("amount") - 120):min(len(text), match.end("amount") + 120)]
    if _BLOCKED_CONTEXT.search(window):
        return None
    return {
        "offering_amount_m": round(amount_m, 6),
        "currency": "USD",
        "evidence": text[max(0, match.start() - 150):min(len(text), match.end() + 150)].strip(),
        "matched_amount": raw,
        "evidence_type": "explicit_aggregate_or_gross",
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
    rank = {"explicit_aggregate_or_gross": 2, "explicit_aggregate_up_to": 1}
    return sorted(
        candidates,
        key=lambda x: (rank.get(x["evidence_type"], 0), x["offering_amount_m"]),
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
    analysis = {
        "verified": True,
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
    ratio = amount_m / market_cap_m if market_cap_m and amount_m is not None else None
    score, reasons = 0, []
    if analysis.get("registered_direct") or analysis.get("purchase_agreement") or analysis.get("rights_offering"):
        score += 25
        reasons.append("verifierad kapitalanskaffning")
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


def discover_issuance_candidates(days=7, limit=25):
    """Main API used by backend.main. Keeps V9 discovery while using V10 amount validation."""
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
    for item in profile_candidates:
        cap = market_caps.get(item["symbol"])
        if cap is None or cap > MAX_MARKET_CAP_M:
            continue
        item["market_cap_m"] = round(cap, 2)
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
        item["filing_analysis"] = analysis or {"verified": False}
        item["issuance_quality_score"] = max(0, min(100, 50 + quality))
        item["dilution_risk"] = dilution
        item["issuance_reasons"].extend(reasons)
        cap = item["market_cap_m"]
        if cap <= 100:
            item["issuance_score"] = min(100, item["issuance_score"] + 15)
            item["issuance_reasons"].append("microcap")
        elif cap <= 500:
            item["issuance_score"] = min(100, item["issuance_score"] + 10)
            item["issuance_reasons"].append("smallcap")
        results.append(item)

    results.sort(key=lambda x: (x["issuance_score"], x["filing_date"] or "", -x["market_cap_m"]), reverse=True)
    return {
        "ok": True,
        "source": "SEC EDGAR daily index + Finnhub company profile",
        "selection": "recent offering filings, deduplicated and filtered for market cap",
        "days": days,
        "days_checked": days_checked,
        "today_index_skipped": True,
        "max_market_cap_m": MAX_MARKET_CAP_M,
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
    tests = [
        "The securities were sold at $0.08 per share.",
        "The warrants have an exercise price of $0.08 per share.",
        "The company may issue up to $0.08 million of securities.",
        "The aggregate gross proceeds of the offering were $12 million.",
        "Gross proceeds from the financing were approximately $25.5 million.",
        "The company raised $8 million in the financing.",
    ]
    for sample in tests:
        print(analyze_issuance(sample))
