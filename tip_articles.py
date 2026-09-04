import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

def scan_blog(url):
    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (TradePilot AI)"},
        timeout=20
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    keywords = [
        "köp",
        "sälj",
        "riktkurs",
        "potential",
        "undervärderad",
        "nyemission",
        "teckna",
        "aktie",
        "aktier",
        "bull",
        "bear",
        "köpvärd",
        "köpläge",
        "uppsida"
    ]

    results = []
    seen = set()

    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        href = urljoin(url, a["href"])

        if not title or len(title) < 20:
            continue

        if href in seen:
            continue

        # Bara riktiga inlägg från bloggen
        if "/@aktiepappa/" not in href:
            continue

        # Hoppa över uppenbart irrelevanta sidor
        if any(x in href for x in [
            "/integritet",
            "/kontakt",
            "/login"
        ]):
            continue

        text = title.lower()

        matches = [
            word for word in keywords
            if word in text
        ]

        if matches:
            seen.add(href)

            results.append({
                "title": title,
                "url": href,
                "matches": matches
            })

    return results


if __name__ == "__main__":

    url = "https://tradevenue.se/@aktiepappa"

    results = scan_blog(url)

    print("AKTIETIPS / RELEVANTA ARTIKLAR:", len(results))
    print()

    for item in results:
        print("------------------------------------------------")
        print("TITEL:", item["title"])
        print("MATCH:", ", ".join(item["matches"]))
        print("URL:", item["url"])
