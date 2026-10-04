import re
import time
from datetime import datetime, timedelta, timezone

from backend.engine.intelligence import news_catalysts

MAX_MARKET_CAP_MILLIONS = 2000
MAX_DIAGNOSTIC_CANDIDATES = 50
_SYMBOL_DIRECTORY_CACHE = None

_STOP_SYMBOLS = {
    "A","AI","AM","AN","AS","AT","BE","BY","CAN","CEO","CFO","CO","DO",
    "FOR","FROM","GDP","GO","HAS","IN","IS","IT","ITS","NEWS","NEW","NO",
    "OF","ON","OR","Q1","Q2","Q3","Q4","THE","TO","US","USA","USD","VS",
    "WE","WITH","YOU","UK","EU","UAE","UN","NATO","OPEC","SEC","NASA",
    "ISS","IEA","RBI","IPO","IBM"
}
_COMPANY_SUFFIXES = re.compile(
    r"\b(incorporated|inc|corp|corporation|company|co|plc|limited|ltd|"
    r"holdings|holding|group|sa|ag|nv|lp|llc)\b", re.I
)

def _normalize_company_name(value):
    text = str(value or "").lower()
    text = _COMPANY_SUFFIXES.sub(" ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())

def _stock_symbol_directory(fh):
    global _SYMBOL_DIRECTORY_CACHE
    if _SYMBOL_DIRECTORY_CACHE is not None:
        return _SYMBOL_DIRECTORY_CACHE
    try:
        rows = fh.request("/stock/symbol", {"exchange": "US"}, timeout=20) or []
    except Exception:
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol") or row.get("displaySymbol")
        name = row.get("description") or row.get("name")
        if not symbol or not name or row.get("type") not in (None, "Common Stock"):
            continue
        normalized = _normalize_company_name(name)
        if len(normalized) >= 5:
            result.append((str(symbol).upper(), normalized, str(name)))
    _SYMBOL_DIRECTORY_CACHE = result
    return result

def _clean_symbols(values):
    out = []
    for value in values:
        symbol = str(value).strip().upper().lstrip("$")
        if not symbol or symbol in _STOP_SYMBOLS:
            continue
        if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,5}", symbol):
            continue
        if symbol not in out:
            out.append(symbol)
    return out

def _related_symbols(item):
    related = item.get("related")
    if not related:
        return []
    values = related if isinstance(related, list) else re.split(r"[,;\s]+", str(related))
    return _clean_symbols(values)

def _headline_symbols(item):
    text = " ".join([str(item.get("headline") or ""), str(item.get("summary") or "")])
    tokens = re.findall(
        r"(?<![A-Za-z0-9])\$([A-Z][A-Z0-9.-]{0,5})(?![A-Za-z0-9])", text
    )
    tokens += re.findall(
        r"\b(?:NASDAQ|NYSE|AMEX|OTC)(?:\s*:\s*)([A-Z][A-Z0-9.-]{0,5})\b", text
    )
    return _clean_symbols(tokens)

def _build_company_index(directory):
    """
    Build targeted indexes for company-name matching.

    The first-token index handles one-word names and broad matching. The
    phrase index uses the first two distinctive words of multi-word names,
    avoiding a scan of the full symbol directory for every article.
    """
    first_index = {}
    phrase_index = {}

    for symbol, name, display_name in directory:
        tokens = name.split()
        if not tokens:
            continue

        first_index.setdefault(tokens[0], []).append(
            (symbol, name, display_name)
        )

        if len(tokens) >= 2 and all(len(token) >= 4 for token in tokens[:2]):
            phrase = " ".join(tokens[:2])
            phrase_index.setdefault(phrase, []).append(
                (symbol, name, display_name)
            )

    return {"first": first_index, "phrase": phrase_index}


def _company_name_symbols(item, company_index):
    text = _normalize_company_name(
        " ".join([str(item.get("headline") or ""), str(item.get("summary") or "")])
    )
    if not text:
        return []

    words = text.split()
    word_set = set(words)
    out = []
    candidates = {}

    # One-word candidates: only inspect companies whose first word occurs.
    for first in word_set:
        for symbol, name, display_name in company_index["first"].get(first, []):
            candidates[symbol] = (symbol, name, display_name)

    # Multi-word candidates: derive article phrases, then look them up directly.
    for index in range(len(words) - 1):
        first, second = words[index], words[index + 1]
        if len(first) < 4 or len(second) < 4:
            continue
        phrase = f"{first} {second}"
        for symbol, name, display_name in company_index["phrase"].get(phrase, []):
            candidates[symbol] = (symbol, name, display_name)

    for symbol, name, _display_name in candidates.values():
        # Exact normalized company-name match remains the strongest signal.
        # For multi-word names, the indexed first-two-word phrase also allows
        # public-facing shortened names such as "Flux Power" to match
        # directory names such as "Flux Power Holdings".
        if re.search(
            r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])",
            text,
        ):
            out.append(symbol)
            continue

        name_words = name.split()
        if len(name_words) >= 2:
            phrase = " ".join(name_words[:2])
            if re.search(
                r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])",
                text,
            ):
                out.append(symbol)

    return list(dict.fromkeys(out))

