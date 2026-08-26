import re


def analyze_article(article):
    text = article.get("text", "")
    title = article.get("title", "")
    lower = text.lower()

    result = {
        "title": title,
        "url": article.get("url"),
        "companies": [],
        "events": [],
        "signals": [],
        "prices": {},
        "author_recommendation": None,
        "confidence": 0
    }

    # ==========================================
    # 1. BOLAG
    # ==========================================

    known_companies = [
        "Latour",
        "Securitas",
        "ASSA ABLOY",
        "Investor",
        "Volvo",
        "Saab",
        "Evolution",
        "Embracer",
        "EQT",
        "Hexagon",
        "Sinch"
    ]

    for company in known_companies:
        if company.lower() in lower:
            result["companies"].append(company)

    # ==========================================
    # 2. HÄNDELSER
    # ==========================================

    event_patterns = {
        "försäljning": [
            "säljer",
            "sälja",
            "försäljning",
            "avyttra",
            "avyttring"
        ],
        "förvärv": [
            "förvärvar",
            "förvärv",
            "köper",
            "köpa"
        ],
        "nyemission": [
            "nyemission",
            "företrädesemission",
            "riktad emission",
            "teckningskurs"
        ],
        "rapport": [
            "delårsrapport",
            "kvartalsrapport",
            "årsrapport"
        ],
        "insiderköp": [
            "insiderköp",
            "insider köper",
            "köpt aktier"
        ],
        "insidersälj": [
            "insidersälj",
            "insider säljer",
            "sålt aktier"
        ]
    }

    for event, words in event_patterns.items():
        if any(word in lower for word in words):
            result["events"].append(event)

    # ==========================================
    # 3. RIKTIG INVESTERINGSREKOMMENDATION
    # ==========================================

    # Vi letar INTE bara efter ordet "sälj".
    # Vi kräver uttryck som faktiskt riktar
    # rekommendationen mot en investering.

    recommendation_patterns = [
        (r"\brekommenderar köp\b", "KÖP"),
        (r"\brekommenderar att köpa\b", "KÖP"),
        (r"\brekommendation.*köp\b", "KÖP"),
        (r"\bköprekommendation\b", "KÖP"),
        (r"\bköpläge\b", "KÖP"),
        (r"\bköpvärd\b", "KÖP"),

        (r"\brekommenderar sälj\b", "SÄLJ"),
        (r"\brekommenderar att sälja\b", "SÄLJ"),
        (r"\bsäljrekommendation\b", "SÄLJ"),
        (r"\bsäljläge\b", "SÄLJ"),

        (r"\brekommenderar avvakta\b", "AVVAKTA"),
        (r"\brekommendation.*avvakta\b", "AVVAKTA"),

        (r"\brekommenderar att teckna\b", "TECKNA"),
        (r"\bteckningsrekommendation\b", "TECKNA"),
        (r"\bteckna aktien\b", "TECKNA")
    ]

    for pattern, recommendation in recommendation_patterns:
        if re.search(pattern, lower):
            result["author_recommendation"] = recommendation
            result["confidence"] = 90
            break

    # ==========================================
    # 4. SIGNALER
    # ==========================================

    signal_words = [
        "riktkurs",
        "uppsida",
        "potential",
        "substansvärde",
        "rabatt",
        "premie",
        "nyemission",
        "företrädesemission",
        "insiderköp",
        "insidersälj",
        "vinstvarning",
        "resultatvarning"
    ]

    for signal in signal_words:
        if signal in lower:
            result["signals"].append(signal)

    # ==========================================
    # 5. PRISER
    # ==========================================

    price_patterns = re.findall(
        r"(Latour|Securitas|ASSA ABLOY)"
        r".{0,100}?"
        r"(\d+[,.]\d+)\s*kr",
        text,
        re.IGNORECASE
    )

    for company, price in price_patterns:
        result["prices"][company.upper()] = float(
            price.replace(",", ".")
        )

    # ==========================================
    # 6. VIKTIG SÄKERHETSKONTROLL
    # ==========================================

    # Om artikeln bara säger att ett bolag säljer
    # ett innehav ska detta INTE klassas som
    # investeringsrekommendation.

    if result["author_recommendation"] is None:
        result["confidence"] = 0

    return result


if __name__ == "__main__":

    from article_reader import read_article

    url = "https://tradevenue.se/@aktiepappa/latour-planerar-att-salja-av-securitas-och-assa-5883"

    article = read_article(url)

    result = analyze_article(article)

    print("\n========================================")
    print("TRADEPILOT ARTICLE ANALYZER")
    print("========================================")

    print("\nTITEL:")
    print(result["title"])

    print("\nBOLAG:")
    print(result["companies"])

    print("\nHÄNDELSER:")
    print(result["events"])

    print("\nFÖRFATTARENS REKOMMENDATION:")
    print(result["author_recommendation"])

    print("\nSIGNALER:")
    print(result["signals"])

    print("\nPRISER:")
    print(result["prices"])

    print("\nCONFIDENCE:")
    print(result["confidence"])
