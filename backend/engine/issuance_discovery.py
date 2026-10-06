import os
import time
import requests
from datetime import datetime, timezone, timedelta

EFTS_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "TradePilotAI research contact@example.com",
)

# Focused on new share supply / financing events.
ISSUANCE_QUERIES = [
    '"registered direct offering" OR "public offering" OR "underwritten offering"',
    '"equity line" OR "convertible note" OR "convertible securities"',
    '"warrant" OR "pre-funded warrant" OR "purchase agreement"',
]

ISSUANCE_FORMS = "S-1,S-3,F-1,F-3,424B,8-K"


def _search(q, start_date, end_date, limit=50):
    params = {
        "q": q,
        "forms": ISSUANCE_FORMS,
        "dateRange": "custom",
        "startdt": start_date,
        "enddt": end_date,
        "from": 0,
    }

    r = requests.get(
        EFTS_URL,
        params=params,
        headers={"User-Agent": SEC_USER_AGENT},
        timeout=20,
    )
    r.raise_for_status()

    data = r.json()
    if data.get("errorType"):
        raise RuntimeError(data.get("errorMessage", "SEC search error"))

    hits = (data.get("hits") or {}).get("hits") or []
    return hits[:limit]


def _score(form, description):
    text = f"{form} {description}".lower()
    score = 0
    reasons = []

    if "424b" in form.lower():
        score += 35
        reasons.append("prospekt/erbjudande")

    if form.upper().startswith(("S-1", "S-3", "F-1", "F-3")):
        score += 20
        reasons.append("registrering av värdepapper")

    if "registered direct" in text:
        score += 30
        reasons.append("registered direct")

    if "equity line" in text:
        score += 30
        reasons.append("equity line")

    if "convertible" in text:
        score += 25
        reasons.append("convertible")

    if "pre-funded warrant" in text:
        score += 25
        reasons.append("pre-funded warrant")

    if "warrant" in text:
        score += 10
        reasons.append("warrants")

    if "purchase agreement" in text:
        score += 10
        reasons.append("purchase agreement")

    return min(score, 100), reasons


def discover_issuance_candidates(days=7, limit=25):
    days = max(1, min(int(days), 14))
    limit = max(1, min(int(limit), 50))

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)

    rows = {}
    errors = []

    for query in ISSUANCE_QUERIES:
        try:
            hits = _search(
                query,
                start.isoformat(),
                end.isoformat(),
                limit=50,
            )
        except Exception as exc:
            errors.append(str(exc))
            continue

        # Keep requests comfortably below SEC fair-access limits.
        time.sleep(0.2)

        for hit in hits:
            src = hit.get("_source") or {}

            ticker = src.get("ticker")
            if not ticker:
                continue

            ticker = str(ticker).upper().strip()

            # Avoid obvious non-ticker values.
            if not ticker or len(ticker) > 8:
                continue

            accession = (
                hit.get("_id", "").split(":", 1)[0]
                or src.get("accession_no")
            )
            if not accession:
                continue

            form = str(
                src.get("form", "")
                or src.get("formType", "")
            )

            filed_at = (
                src.get("file_date")
                or src.get("filedAt")
            )

            description = str(
                src.get("display_names")
                or src.get("description")
                or ""
            )

            score, reasons = _score(form, description)

            key = f"{ticker}:{accession}"

            row = {
                "symbol": ticker,
                "company_name": str(
                    src.get("entity_name")
                    or src.get("companyNameLong")
                    or ""
                ).replace(" (Filer)", "").strip(),
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