def _verify_symbol(fh, symbol):
    try:
        profile = fh.company_profile(symbol)
        if not profile or not profile.get("name"):
            return False, None, "company_not_found"
        raw_cap = profile.get("marketCapitalization")
        if raw_cap is None:
            return False, None, "no_market_cap"
        cap = float(raw_cap)
        if cap <= 0:
            return False, cap, "invalid_market_cap"
        if cap > MAX_MARKET_CAP_MILLIONS:
            return False, cap, "large_cap"
        quote = fh.quote(symbol)
        price = quote.get("c")
        if price is None or float(price) <= 0:
            return False, cap, "invalid_quote"
        return True, cap, "accepted"
    except (TypeError, ValueError):
        return False, None, "invalid_profile_data"
    except Exception:
        return False, None, "verification_error"


def _market_news_multi_category(fh, days):
    """
    Combine multiple Finnhub market-news categories and apply the requested
    date window locally. This broadens discovery without changing the
    small-cap or catalyst rules.
    """
    try:
        days = max(1, min(int(days), 30))
    except (TypeError, ValueError):
        days = 2

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    merged = []
    seen = set()

    for category in ("general", "merger"):
        try:
            rows = fh.request(
                "/news",
                {"category": category},
                timeout=20,
            ) or []
        except Exception:
            continue

        for item in rows:
            if not isinstance(item, dict):
                continue

            raw_dt = item.get("datetime")
            try:
                if isinstance(raw_dt, (int, float)):
                    item_dt = datetime.fromtimestamp(raw_dt, tz=timezone.utc)
                else:
                    item_dt = datetime.fromisoformat(
                        str(raw_dt).replace("Z", "+00:00")
                    )
                    if item_dt.tzinfo is None:
                        item_dt = item_dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue

            if item_dt < cutoff:
                continue

            key = (
                item.get("id"),
                item.get("url"),
                item.get("headline"),
                item.get("datetime"),
            )
            if key in seen:
                continue

            seen.add(key)
            merged.append(item)

    merged.sort(key=lambda x: x.get("datetime") or 0, reverse=True)
    return merged


