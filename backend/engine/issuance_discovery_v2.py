import os
import time
import requests
from datetime import datetime, timezone, timedelta

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "TradePilotAI research contact@example.com",
)

# Broad enough to catch the financing language actually used in filings.
ISSUANCE_QUERIES = [
    '"registered direct" OR "public offering" OR "underwritten offering"',
    '"convertible" OR "equity line" OR "securities purchase agreement"',
    '"pre-funded warrant" OR "warrant" OR "offering"',
    '"purchase agreement" OR "subscription agreement" OR "private placement"',
]

INTERESTING_FORMS = {
    "S-1", "S-1/A", "S-3", "S-3/A",
    "F-1", "F-1/A", "F-3", "F-3/A",
    "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424B8",
    "8-K", "6-K",
}

_ticker_cache = None


def _get_ticker_map():
    global _ticker_cache

    if _ticker_cache is not None:
        return _ticker_cache

    r = requests.get(
        TICKERS_URL,
        headers={"User-Agent": SEC_USER_AGENT},
        timeout=20,
    )
    r.raise_for_status()

    data = r.json()
    mapping = {}

    for row in data.values():
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

    _ticker_cache = mapping
    return mapping


def _extract_ciks(src):
    raw = (
        src.get("ciks")
        or src.get("cik")
        or src.get("cik_str")
        or ""
    )

    if isinstance(raw, list):
        values = raw
    else:
        values = [raw]

    out = []

    for value in values:
        digits = "".join(ch for ch in str(value) if ch.isdigit())

        if digits:
            out.append(digits.zfill(10))

    return out


def _search(q, start_date, end_date, limit=100):
    params = {
        "q": q,
        "dateRange": "custom",
        "startdt": start_date,
        "enddt": end_date,
        "from": 0,
        "size": min(max(limit, 1), 100),
    }

    r = requests.get(
        EFTS_URL,
        params=params,
        headers={"User-Agent": SEC_USER_AGENT},
        timeout=25,
    )
    r.raise_for_status()

    data = r.json()

    if data.get("errorType"):
        raise RuntimeError(
            data.get("errorMessage", "SEC search error")
        )

    return (data.get("hits") or {}).get("hits") or []


def _score(form, description, query):
    text = f"{form} {description} {query}".lower()
    score = 0
    reasons = []

    if form.upper().startswith(("S-1", "S-3", "F-1", "F-3")):
        score += 25
        reasons.append("registrering")

    if form.upper().startswith("424B"):
        score += 40
        reasons.append("prospekt/erbjudande")

    if "registered direct" in text:
        score += 35
        reasons.append("registered direct")

    if "public offering" in text:
        score += 25
        reasons.append("public offering")

    if "underwritten offering" in text:
        score += 25
        reasons.append("underwritten offering")

    if "equity line" in text:
        score += 35
        reasons.append("equity line")

    if "convertible" in text:
        score += 30
        reasons.append("convertible")

    if "pre-funded warrant" in text:
        score += 30
        reasons.append("pre-funded warrant")

    if "warrant" in text:
        score += 15
        reasons.append("warrants")

    if "securities purchase agreement" in text:
        score += 20
        reasons.append("securities purchase agreement")

    if "private placement" in text:
        score += 20
        reasons.append("private placement")

    if "subscription agreement" in text:
        score += 15
        reasons.append("subscription agreement")

    return min(score, 100), reasons


def discover_issuance_candidates(days=7, limit=25):
    days = max(1, min(int(days), 14))
    limit = max(1, min(int(limit), 50))

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)

    ticker_map = _get_ticker_map()

    rows = {}
    errors = []

    for query in ISSUANCE_QUERIES:
        try:
            hits = _search(
                query,
                start.isoformat(),
                end.isoformat(),
                limit=100,
            )
        except Exception as exc:
            errors.append(str(exc))
            continue

        time.sleep(0.2)

        for hit in hits:
            src = hit.get("_source") or {}

            form = str(
                src.get("form")
                or src.get("formType")
                or ""
            ).upper().strip()

            if form not in INTERESTING_FORMS:
                continue

            ciks = _extract_ciks(src)

            # Some EFTS results do not expose a ticker. Resolve CIK -> ticker
            # using the SEC's official company_tickers file.
            identity = None
            for cik in ciks:
                if cik in ticker_map:
                    identity = ticker_map[cik]
                    break

            if not identity:
                continue

            ticker = identity["ticker"]

            if not ticker or len(ticker) > 8:
                continue

            filed_at = (
                src.get("file_date")
                or src.get("filedAt")
            )

            description = str(
                src.get("display_names")
                or src.get("description")
                or ""
            )

            accession = (
                src.get("adsh")
                or src.get("accession_no")
                or ""
            )

            if not accession:
                hit_id = str(hit.get("_id") or "")
                accession = hit_id.split(":", 1)[0]

            score, reasons = _score(
                form,
                description,
                query,
            )

            key = f"{ticker}:{accession}:{form}"

            row = {
                "symbol": ticker,
                "company_name": identity["company_name"],
                "form": form,
                "filing_date": filed_at,
                "accession": accession,
                "description": description[:500],
                "issuance_score": score,
                "issuance_reasons": reasons,
                "source": "SEC EDGAR EFTS",
            }

            old = rows.get(key)

            if old is None or row["issuance_score"] > old["issuance_score"]:
                rows[key] = row

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
        "source": "SEC EDGAR EFTS",
        "selection": (
            "recent SEC filings linked to new share supply / financing"
        ),
        "days": days,
        "count": len(results[:limit]),
        "results": results[:limit],
        "errors": errors,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }
