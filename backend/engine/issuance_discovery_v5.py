import os
import requests
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

MAX_MARKET_CAP_M = float(os.getenv("TRADEPILOT_ISSUANCE_MAX_MARKET_CAP_M", "2000"))
PROFILE_TIMEOUT = 12

_ticker_map = None
_profile_cache = {}


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


def _profile(symbol):
    """Fetch Finnhub profile once per symbol and cache it."""
    if symbol in _profile_cache:
        return _profile_cache[symbol]

    if not FINNHUB_API_KEY:
        _profile_cache[symbol] = None
        return None

    try:
        r = requests.get(
            f"{FINNHUB_BASE_URL}/stock/profile2",
            params={"symbol": symbol, "token": FINNHUB_API_KEY},
            timeout=PROFILE_TIMEOUT,
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

    raw = profile.get("marketCapitalization")

    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    # Finnhub marketCapitalization is reported in millions.
    return value


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


def discover_issuance_candidates(days=7, limit=25):
    days = max(1, min(int(days), 14))
    limit = max(1, min(int(limit), 50))

    ticker_map = _get_ticker_map()

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)

    # First collect filings, then deduplicate by ticker.
    by_ticker = {}
    errors = []
    days_checked = 0

    for offset in range(days + 1):
        day = start + timedelta(days=offset)

        if day.weekday() >= 5:
            continue

        try:
            r = requests.get(
                _index_url(day),
                headers=_headers(),
                timeout=20,
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

            if len(parts) >= 4 and parts[0] == "edgar" and parts[1] == "data":
                accession = parts[3].replace("-", "")

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

            # Keep the strongest/recent filing for each ticker.
            previous = by_ticker.get(ticker)

            if previous is None or (
                filing["issuance_score"],
                filing["filing_date"],
            ) > (
                previous["issuance_score"],
                previous["filing_date"],
            ):
                by_ticker[ticker] = filing

    # Market-cap filter is deliberately applied after SEC collection/dedup.
    results = []
    excluded_large_cap = 0
    missing_market_cap = 0

    for ticker, filing in by_ticker.items():
        profile = _profile(ticker)
        market_cap_m = _market_cap_m(profile)

        if market_cap_m is None:
            missing_market_cap += 1
            continue

        if market_cap_m > MAX_MARKET_CAP_M:
            excluded_large_cap += 1
            continue

        filing["market_cap_m"] = round(market_cap_m, 2)

        # Give smaller issuers a modest ranking bonus.
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
            -x.get("market_cap_m", 999999999),
            x.get("filing_date") or "",
        ),
        reverse=True,
    )

    return {
        "ok": True,
        "source": "SEC EDGAR daily index + Finnhub company profile",
        "selection": "recent offering filings from US-listed companies under the market-cap limit",
        "days": days,
        "days_checked": days_checked,
        "max_market_cap_m": MAX_MARKET_CAP_M,
        "unique_sec_candidates": len(by_ticker),
        "excluded_large_cap": excluded_large_cap,
        "missing_market_cap": missing_market_cap,
        "count": len(results[:limit]),
        "results": results[:limit],
        "errors": errors,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
