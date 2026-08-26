from typing import Dict, Any


def analyse_tip(
    tip: Dict[str, Any],
    market: Dict[str, Any] | None = None
) -> Dict[str, Any]:

    market = market or {}

    score = 50
    reasons_for = []
    reasons_against = []

    symbol = tip.get("symbol", "")
    source = tip.get("source", "Okänd källa")
    author = tip.get("author", "Okänd")
    tip_text = tip.get("tip_text", "")

    # 1. Källa
    if source and source != "Okänd källa":
        reasons_for.append(f"Tipset kommer från {source}.")
        score += 5
    else:
        reasons_against.append("Källan är okänd.")
        score -= 5

    # 2. Marknadsdata
    price = market.get("price")
    change = market.get("change_pct")
    volume = market.get("volume")

    if change is not None:
        if change > 3:
            score += 10
            reasons_for.append("Aktien visar stark positiv momentum.")
        elif change < -3:
            score -= 10
            reasons_against.append("Aktien visar negativ momentum.")

    if volume is not None:
        if volume >= 1_000_000:
            score += 10
            reasons_for.append("Hög handelsvolym.")
        elif volume < 100_000:
            score -= 5
            reasons_against.append("Relativt låg handelsvolym.")

    # 3. Externt aktietips
    if tip_text:
        reasons_for.append("Det finns ett konkret externt aktietips.")
    else:
        score -= 15
        reasons_against.append("Själva tipset saknas.")

    # 4. Målpris
    target = tip.get("target_price")

    if target is not None and price is not None and price > 0:
        upside = ((float(target) - float(price)) / float(price)) * 100

        if upside >= 20:
            score += 15
            reasons_for.append(
                f"Angivet målpris innebär cirka {upside:.1f}% uppsida."
            )
        elif upside >= 10:
            score += 8
            reasons_for.append(
                f"Angivet målpris innebär cirka {upside:.1f}% uppsida."
            )
        elif upside < 0:
            score -= 15
            reasons_against.append("Målpriset ligger under aktuell kurs.")

    # Begränsa score
    score = max(0, min(100, score))

    # Slutlig bedömning
    if score >= 80:
        verdict = "STARKT TIPS"
    elif score >= 65:
        verdict = "INTRESSANT"
    elif score >= 50:
        verdict = "AVVAKTA"
    else:
        verdict = "SVAGT TIPS"

    return {
        "symbol": symbol,
        "source": source,
        "author": author,
        "score": score,
        "verdict": verdict,
        "reasons_for": reasons_for,
        "reasons_against": reasons_against,
    }


if __name__ == "__main__":

    test_tip = {
        "symbol": "TEST",
        "source": "Metro Finans",
        "author": "Testprofil",
        "tip_text": "Testbolaget kan bli intressant.",
        "target_price": 10.0,
    }

    market = {
        "price": 8.0,
        "change_pct": 4.5,
        "volume": 1500000,
    }

    result = analyse_tip(test_tip, market)

    print(result)
