import math


def number(value, default=0.0):
    try:
        return float(
            str(value)
            .replace("%", "")
            .replace(",", "")
        )
    except (TypeError, ValueError):
        return default


def analyze(stock):
    change = number(stock.get("change_pct"))
    volume = number(stock.get("volume"))
    price = number(stock.get("price"))

    # 1. Momentum: 0–35
    momentum = min(35, max(0, change * 1.75))

    # 2. Volym: 0–25
    volume_score = min(
        25,
        max(0, math.log10(max(volume, 1)) * 2.5)
    )

    # 3. Likviditet: 0–20
    if volume >= 1_000_000:
        liquidity = 20
    elif volume >= 250_000:
        liquidity = 14
    elif volume >= 50_000:
        liquidity = 8
    else:
        liquidity = 2

    # 4. Risk
    risk_penalty = 0

    if change > 20:
        risk_penalty += min(15, (change - 20) * 1.5)

    if volume < 25_000:
        risk_penalty += 10

    score = round(
        max(
            0,
            min(
                100,
                20 + momentum + volume_score
                + liquidity - risk_penalty
            )
        ),
        1,
    )

    if score >= 75:
        signal = "KÖP-ZON"
        risk = "MEDEL"
    elif score >= 55:
        signal = "AVVAKTA"
        risk = "MEDEL/HÖG"
    else:
        signal = "HÖG RISK"
        risk = "HÖG"

    # En enkel scenario-modell.
    entry = price

    if price > 0:
        stop = round(price * 0.95, 4)
        target1 = round(price * 1.08, 4)
        target2 = round(price * 1.15, 4)
    else:
        stop = target1 = target2 = None

    return {
        **stock,
        "score": score,
        "signal": signal,
        "risk": risk,
        "analysis": {
            "observation": (
                f"Aktien rör sig {change:.2f}% "
                f"med volym {int(volume):,}."
            ),
            "context": (
                "Starkt momentum. Katalysator och nyhetsläge "
                "måste verifieras innan handel."
            ),
            "bullish_scenario": (
                f"Över {entry} med fortsatt volym."
            ),
            "bearish_scenario": (
                f"Under {stop} är setupen försvagad."
            ),
            "entry": entry,
            "stop_loss": stop,
            "target_1": target1,
            "target_2": target2,
            "risk_reward": "cirka 1:1.6",
        },
    }
