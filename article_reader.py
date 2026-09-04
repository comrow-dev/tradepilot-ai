import requests
from bs4 import BeautifulSoup

def read_article(url):
    r = requests.get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (TradePilot AI)"},
        timeout=20
    )
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    # Ta bort sådant som inte är artikelinnehåll
    for tag in soup([
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "aside",
        "form"
    ]):
        tag.decompose()

    # Försök hitta själva artikelområdet
    article = (
        soup.find("article")
        or soup.find("main")
        or soup.find(class_=lambda x: x and "article" in str(x).lower())
    )

    if article:
        text = article.get_text(" ", strip=True)
    else:
        text = soup.get_text(" ", strip=True)

    title = ""

    if soup.find("h1"):
        title = soup.find("h1").get_text(" ", strip=True)
    elif soup.title:
        title = soup.title.get_text(" ", strip=True)

    # Leta efter investeringsrelaterade signaler
    keywords = [
        "köp",
        "köpläge",
        "köpvärd",
        "sälj",
        "säljläge",
        "teckna",
        "teckningskurs",
        "riktkurs",
        "uppsida",
        "potential",
        "undervärderad",
        "övervärderad",
        "avvakta",
        "emission"
    ]

    lower = text.lower()

    matches = [
        word for word in keywords
        if word in lower
    ]

    return {
        "title": title,
        "url": url,
        "matches": matches,
        "text": text
    }


if __name__ == "__main__":

    url = "https://tradevenue.se/@aktiepappa/latour-planerar-att-salja-av-securitas-och-assa-5883"

    print("\n========================================")
    print("TRADEPILOT ARTICLE READER")
    print("========================================")

    try:
        article = read_article(url)

        print("\nTITEL:")
        print(article["title"])

        print("\nSIGNALER:")
        print(", ".join(article["matches"]))

        print("\nARTIKELTEXT:")
        print(article["text"][:8000])

    except Exception as e:
        print("FEL:", e)
