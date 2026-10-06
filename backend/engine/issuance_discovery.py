import os
import requests
from datetime import datetime, timezone, timedelta

SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "TradePilotAI research contact@example.com",
)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# We deliberately use EDGAR daily index files instead of EFTS.
# This avoids depending on full-text search result fields such as ticker.
OFFERING_FORMS = {
    "S-1", "S-1/A",
    "S-3", "S-3/A",
    "F-1", "F-1/A",
    "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4",
    "424B5", "424B7", "424B8",
}

_ticker_map = None


def _headers():
    return {
        "User-Agent": SEC_USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    }


def _get_ticker_map():
    global _ticker_map

    if _ticker_map is not None:
        return _ticker_map

    r = requests.get(
        TICKERS_URL,
        headers=_headers(),
        timeout=20,
    )
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
    year = date_obj.year
    quarter = _quarter(date_obj)
    stamp = date_obj.strftime("%Y%m%d")

    return (
        f"https://www.sec.gov/Archives/edgar/daily-index/"
        f"{year}/QTR{quarter}/master.{stamp}.idx"
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

        # SEC master.idx is pipe-delimited:
        # CIK|Company Name|Form Type|Date Filed|Filename
        parts = line.split("|")

        if len(parts) != 5:
            continue

        cik, company, form, filing_date, filename = [
            p.strip() for p in parts
        ]

        rows.append({
            "cik": cik.zfill(10),
            "company_name": company,
            "form": form,
            "filing_date": filing_date,
            "filename": filename,
        })

    return rows


def _score(form):
    form = form.upper()
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


def discover_issuance_candidates(days=7, limit=25):
    days = max(1, min(int(days), 14))
    limit = max(1, min(int(limit), 50))

    ticker_map = _get_ticker_map()

    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=days)

    rows = {}
    errors = []
    days_checked = 0

    for offset in range(days + 1):
        day = start + timedelta(days=offset)

        # EDGAR daily index is published for filing/business days.
        if day.weekday() >= 5:
            continue

        url = _index_url(day)

        try:
            r = requests.get(
                url,
                headers=_headers(),
                timeout=20,
            )

            if r.status_code == 404:
                # Weekend/holiday/no index for this date.
                continue

            r.raise_for_status()
            index_rows = _parse_master_index(r.text)
            days_checked += 1

        except Exception as exc:
            errors.append(f"{day.isoformat()}: {exc}")
            continue

        for item in index_rows:
            form = item["form"].upper()

            if form not in OFFERING_FORMS:
                continue

            identity = ticker_map.get(item["cik"])

            if not identity:
                continue

            ticker = identity["ticker"]

            if not ticker or len(ticker) > 8:
                continue

            score, reasons = _score(form)

            accession = ""
            parts = item["filename"].split("/")

            # Typical filename:
            # edgar/data/CIK/ACCESSION/PRIMARY-DOCUMENT
            if len(parts) >= 4 and parts[0] == "edgar" and parts[1] == "data":
                accession = parts[3].replace("-", "")

            key = f"{ticker}:{accession}:{form}"

            rows[key] = {
                "symbol": ticker,
                "company_name": identity["company_name"],
                "cik": item["cik"],
                "form": form,
                "filing_date": item["filing_date"],
                "accession": accession,
                "filing_path": item["filename"],
                "issuance_score": score,
                "issuance_reasons": reasons,
                "source": "SEC EDGAR daily index",
            }

    results = sorted(
        rows.values(),
        key=lambda x: (
            x.get("issuance_score", 0),
            x.get("filing_date") or "",
        ),
        reverse=True,
    )

    return {
        "ok": True,
        "source": "SEC EDGAR daily index",
        "selection": "recent registration statements and offering prospectuses",
        "days": days,
        "days_checked": days_checked,
        "count": len(results[:limit]),
        "results": results[:limit],
        "errors": errors,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
