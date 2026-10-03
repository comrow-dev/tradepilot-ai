from datetime import datetime, timezone
from backend.engine.intelligence import news_catalysts


def _symbols_from_news(item):
    """
    Finnhub general-news items may contain a `related` field with one or
    more ticker symbols. Some feeds may return a comma/space separated string.
    """
    related = item.get("related")

    if not related:
        return []

    if isinstance(related, list):
        values = related
    else:
        values = str(related).replace(";", ",").split(",")

    symbols = []
    for value in values:
        symbol = str(value).strip().upper()
        if symbol and symbol.isalnum() and 1 <= len(symbol) <= 8:
            symbols.append(symbol)

    return list(dict.fromkeys(symbols))


def discover_news_candidates(fh, days=2, limit=25):
    """
    Discover symbols from Finnhub market news without changing the normal
    scan universe.

    Only news that contains an identified catalyst is returned. The
    discovery layer does not create signals or database records.
    """
    raw_news = fh.market_news(days=days)

    discovered = []
    seen = set()

    for item in raw_news or []:
        symbols = _symbols_from_news(item)
        if not symbols:
            continue

        analyzed = news_catalysts([item])

        if not analyzed:
            continue

        article = analyzed[0]

        # General market news without a recognised catalyst must not enter
        # the discovery queue.
        if article.get("catalyst_score", 0) <= 0:
            continue

        for symbol in symbols:
            if symbol in seen:
                continue

            seen.add(symbol)

            discovered.append(
                {
                    "symbol": symbol,
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
                return {
                    "ok": True,
                    "count": len(discovered),
                    "results": discovered,
                    "discovered_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }

    discovered.sort(
        key=lambda x: x.get("catalyst_score", 0),
        reverse=True,
    )

    return {
        "ok": True,
        "count": len(discovered),
        "results": discovered[:limit],
        "discovered_at": datetime.now(
            timezone.utc
        ).isoformat(),
    }
