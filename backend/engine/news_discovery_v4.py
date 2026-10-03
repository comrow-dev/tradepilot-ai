import re
from datetime import datetime, timezone

from backend.engine.intelligence import news_catalysts


# Common uppercase words that can look like tickers in headlines.
_STOP_SYMBOLS = {
    "A", "AI", "AM", "AN", "AS", "AT", "BE", "BY", "CAN", "CEO",
    "CFO", "CO", "DO", "FOR", "FROM", "GDP", "GO", "HAS", "IN",
    "IS", "IT", "ITS", "NEWS", "NEW", "NO", "OF", "ON", "OR",
    "Q1", "Q2", "Q3", "Q4", "THE", "TO", "US", "USA", "USD",
    "VS", "WE", "WITH", "YOU",
}

# Small-cap discovery gate.
# Finnhub company profile marketCapitalization is expressed in USD millions.
MAX_MARKET_CAP_MILLIONS = 2000
MAX_DIAGNOSTIC_CANDIDATES = 50


def _related_symbols(item):
    related = item.get("related")
    if not related:
        return []

    values = related if isinstance(related, list) else re.split(r"[,;\s]+", str(related))
    return _clean_symbols(values)


def _headline_symbols(item):
    text = " ".join(
        [
            str(item.get("headline") or ""),
            str(item.get("summary") or ""),
        ]
    )

    # Conservative fallback: only explicit all-caps ticker-like tokens.
    tokens = re.findall(
        r"(?<![A-Za-z0-9])\$?([A-Z][A-Z0-9.-]{0,5})(?![A-Za-z0-9])",
        text,
    )

    return _clean_symbols(tokens)


def _clean_symbols(values):
    result = []

    for value in values:
        symbol = str(value).strip().upper().lstrip("$")

        if not symbol:
            continue
        if symbol in _STOP_SYMBOLS:
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,5}", symbol):
            continue
        if symbol not in result:
            result.append(symbol)

    return result


def _verify_symbol(fh, symbol):
    """
    Verify ticker and apply the small-cap gate.

    Returns:
        (True, market_cap_millions, "accepted") when the company is verified
        and its market cap is at or below MAX_MARKET_CAP_MILLIONS.

        (False, market_cap_millions, reason) otherwise.
    """
    try:
        profile = fh.company_profile(symbol)

        if not profile or not profile.get("name"):
            return False, None, "company_not_found"

        raw_cap = profile.get("marketCapitalization")
        if raw_cap is None:
            return False, None, "no_market_cap"

        market_cap_millions = float(raw_cap)

        if market_cap_millions <= 0:
            return False, market_cap_millions, "invalid_market_cap"

        if market_cap_millions > MAX_MARKET_CAP_MILLIONS:
            return False, market_cap_millions, "large_cap"

        quote = fh.quote(symbol)
        price = quote.get("c")

        if price is None or float(price) <= 0:
            return False, market_cap_millions, "invalid_quote"

        return True, market_cap_millions, "accepted"

    except (TypeError, ValueError):
        return False, None, "invalid_profile_data"
    except Exception:
        return False, None, "verification_error"


def discover_news_candidates(fh, days=2, limit=25):
    """
    News Discovery v4.

    Discovery sources:
      1. Finnhub's explicit `related` symbols.
      2. Conservative ticker-like tokens in headline/summary.

    Candidate diagnostics now explain why discovered ticker candidates were
    accepted or rejected. This is diagnostic only: it does not create signals,
    modify the scan universe, or write to the learning database.
    """
    raw_news = fh.market_news(days=days)

    discovered = []
    seen = set()
    diagnostic_seen = set()

    inspected_articles = 0
    articles_with_symbols = 0
    candidates_rejected_large_cap = 0
    candidates_rejected_no_catalyst = 0

    candidate_diagnostics = []

    for item in raw_news or []:
        inspected_articles += 1

        symbols = _related_symbols(item)
        symbols.extend(_headline_symbols(item))
        symbols = list(dict.fromkeys(symbols))

        if not symbols:
            continue

        articles_with_symbols += 1

        analyzed = news_catalysts([item])
        article = analyzed[0] if analyzed else {}

        catalyst_score = article.get("catalyst_score", 0) or 0

        for symbol in symbols:
            if symbol in diagnostic_seen:
                continue

            diagnostic_seen.add(symbol)

            if catalyst_score <= 0:
                candidates_rejected_no_catalyst += 1

                if len(candidate_diagnostics) < MAX_DIAGNOSTIC_CANDIDATES:
                    candidate_diagnostics.append(
                        {
                            "symbol": symbol,
                            "status": "rejected",
                            "reason": "no_catalyst",
                            "market_cap_millions": None,
                            "catalyst_score": 0,
                            "headline": item.get("headline"),
                        }
                    )
                continue

            verified, market_cap_millions, reason = _verify_symbol(
                fh, symbol
            )

            if not verified:
                if reason == "large_cap":
                    candidates_rejected_large_cap += 1

                if len(candidate_diagnostics) < MAX_DIAGNOSTIC_CANDIDATES:
                    candidate_diagnostics.append(
                        {
                            "symbol": symbol,
                            "status": "rejected",
                            "reason": reason,
                            "market_cap_millions": (
                                round(market_cap_millions, 2)
                                if market_cap_millions is not None
                                else None
                            ),
                            "catalyst_score": catalyst_score,
                            "headline": article.get("headline")
                            or item.get("headline"),
                        }
                    )
                continue

            if symbol in seen:
                continue

            seen.add(symbol)

            discovered.append(
                {
                    "symbol": symbol,
                    "market_cap_millions": round(market_cap_millions, 2),
                    "headline": article.get("headline"),
                    "summary": article.get("summary"),
                    "source": article.get("source"),
                    "url": article.get("url"),
                    "datetime": article.get("datetime"),
                    "catalysts": article.get("catalysts", []),
                    "catalyst_type": article.get(
                        "catalyst_type", "NONE"
                    ),
                    "catalyst_score": catalyst_score,
                }
            )

            if len(candidate_diagnostics) < MAX_DIAGNOSTIC_CANDIDATES:
                candidate_diagnostics.append(
                    {
                        "symbol": symbol,
                        "status": "accepted",
                        "reason": "accepted",
                        "market_cap_millions": round(
                            market_cap_millions, 2
                        ),
                        "catalyst_score": catalyst_score,
                        "headline": article.get("headline"),
                    }
                )

            if len(discovered) >= limit:
                break

        if len(discovered) >= limit:
            break

    discovered.sort(
        key=lambda x: (
            x.get("catalyst_score", 0),
            x.get("datetime") or "",
        ),
        reverse=True,
    )

    return {
        "ok": True,
        "count": len(discovered),
        "results": discovered[:limit],
        "diagnostics": {
            "articles_inspected": inspected_articles,
            "articles_with_symbol_candidates": articles_with_symbols,
            "candidates_rejected_large_cap": candidates_rejected_large_cap,
            "candidates_rejected_no_catalyst": candidates_rejected_no_catalyst,
            "max_market_cap_millions": MAX_MARKET_CAP_MILLIONS,
            "candidate_diagnostics": candidate_diagnostics,
        },
        "discovered_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }
