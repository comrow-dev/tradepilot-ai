import os
import re
import html
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "TradePilotAI research contact@example.com",
)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")

OFFERING_FORMS = {
    "S-1", "S-1/A",
    "S-3", "S-3/A",
    "F-1", "F-1/A",
    "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4",
    "424B5", "424B7", "424B8",
}

MAX_MARKET_CAP_M = float(
    os.getenv("TRADEPILOT_ISSUANCE_MAX_MARKET_CAP_M", "2000")
)

# Keep this bounded so Render does not make one Finnhub request per SEC filing.
MAX_PROFILE_CHECKS = int(
    os.getenv("TRADEPILOT_ISSUANCE_PROFILE_CHECKS", "40")
)
MAX_FILING_CHECKS = int(
    os.getenv("TRADEPILOT_ISSUANCE_FILING_CHECKS", "25")
)
PROFILE_WORKERS = int(
    os.getenv("TRADEPILOT_ISSUANCE_PROFILE_WORKERS", "4")
)

_ticker_map = None
_profile_cache = {}
_filing_cache = {}


def _headers():
    return {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }


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
            name = str(row.get("title") or "").strip()

            if ticker:
                mapping[cik] = {
                    "ticker": ticker,
                    "company_name": name,
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
    rows = []
    started = False

    for line in text.splitlines():
        if line.startswith("----"):
            started = True
            continue

        if not started or not line.strip():
            continue

        parts = line.split("|")
        if len(parts) != 5:
            continue

        cik, company, form, filing_date, filename = [
            p.strip() for p in parts
        ]

        rows.append({
            "cik": cik.zfill(10),
            "company_name": company,
            "form": form.upper(),
            "filing_date": filing_date,
            "filename": filename,
        })

    return rows


def _score(form):
    score = 0
    reasons = []

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

    blocked = (
        " ETF",
        " TRUST",
        " FUND",
        " FUNDS",
        " MUTUAL",
        " INCOME OPPORTUNITIES",
    )

    return any(token in name for token in blocked)


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
    if not profile:
        return None

    try:
        return float(profile.get("marketCapitalization"))
    except (TypeError, ValueError):
        return None


def _check_profile(item):
    profile = _profile(item["symbol"])
    market_cap_m = _market_cap_m(profile)

    return item["symbol"], market_cap_m


def _filing_url(filing_path):
    return f"https://www.sec.gov/Archives/{filing_path}"


def _clean_filing_text(text):
    text = re.sub(r"<script.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def _money_to_m(value, unit=""):
    try:
        amount = float(value.replace(",", ""))
    except (TypeError, ValueError):
        return None

    unit = (unit or "").lower()
    if unit.startswith("b"):
        amount *= 1000.0
    elif unit.startswith("k") or unit.startswith("th"):
        amount /= 1000.0
    elif unit.startswith("m"):
        pass
    else:
        amount /= 1_000_000.0

    return round(amount, 4)


def _extract_offering_amount_m(text):
    patterns = [
        r"(?:aggregate|gross)\s+(?:offering\s+price|proceeds|purchase\s+price|amount)[^$]{0,180}\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?",
        r"(?:aggregate|gross)\s+(?:offering\s+price|proceeds|purchase\s+price|amount)[^$]{0,180}\$\s*([\d,]+(?:\.\d+)?)",
        r"up\s+to\s+\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?",
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|billion|thousand)?[^.]{0,80}(?:offering|proceeds)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            unit = match.group(2) if match.lastindex and match.lastindex >= 2 else ""
            amount = _money_to_m(match.group(1), unit)
            if amount is not None and amount > 0:
                return amount

    return None


def _extract_shares_offered(text):
    patterns = [
        r"(?:we are|we're)\s+offering\s+([\d,]+)\s+(?:shares|ordinary shares)",
        r"offering\s+(?:of|up to)\s+([\d,]+)\s+(?:shares|ordinary shares)",
        r"up to\s+([\d,]+)\s+(?:shares|ordinary shares)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            try:
                return int(match.group(1).replace(",", ""))
            except ValueError:
                pass

    return None


def _analyze_filing(item):
    key = item["filing_path"]
    if key in _filing_cache:
        return _filing_cache[key]

    try:
        r = requests.get(
            _filing_url(key),
            headers=_headers(),
            timeout=12,
        )
        r.raise_for_status()
        text = _clean_filing_text(r.text)
    except Exception:
        _filing_cache[key] = None
        return None

    lower = text.lower()
    atm = bool(
        re.search(r"at[- ]the[- ]market", lower)
        or re.search(r"atm sales agreement", lower)
    )
    pre_funded = "pre-funded warrant" in lower or "prefunded warrant" in lower
    warrants = bool(re.search(r"\bwarrants?\b", lower))
    purchase_agreement = "securities purchase agreement" in lower
    registered_direct = "registered direct offering" in lower
    public_offering = "public offering" in lower
    rights_offering = "rights offering" in lower

    amount_m = _extract_offering_amount_m(text)
    shares_offered = _extract_shares_offered(text)

    offering_type = []
    if registered_direct:
        offering_type.append("registered_direct")
    if public_offering:
        offering_type.append("public_offering")
    if atm:
        offering_type.append("atm")
    if rights_offering:
        offering_type.append("rights_offering")
    if purchase_agreement:
        offering_type.append("purchase_agreement")

    analysis = {
        "verified": True,
        "offering_type": offering_type,
        "offering_amount_m": amount_m,
        "shares_offered": shares_offered,
        "pre_funded_warrants": pre_funded,
        "warrants": warrants,
        "atm": atm,
        "registered_direct": registered_direct,
        "public_offering": public_offering,
        "rights_offering": rights_offering,
        "purchase_agreement": purchase_agreement,
        "dilution_language": bool(re.search(r"\bdilution\b|diluted", lower)),
    }

    _filing_cache[key] = analysis
    return analysis


def _check_filing(item):
    return item["symbol"], _analyze_filing(item)


def _issuance_quality(filing, analysis):
    if not analysis:
        return 0, ["filing ej verifierad"], "OKÄND"

    market_cap_m = filing.get("market_cap_m")
    amount_m = analysis.get("offering_amount_m")
    ratio = None
    if market_cap_m and amount_m is not None and market_cap_m > 0:
        ratio = amount_m / market_cap_m

    score = 0
    reasons = []

    concrete = bool(
        analysis.get("registered_direct")
        or analysis.get("purchase_agreement")
        or analysis.get("rights_offering")
    )
    if concrete:
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

    if ratio is None:
        dilution_risk = "OKÄND"
    elif ratio >= 0.5:
        dilution_risk = "HÖG"
    elif ratio >= 0.2:
        dilution_risk = "MEDEL"
    else:
        dilution_risk = "LÅG"

    return score, reasons, dilution_risk


def discover_issuance_candidates(days=7, limit=25):
    days = max(1, min(int(days), 14))
    limit = max(1, min(int(limit), 50))

    ticker_map = _get_ticker_map()

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)

    # One strongest/recent filing per ticker.
    by_ticker = {}
    errors = []
    days_checked = 0

    for offset in range(days + 1):
        day = start + timedelta(days=offset)

        # SEC publishes the current business-day daily index later in the
        # evening (ET). Do not request today's index before it is published.
        if day >= today:
            continue

        if day.weekday() >= 5:
            continue

        try:
            r = requests.get(
                _index_url(day),
                headers=_headers(),
                timeout=12,
            )

            if r.status_code == 404:
                continue

            r.raise_for_status()
            index_rows = _parse_master_index(r.text)
            days_checked += 1

        except Exception as exc:
            errors.append(f"{day.isoformat()}: {exc}")
            continue

        for item in index_rows:
            form = item["form"]

            if form not in OFFERING_FORMS:
                continue

            identity = ticker_map.get(item["cik"])
            if not identity:
                continue

            ticker = identity["ticker"]
            company_name = identity["company_name"]

            if not ticker or len(ticker) > 8:
                continue

            if _looks_like_fund(company_name):
                continue

            score, reasons = _score(form)

            parts = item["filename"].split("/")
            accession = ""

            if (
                len(parts) >= 4
                and parts[0] == "edgar"
                and parts[1] == "data"
            ):
                accession = parts[3].replace(".txt", "").replace("-", "")

            filing = {
                "symbol": ticker,
                "company_name": company_name,
                "cik": item["cik"],
                "form": form,
                "filing_date": item["filing_date"],
                "accession": accession,
                "filing_path": item["filename"],
                "issuance_score": score,
                "issuance_reasons": reasons,
                "source": "SEC EDGAR daily index",
            }

            previous = by_ticker.get(ticker)

            if previous is None or (
                filing["issuance_score"],
                filing["filing_date"],
            ) > (
                previous["issuance_score"],
                previous["filing_date"],
            ):
                by_ticker[ticker] = filing

    # Prefer recent filings and strongest offering forms before the
    # expensive market-cap checks. This keeps Render fast.
    sec_candidates = sorted(
        by_ticker.values(),
        key=lambda x: (
            x.get("issuance_score", 0),
            x.get("filing_date") or "",
        ),
        reverse=True,
    )

    profile_candidates = sec_candidates[:MAX_PROFILE_CHECKS]

    market_caps = {}
    if FINNHUB_API_KEY and profile_candidates:
        workers = max(1, min(PROFILE_WORKERS, len(profile_candidates)))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_check_profile, item)
                for item in profile_candidates
            ]

            for future in as_completed(futures):
                try:
                    symbol, market_cap_m = future.result()
                    market_caps[symbol] = market_cap_m
                except Exception:
                    continue

    filing_candidates = []
    for item in profile_candidates:
        market_cap_m = market_caps.get(item["symbol"])
        if market_cap_m is not None and market_cap_m <= MAX_MARKET_CAP_M:
            item["market_cap_m"] = round(market_cap_m, 2)
            filing_candidates.append(item)

    filing_candidates = filing_candidates[:MAX_FILING_CHECKS]
    filing_analyses = {}
    if filing_candidates:
        workers = max(1, min(PROFILE_WORKERS, len(filing_candidates)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(_check_filing, item)
                for item in filing_candidates
            ]
            for future in as_completed(futures):
                try:
                    symbol, analysis = future.result()
                    filing_analyses[symbol] = analysis
                except Exception:
                    continue

    results = []
    excluded_large_cap = 0
    missing_market_cap = 0
    not_profile_checked = max(0, len(sec_candidates) - len(profile_candidates))

    for filing in profile_candidates:
        ticker = filing["symbol"]
        market_cap_m = market_caps.get(ticker)

        if market_cap_m is None:
            missing_market_cap += 1
            continue

        if market_cap_m > MAX_MARKET_CAP_M:
            excluded_large_cap += 1
            continue

        filing["market_cap_m"] = round(market_cap_m, 2)

        filing_analysis = None
        if ticker in filing_analyses:
            filing_analysis = filing_analyses[ticker]

        quality_score, quality_reasons, dilution_risk = _issuance_quality(
            filing, filing_analysis
        )
        filing["filing_analysis"] = filing_analysis or {
            "verified": False
        }
        filing["issuance_quality_score"] = max(0, min(100, 50 + quality_score))
        filing["dilution_risk"] = dilution_risk
        filing["issuance_reasons"].extend(quality_reasons)

        if market_cap_m <= 100:
            filing["issuance_score"] = min(
                100, filing["issuance_score"] + 15
            )
            filing["issuance_reasons"].append("microcap")
        elif market_cap_m <= 500:
            filing["issuance_score"] = min(
                100, filing["issuance_score"] + 10
            )
            filing["issuance_reasons"].append("smallcap")
        else:
            filing["issuance_reasons"].append("under_2b_market_cap")

        results.append(filing)

    results.sort(
        key=lambda x: (
            x.get("issuance_score", 0),
            x.get("filing_date") or "",
            -x.get("market_cap_m", 999999999),
        ),
        reverse=True,
    )

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
        "filings_verified": sum(1 for value in filing_analyses.values() if value),
        "not_profile_checked": not_profile_checked,
        "excluded_large_cap": excluded_large_cap,
        "missing_market_cap": missing_market_cap,
        "count": len(results[:limit]),
        "results": results[:limit],
        "errors": errors,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
