import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from urllib.parse import urljoin

def fetch_source(source):
    url = source["url"]

    headers = {
        "User-Agent": "Mozilla/5.0 (TradePilot AI)"
    }

    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = urljoin(url, a["href"])
        title = a.get_text(" ", strip=True)

        if not title or len(title) < 10:
            continue

        # Ta bort bolagsprofiler
        if "/foretag/" in href:
            continue

        # Ta bort navigering och skräp
        bad_words = [
            "/kontakt",
            "/om-oss",
            "/integritet",
            "/anvandarvillkor",
            "/login",
            "/registrera"
        ]

        if any(x in href.lower() for x in bad_words):
            continue

        # Endast TradeVenue
        if "tradevenue.se" not in href:
            continue

        if href in seen:
            continue

        seen.add(href)

        links.append({
            "title": title,
            "url": href,
            "found_at": datetime.now(timezone.utc).isoformat()
        })

    return {
        "source": source["name"],
        "links": links
    }


if __name__ == "__main__":
    source = {
        "name": "TradeVenue Aktietips",
        "url": "https://tradevenue.se/aktietips",
        "type": "aktietips"
    }

    result = fetch_source(source)

    print("ANTAL:", len(result["links"]))

    for x in result["links"][:30]:
        print(x["title"], "->", x["url"])
