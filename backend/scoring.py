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

    # ==================================
    # TRADEPILOT SCORE V2 — 0-100
    # ==================================

    # 1. Momentum: 0-30
    # Positiv rörelse belönas gradvis.
    # Negativ rörelse ger tydligt avdrag.
    if change <= 0:
        momentum = max(-18.0, change * 1.5)
    else:
        momentum = min(30.0, change * 2.2)

    # 2. Volym: 0-25
    volume_score = min(
        25.0,
        max(
            0.0,
            math.log10(max(volume, 1)) * 2.7
        )
    )

    # 3. Likviditet: 0-20
    if volume >= 1_000_000:
        liquidity = 20.0
    elif volume >= 250_000:
        liquidity = 15.0
    elif volume >= 50_000:
        liquidity = 9.0
    else:
        liquidity = 2.0

    # 4. Tidig momentum
    # Progressiv bonus utan hårda hopp.
    if change <= 5:
        early_bonus = max(0.0, change / 5 * 10.0)

    elif change <= 12:
        early_bonus = 10.0

    elif change <= 18:
        # 10 -> 6 mellan 12% och 18%
        early_bonus = 10.0 - ((change - 12) / 6) * 4.0

    elif change <= 25:
        # 6 -> 2 mellan 18% och 25%
        early_bonus = 6.0 - ((change - 18) / 7) * 4.0

    else:
        early_bonus = 2.0

    # 5. Risk
    risk_penalty = 0.0

    # Kraftig uppgång = ökande risk
    if change > 18:
        risk_penalty += min(
            20.0,
            (change - 18.0) * 1.5
        )

    # Extrem uppgång = ytterligare risk
    if change > 25:
        risk_penalty += min(
            10.0,
            (change - 25.0) * 1.0
        )

    # Låg volym = högre risk
    if volume < 25_000:
        risk_penalty += 10.0

    # Score
    score = round(
        max(
            0.0,
            min(
                100.0,
                15.0
                + momentum
                + volume_score
                + liquidity
                + early_bonus
                - risk_penalty
            )
        ),
        1
    )

    # ==================================
    # SIGNAL
    # ==================================

    if change < 0:
        signal = "AVSTÅ"
        risk = "HÖG"

    elif change > 25:
        signal = "AVSTÅ"
        risk = "HÖG"

    elif score >= 82:
        signal = "KÖP-KANDIDAT"
        risk = "MEDEL"

    elif score >= 70:
        signal = "VÄNTA PÅ BEKRÄFTELSE"
        risk = "MEDEL"

    elif score >= 55:
        signal = "BEVAKA"
        risk = "MEDEL/HÖG"

    else:
        signal = "AVSTÅ"
        risk = "HÖG"

    # ==================================
    # KÖP / STOP / MÅL
    # ==================================

    stop = None
    target1 = None
    target2 = None
    risk_reward = None

    # Trade-plan skapas endast för
    # positiv och köpbar setup.
    if score >= 70 and price > 0 and change > 0 and change <= 25:

        # Progressiv stop-loss
        # Undviker stora hopp vid små förändringar i momentum.
        if change <= 12:
            stop_pct = 0.045

        elif change <= 18:
            # 4.5% -> 6.0% mellan 12% och 18%
            stop_pct = 0.045 + ((change - 12) / 6) * 0.015

        elif change <= 25:
            # 6.0% -> 7.0% mellan 18% och 25%
            stop_pct = 0.060 + ((change - 18) / 7) * 0.010

        else:
            stop_pct = 0.070

        stop = round(
            price * (1 - stop_pct),
            4
        )

        target1 = round(
            price * (1 + stop_pct * 1.8),
            4
        )

        target2 = round(
            price * (1 + stop_pct * 3.0),
            4
        )

        risk_per_share = price - stop

        if risk_per_share > 0:
            risk_reward = round(
                (target1 - price) / risk_per_share,
                2
            )

    # ==================================
    # HANDELSBESLUT
    # ==================================

    if score >= 82 and price > 0 and 0 < change <= 25:
        action = "KÖP-KANDIDAT"

    elif score >= 70 and change > 0:
        action = "VÄNTA PÅ BEKRÄFTELSE"

    else:
        action = "AVVAKTA"

    # ==================================
    # RESULTAT
    # ==================================

    return {
        **stock,

        "score": score,
        "signal": signal,
        "risk": risk,

        "trade_plan": {
            "action": action,
            "entry": price if price > 0 else None,
            "stop_loss": stop,
            "target_1": target1,
            "target_2": target2,
            "risk_reward": risk_reward,
            "sell_rule": (
                "Ta delvinst vid mål 1. "
                "Flytta därefter stop-loss uppåt. "
                "Sälj om stop-loss träffas "
                "eller om momentum bryts."
            ),
        },

        "analysis": {
            "observation": (
                f"Rörelse {change:+.2f}% "
                f"med volym {int(volume):,}."
            ),
            "context": (
                "Score baseras på momentum, "
                "volym, likviditet, tidigt "
                "momentum och risk."
            ),
            "bullish_scenario": (
                "Fortsatt uppgång bör bekräftas "
                "av fortsatt eller ökande volym."
            ),
            "bearish_scenario": (
                f"Under {stop} är setupen försvagad."
                if stop is not None
                else "Prisdata saknas eller setupen är inte köpbar."
            ),
        },
    }
