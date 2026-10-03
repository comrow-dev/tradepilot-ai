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
        (True, market_cap_millions) when the company is verified and
        its market cap is at or below MAX_MARKET_CAP_MILLIONS.
        (False, None) otherwise.
    """
    try:
        profile = fh.company_profile(symbol)
        if not profile or not profile.get("name"):
            return False, None

        raw_cap = profile.get("marketCapitalization")
        if raw_cap is None:
            return False, None

        market_cap_millions = float(raw_cap)

        if market_cap_millions <= 0:
            return False, None

        if market_cap_millions > MAX_MARKET_CAP_MILLIONS:
            return False, market_cap_millions

        quote = fh.quote(symbol)
        price = quote.get("c")
        if price is None or float(price) <= 0:
            return False, market_cap_millions

        return True, market_cap_millions

    except (TypeError, ValueError):
        return False, None
    except Exception:
        return False, None


def discover_news_candidates(fh, days=2, limit=25):
    """
    News Discovery v3.

    Discovery sources:
      1. Finnhub's explicit `related` symbols.
      2. Conservative ticker-like tokens in headline/summary.

    Every candidate must then:
      - resolve to a real company/ticker;
      - have a usable market cap;
      - be <= MAX_MARKET_CAP_MILLIONS;
      - contain an identified catalyst.

    This module only returns discovery results. It does not create signals,
    modify the scan universe, or write to the learning database.
    """
    raw_news = fh.market_news(days=days)

    discovered = []
    seen = set()
    inspected_articles = 0
    articles_with_symbols = 0
    candidates_rejected_large_cap = 0

    for item in raw_news or []:
        inspected_articles += 1

        symbols = _related_symbols(item)
        symbols.extend(_headline_symbols(item))
        symbols = list(dict.fromkeys(symbols))

        if not symbols:
            continue

        articles_with_symbols += 1

        analyzed = news_catalysts([item])
        if not analyzed:
            continue

        article = analyzed[0]

        # General news without a recognized catalyst never enters discovery.
        if article.get("catalyst_score", 0) <= 0:
            continue

        for symbol in symbols:
            if symbol in seen:
                continue

            verified, market_cap_millions = _verify_symbol(fh, symbol)

            if (
                not verified
                and market_cap_millions is not None
                and market_cap_millions > MAX_MARKET_CAP_MILLIONS
            ):
                candidates_rejected_large_cap += 1

            if not verified:
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
                    "catalyst_score": article.get(
                        "catalyst_score", 0
                    ),
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
            "max_market_cap_millions": MAX_MARKET_CAP_MILLIONS,
        },
        "discovered_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }
