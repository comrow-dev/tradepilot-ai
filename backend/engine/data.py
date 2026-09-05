import os
import time
import threading
from datetime import datetime, timezone, timedelta

import requests

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
FINNHUB_BASE_URL = "https://finnhub.io/api/v1"

TWELVE_DATA_API_KEY = (
    os.getenv("TWELVE_DATA_API_KEY")
    or os.getenv("TWELVE_API_KEY")
    or os.getenv("TWELVE_DATA_KEY")
    or ""
)
TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"

FINNHUB_MIN_INTERVAL = float(os.getenv("FINNHUB_MIN_INTERVAL", "1.05"))
FINNHUB_CACHE_TTL = float(os.getenv("FINNHUB_CACHE_TTL", "45"))
TWELVE_MIN_INTERVAL = float(os.getenv("TWELVE_MIN_INTERVAL", "1.05"))
TWELVE_CACHE_TTL = float(os.getenv("TWELVE_CACHE_TTL", "120"))

_finnhub_last_request = 0.0
_twelve_last_request = 0.0
_finnhub_lock = threading.Lock()
_twelve_lock = threading.Lock()
_finnhub_cache = {}
_twelve_cache = {}


def _cache_get(cache, key, ttl):
    item = cache.get(key)
    if item and time.monotonic() - item[0] < ttl:
        return item[1]
    return None


class TwelveData:
    def __init__(self, key=None):
        self.key = key or TWELVE_DATA_API_KEY

    def request(self, path="/time_series", params=None, timeout=20):
        if not self.key:
            raise RuntimeError("TWELVE_DATA_API_KEY saknas")

        p = dict(params or {})
        p["apikey"] = self.key
        cache_key = (
            path,
            tuple(sorted((k, str(v)) for k, v in p.items() if k != "apikey")),
        )

        cached = _cache_get(_twelve_cache, cache_key, TWELVE_CACHE_TTL)
        if cached is not None:
            return cached

        global _twelve_last_request
        with _twelve_lock:
            wait = TWELVE_MIN_INTERVAL - (
                time.monotonic() - _twelve_last_request
            )
            if wait > 0:
                time.sleep(wait)

            r = requests.get(
                TWELVE_DATA_BASE_URL + path,
                params=p,
                timeout=timeout,
            )
            _twelve_last_request = time.monotonic()

        r.raise_for_status()
        data = r.json()

        if isinstance(data, dict) and data.get("status") == "error":
            raise RuntimeError(
                data.get("message") or data.get("code") or "Twelve Data error"
            )

        _twelve_cache[cache_key] = (time.monotonic(), data)
        return data

    def candles(self, symbol, resolution="D", days=400):
        interval_map = {
            "D": "1day",
            "60": "1h",
            "15": "15min",
        }
        interval = interval_map.get(resolution)
        if not interval:
            raise ValueError(f"Unsupported Twelve Data resolution: {resolution}")

        if resolution == "D":
            outputsize = min(max(days + 20, 250), 5000)
        elif resolution == "60":
            outputsize = min(max(days * 7 + 100, 500), 5000)
        else:
            outputsize = min(max(days * 26 + 100, 500), 5000)

        data = self.request(
            "/time_series",
            {
                "symbol": symbol,
                "interval": interval,
                "outputsize": outputsize,
                "order": "ASC",
            },
            timeout=25,
        )

        values = data.get("values") if isinstance(data, dict) else None
        if not values:
            raise RuntimeError(f"Inga candles från Twelve Data för {symbol} {interval}")

        # Convert Twelve Data's OHLCV strings to the Finnhub-like structure
        # expected by technical_snapshot().
        out = {
            "s": "ok",
            "t": [],
            "o": [],
            "h": [],
            "l": [],
            "c": [],
            "v": [],
        }

        for row in values:
            try:
                dt = row.get("datetime")
                if dt:
                    try:
                        ts = int(
                            datetime.fromisoformat(
                                dt.replace("Z", "+00:00")
                            ).timestamp()
                        )
                    except ValueError:
                        ts = int(
                            datetime.strptime(
                                dt[:19], "%Y-%m-%d %H:%M:%S"
                            ).replace(tzinfo=timezone.utc).timestamp()
                        )
                else:
                    ts = 0

                out["t"].append(ts)
                out["o"].append(float(row["open"]))
                out["h"].append(float(row["high"]))
                out["l"].append(float(row["low"]))
                out["c"].append(float(row["close"]))
                out["v"].append(float(row.get("volume", 0) or 0))
            except (TypeError, ValueError, KeyError):
                continue

        if not out["c"]:
            raise RuntimeError(f"Ogiltiga candles från Twelve Data för {symbol}")

        return out


class Finnhub:
    def __init__(self, key=None):
        self.key = key or FINNHUB_API_KEY

    def request(self, path, params=None, timeout=15):
        if not self.key:
            raise RuntimeError("FINNHUB_API_KEY saknas")

        p = dict(params or {})
        p["token"] = self.key
        cache_key = (
            path,
            tuple(sorted((k, str(v)) for k, v in p.items() if k != "token")),
        )

        cached = _cache_get(_finnhub_cache, cache_key, FINNHUB_CACHE_TTL)
        if cached is not None:
            return cached

        global _finnhub_last_request
        with _finnhub_lock:
            wait = FINNHUB_MIN_INTERVAL - (
                time.monotonic() - _finnhub_last_request
            )
            if wait > 0:
                time.sleep(wait)

            r = requests.get(
                FINNHUB_BASE_URL + path,
                params=p,
                timeout=timeout,
            )
            _finnhub_last_request = time.monotonic()

        r.raise_for_status()
        data = r.json()

        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError(str(data["error"]))

        _finnhub_cache[cache_key] = (time.monotonic(), data)
        return data

    def symbols(self, exchange="US"):
        return self.request("/stock/symbol", {"exchange": exchange})

    def quote(self, symbol):
        return self.request("/quote", {"symbol": symbol})

    def candles(self, symbol, resolution="D", days=400):
        # Finnhub candle access is not available for this API key/plan.
        # Use Twelve Data for historical OHLCV instead.
        return TwelveData().candles(symbol, resolution, days)

    def company_profile(self, symbol):
        return self.request("/stock/profile2", {"symbol": symbol})

    def metrics(self, symbol):
        return self.request("/stock/metric", {"symbol": symbol, "metric": "all"})

    def recommendation_trends(self, symbol):
        return self.request("/stock/recommendation", {"symbol": symbol})

    def insider_transactions(self, symbol):
        return self.request("/stock/insider-transactions", {"symbol": symbol})

    def company_news(self, symbol, days=7):
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=days)
        return self.request(
            "/company-news",
            {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat()},
            timeout=20,
        )

    def market_news(self, category="general", days=2):
        return self.request("/news", {"category": category}, timeout=20)

    def market_snapshot(self):
        symbols = ["SPY", "QQQ", "IWM"]
        q = {}
        for s in symbols:
            try:
                q[s] = self.quote(s)
            except Exception as e:
                q[s] = {"error": str(e)}
        return q
