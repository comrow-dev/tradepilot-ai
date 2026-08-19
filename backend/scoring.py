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

    # =========================
    # TRADEPILOT SCORE 0-100
    # =========================

    # 1. Momentum: 0-30
    momentum = min(
        30.0,
        max(0.0, change * 2.2)
    )

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
    # Vi vill inte bara jaga aktier
    # som redan rusat väldigt mycket.
    if 5 <= change <= 12:
        early_bonus = 10.0
    elif change <= 18:
        early_bonus = 6.0
    else:
        early_bonus = 2.0

    # 5. Risk
    risk_penalty = 0.0

    if change > 18:
        risk_penalty += min(
            12.0,
            (change - 18) * 1.2
        )

    if volume < 25_000:
        risk_penalty += 10.0

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
        1,
    )

    # =========================
    # SIGNAL
    # =========================

    if score >= 82:
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

    # =========================
    # KÖP / STOP / MÅL
    # =========================

    if price > 0:

        if change <= 12:
            stop_pct = 0.045

        elif change <= 18:
            stop_pct = 0.060

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
                (target1 - price)
                / risk_per_share,
                2
            )
        else:
            risk_reward = None

    else:

        stop = None
        target1 = None
        target2 = None
        risk_reward = None

    # =========================
    # HANDELSBESLUT
    # =========================

    if score >= 82 and price > 0:

        action = "KÖP-KANDIDAT"

    elif score >= 70:

        action = "VÄNTA PÅ BEKRÄFTELSE"

    else:

        action = "AVVAKTA"

    # =========================
    # RESULTAT
    # =========================

    return {
        **stock,

        "score": score,

        "signal": signal,

        "risk": risk,

        "trade_plan": {

            "action": action,

            "entry": price
            if price > 0
            else None,

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
                f"Rörelse +{change:.2f}% "
                f"med volym "
                f"{int(volume):,}."
            ),

            "context": (
                "Score baseras på momentum, "
                "volym, likviditet, tidig "
                "momentum och risk."
            ),

            "bullish_scenario": (
                "Fortsatt uppgång bör "
                "bekräftas av fortsatt "
                "eller ökande volym."
            ),

            "bearish_scenario": (
                f"Under {stop} är "
                "setupen försvagad."
                if stop
                else "Prisdata saknas."
            ),
        },
    }
