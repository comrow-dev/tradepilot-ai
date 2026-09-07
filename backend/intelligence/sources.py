import os
import re
import time
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
import requests

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
USER_AGENT = os.getenv("TRADEPILOT_USER_AGENT", "TradePilot AI/1.0")


def _iso_now():
    return datetime.now(timezone.utc).isoformat()


def _get(url, params=None, timeout=15):
    r = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    r.raise_for_status()
    return r


def _item_id(title, url):
    return hashlib.sha1(
        f"{title}|{url}".encode("utf-8")
    ).hexdigest()[:20]


def gdelt_search(query, maxrecords=25, timespan="24h"):
    try:
        data = _get(
            GDELT_URL,
            {
                "query": query,
                "mode": "artlist",
                "format": "json",
                "maxrecords": maxrecords,
                "timespan": timespan,
                "sort": "HybridRel",
            },
        ).json()
    except Exception as e:
        return [], str(e)

    out = []

    for article in data.get("articles", []) or []:
        title = (article.get("title") or "").strip()
        url = article.get("url") or ""

        if not title or not url:
            continue

        out.append(
            {
                "id": _item_id(title, url),
                "title": title,
                "url": url,
                "source": article.get("domain") or "GDELT",
                "published": article.get("seendate") or _iso_now(),
                "type": "article",
                "query": query,
                "snippet": article.get("title", ""),
            }
        )

    return out, None


def rss_search(feed_url, source_name=None, limit=30):
    try:
        root = ET.fromstring(_get(feed_url).content)
    except Exception as e:
        return [], str(e)

    out = []

    for node in root.findall(".//item")[:limit]:
        title = (node.findtext("title") or "").strip()
        link = (node.findtext("link") or "").strip()
        desc = (node.findtext("description") or "").strip()
        pub = (node.findtext("pubDate") or "").strip()

        if title and link:
            out.append(
                {
                    "id": _item_id(title, link),
                    "title": title,
                    "url": link,
                    "source": source_name or feed_url,
                    "published": pub or _iso_now(),
                    "type": "rss",
                    "snippet": re.sub("<[^>]+>", " ", desc)[:500],
                }
            )

    return out, None


def x_search(query, max_results=25):
    token = os.getenv("X_BEARER_TOKEN", "")

    if not token:
        return [], "X_BEARER_TOKEN saknas"

    try:
        data = _get(
            "https://api.x.com/2/tweets/search/recent",
            {
                "query": query,
                "max_results": max(10, min(max_results, 100)),
                "tweet.fields": (
                    "created_at,author_id,public_metrics,"
                    "entities,context_annotations"
                ),
                "expansions": "author_id",
                "user.fields": (
                    "name,username,verified,public_metrics"
                ),
            },
            timeout=20,
        ).json()
    except Exception as e:
        return [], str(e)

    users = {
        user.get("id"): user
        for user in data.get("includes", {}).get("users", []) or []
    }

    out = []

    for post in data.get("data", []) or []:
        user = users.get(post.get("author_id"), {})
        text = (post.get("text") or "").strip()

        username = user.get("username", "i")
        post_id = post.get("id")

        url = f"https://x.com/{username}/status/{post_id}"

        out.append(
            {
                "id": _item_id(text, url),
                "title": text[:180],
                "url": url,
                "source": "X",
                "published": post.get("created_at") or _iso_now(),
                "type": "social",
                "author": user.get("name") or username,
                "handle": username,
                "metrics": post.get("public_metrics", {}),
                "snippet": text,
            }
        )

    return out, None


def collect_discovery(influencers=None, topics=None):
    influencers = influencers or []

    topics = topics or [
        "small cap stock",
        "turnaround stock",
        "distressed company investment",
        "new contract stock",
        "acquisition rumor stock",
        "biotech catalyst",
        "AI small cap",
        "defense small cap",
        "energy small cap",
        "hidden gem stock",
    ]

    items = []
    errors = []

    # Global news discovery.
    # GDELT is a broad discovery source, not proof of a claim.
    for query in topics[:8]:
        found, error = gdelt_search(
            query,
            maxrecords=20,
            timespan=os.getenv(
                "TRADEPILOT_NEWS_TIMESPAN",
                "24h",
            ),
        )

        items.extend(found)

        if error:
            errors.append(
                {
                    "source": "GDELT",
                    "error": error,
                }
            )

    # Search specifically around configured influencers.
    for person in influencers:
        name = person.get("name", "").strip()
        handle = person.get("handle", "").strip()
        platform = person.get("platform", "").lower()

        if not name and not handle:
            continue

        query = (
            f'"{name or handle}" '
            "stock OR stocks OR shares OR investing"
        )

        if platform == "x":
            if handle:
                query = (
                    f'from:{handle.lstrip("@")} '
                    "(stock OR stocks OR investing OR shares)"
                )

            found, error = x_search(
                query,
                max_results=50,
            )
        else:
            found, error = gdelt_search(
                query,
                maxrecords=25,
                timespan="72h",
            )

        items.extend(found)

        if error:
            errors.append(
                {
                    "source": name or handle,
                    "error": error,
                }
            )

    # Deduplicate.
    unique = {
        item["id"]: item
        for item in items
    }

    return list(unique.values()), errors
