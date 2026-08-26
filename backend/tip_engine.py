from typing import Dict, Any


def analyze_tip(article_data: Dict[str, Any],
                market_data: Dict[str, Any]) -> Dict[str, Any]:

    score = 50
    reasons_for = []
    reasons_against = []

    # -----------------------------------------
    # 1. EXTERN KÄLLA
    # -----------------------------------------

    recommendation = article_data.get("author_recommendation")

    if recommendation == "KÖP":
        score += 15
        reasons_for.append("Källan har en köp-rekommendation.")

    elif recommendation == "SÄLJ":
        score -= 15
        reasons_against.append("Källan har en sälj-rekommendation.")

    elif recommendation == "TECKNA":
        score += 15
        reasons_for.append("Källan rekommenderar att teckna.")

    # -----------------------------------------
    # 2. POSITIVA SIGNALER
    # -----------------------------------------

    signals = article_data.get("signals", [])

    positive_signals = [
        "uppsida",
        "potential",
        "insiderköp",
    ]

    for signal in positive_signals:
        if signal in signals:
            score += 5
            reasons_for.append(
                f"Positiv signal hittad: {signal}."
            )

    # -----------------------------------------
    # 3. NEGATIVA SIGNALER
    # -----------------------------------------

    negative_signals = [
        "vinstvarning",
        "resultatvarning",
        "insidersälj",
    ]

    for signal in negative_signals:
        if signal in signals:
            score -= 10
            reasons_against.append(
                f"Negativ signal hittad: {signal}."
            )

    # -----------------------------------------
    # 4. MARKNADSDATA
    # -----------------------------------------

    change_pct = market_data.get("change_pct")
    volume = market_data.get("volume")
    avg_volume = market_data.get("avg_volume")

    if change_pct is not None:

        if change_pct > 3:
            score += 10
            reasons_for.append(
                "Aktien visar positivt momentum."
            )

        elif change_pct < -3:
            score -= 10
            reasons_against.append(
                "Aktien visar negativt momentum."
            )

    # -----------------------------------------
    # 5. VOLYM
    # -----------------------------------------

    if volume is not None and avg_volume is not None:

        if avg_volume > 0:

            volume_ratio = volume / avg_volume

            if volume_ratio >= 1.5:
                score += 10
                reasons_for.append(
                    "Handelsvolymen är ovanligt hög."
                )

            elif volume_ratio < 0.5:
                score -= 5
                reasons_against.append(
                    "Handelsvolymen är låg."
                )

    # -----------------------------------------
    # 6. FUNDAMENTA
    # -----------------------------------------

    fundamentals = market_data.get("fundamentals", {})

    revenue_growth = fundamentals.get(
        "revenue_growth"
    )

    profitable = fundamentals.get(
        "profitable"
    )

    if revenue_growth is not None:

        if revenue_growth > 10:
            score += 5
            reasons_for.append(
                "Bolaget visar stark omsättningstillväxt."
            )

        elif revenue_growth < 0:
            score -= 5
            reasons_against.append(
                "Omsättningen minskar."
            )

    if profitable is True:
        score += 5
        reasons_for.append(
            "Bolaget är lönsamt."
        )

    elif profitable is False:
        score -= 5
        reasons_against.append(
            "Bolaget är inte lönsamt."
        )

    # -----------------------------------------
    # 7. BEGRÄNSA SCORE
    # -----------------------------------------

    score = max(0, min(100, score))

    # -----------------------------------------
    # 8. SLUTLIG BEDÖMNING
    # -----------------------------------------

    if score >= 80:
        verdict = "STARKT TIPS"

    elif score >= 65:
        verdict = "INTRESSANT"

    elif score >= 50:
        verdict = "AVVAKTA"

    else:
        verdict = "SVAGT TIPS"

    return {
        "score": score,
        "verdict": verdict,
        "reasons_for": reasons_for,
        "reasons_against": reasons_against,
    }


if __name__ == "__main__":

    article = {
        "author_recommendation": None,
        "signals": ["rabatt"]
    }

    market = {
        "change_pct": 4.5,
        "volume": 1500000,
        "avg_volume": 900000,
        "fundamentals": {
            "revenue_growth": 14,
            "profitable": True
        }
    }

    result = analyze_tip(article, market)

    print("\n==============================")
    print("TRADEPILOT AI TIP ENGINE")
    print("==============================")

    print("SCORE:", result["score"])
    print("BEDÖMNING:", result["verdict"])

    print("\nFÖR:")
    for x in result["reasons_for"]:
        print("-", x)

    print("\nEMOT:")
    for x in result["reasons_against"]:
        print("-", x)