def discover_news_candidates(fh, days=2, limit=25):
    """
    News Discovery v13 diagnostic build.
    Uses targeted company-name indexes and per-request verification caching
    to improve discovery coverage and reduce repeated Finnhub calls.
    No DB writes and no trading signals.
    """
    timings = {}
    t0 = time.perf_counter()
    debug = {
        "symbol_directory_error": None,
        "symbol_directory_sample": [],
        "news_sample": [],
        "article_symbol_debug": [],
    }

    t = time.perf_counter()
    try:
        raw_news = _market_news_multi_category(fh, days)
    except Exception as exc:
        debug["news_fetch_error"] = f"{type(exc).__name__}: {exc}"
        raw_news = []
    timings["news_fetch_seconds"] = round(time.perf_counter() - t, 3)
    debug["news_categories"] = ["general", "merger"]
    debug["news_total_articles"] = len(raw_news)

    if raw_news:
        for item in raw_news[:5]:
            debug["news_sample"].append({
                "headline": item.get("headline"),
                "source": item.get("source"),
                "related": item.get("related"),
                "datetime": item.get("datetime"),
            })

    t = time.perf_counter()
    try:
        directory = _stock_symbol_directory(fh)
    except Exception as exc:
        directory = []
        debug["symbol_directory_error"] = f"{type(exc).__name__}: {exc}"
    timings["symbol_directory_seconds"] = round(time.perf_counter() - t, 3)
    timings["symbol_directory_size"] = len(directory)

    t = time.perf_counter()
    company_index = _build_company_index(directory)
    timings["company_index_seconds"] = round(time.perf_counter() - t, 3)
    timings["company_index_keys"] = len(company_index)

    debug["symbol_directory_sample"] = [
        {"symbol": symbol, "name": display_name}
        for symbol, _normalized, display_name in directory[:10]
    ]

    discovered = []
    diagnostics = []
    seen = set()
    inspected = 0
    articles_with_symbols = 0
    rejected_large = 0
    rejected_no_catalyst = 0
    catalyst_seconds = 0.0
    verification_seconds = 0.0
    verification_cache = {}
    verification_cache_hits = 0

    for item in raw_news or []:
        inspected += 1

        related_symbols = _related_symbols(item)
        headline_symbols = _headline_symbols(item)
        company_symbols = _company_name_symbols(item, company_index)

        symbols = list(dict.fromkeys(
            related_symbols + headline_symbols + company_symbols
        ))

        if len(debug["article_symbol_debug"]) < 20:
            debug["article_symbol_debug"].append({
                "headline": item.get("headline"),
                "related_symbols": related_symbols,
                "headline_symbols": headline_symbols,
                "company_name_symbols": company_symbols,
                "combined_symbols": symbols,
            })
        if not symbols:
            continue
        articles_with_symbols += 1

        t = time.perf_counter()
        analyzed = news_catalysts([item])
        catalyst_seconds += time.perf_counter() - t
        article = analyzed[0] if analyzed else {}
        catalyst_score = article.get("catalyst_score", 0) or 0

        for symbol in symbols:
            if symbol in seen:
                continue

            if catalyst_score <= 0:
                rejected_no_catalyst += 1
                if len(diagnostics) < MAX_DIAGNOSTIC_CANDIDATES:
                    diagnostics.append({
                        "symbol": symbol, "status": "rejected",
                        "reason": "no_catalyst",
                        "catalyst_score": 0,
                        "headline": item.get("headline"),
                    })
                continue

            if symbol in verification_cache:
                verified, cap, reason = verification_cache[symbol]
                verification_cache_hits += 1
            else:
                t = time.perf_counter()
                verification_cache[symbol] = _verify_symbol(fh, symbol)
                verification_seconds += time.perf_counter() - t
                verified, cap, reason = verification_cache[symbol]

            if not verified:
                if reason == "large_cap":
                    rejected_large += 1
                if len(diagnostics) < MAX_DIAGNOSTIC_CANDIDATES:
                    diagnostics.append({
                        "symbol": symbol, "status": "rejected",
                        "reason": reason,
                        "market_cap_millions": round(cap, 2) if cap is not None else None,
                        "catalyst_score": catalyst_score,
                        "headline": article.get("headline") or item.get("headline"),
                    })
                continue

            seen.add(symbol)
            discovered.append({
                "symbol": symbol,
                "market_cap_millions": round(cap, 2),
                "headline": article.get("headline"),
                "summary": article.get("summary"),
                "source": article.get("source"),
                "url": article.get("url"),
                "datetime": article.get("datetime"),
                "catalysts": article.get("catalysts", []),
                "catalyst_type": article.get("catalyst_type", "NONE"),
                "catalyst_score": catalyst_score,
            })

            if len(diagnostics) < MAX_DIAGNOSTIC_CANDIDATES:
                diagnostics.append({
                    "symbol": symbol, "status": "accepted", "reason": "accepted",
                    "market_cap_millions": round(cap, 2),
                    "catalyst_score": catalyst_score,
                    "headline": article.get("headline"),
                })
            if len(discovered) >= limit:
                break

        if len(discovered) >= limit:
            break

    timings["catalyst_analysis_seconds"] = round(catalyst_seconds, 3)
    timings["verification_seconds"] = round(verification_seconds, 3)
    timings["total_seconds"] = round(time.perf_counter() - t0, 3)

    discovered.sort(
        key=lambda x: (x.get("catalyst_score", 0), x.get("datetime") or ""),
        reverse=True,
    )

    return {
        "ok": True,
        "count": len(discovered),
        "results": discovered[:limit],
        "diagnostics": {
            "articles_inspected": inspected,
            "articles_with_symbol_candidates": articles_with_symbols,
            "candidates_rejected_large_cap": rejected_large,
            "candidates_rejected_no_catalyst": rejected_no_catalyst,
            "max_market_cap_millions": MAX_MARKET_CAP_MILLIONS,
            "verification_cache_hits": verification_cache_hits,
            "verification_cache_size": len(verification_cache),
            "candidate_diagnostics": diagnostics,
            "timings": timings,
            "debug": debug,
        },
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }
