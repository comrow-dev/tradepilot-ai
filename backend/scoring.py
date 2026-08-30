def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def analyze(candidate):
    """TradePilots egen scoring. Daytrading.se ligger utanför denna grundscore."""
    price = _num(candidate.get("price"))
    change = _num(candidate.get("change_pct"))
    volume = candidate.get("volume")

    score = 0.0
    reasons = []

    # Momentum
    if change >= 5:
        score += 4
        reasons.append("starkt momentum")
    elif change > 0:
        score += 2
        reasons.append("positivt momentum")
    elif change < -5:
        score -= 3
        reasons.append("svagt momentum")

    # Likviditet
    if volume is not None:
        vol = _num(volume)
        if vol >= 1_000_000:
            score += 3
            reasons.append("hög likviditet")
        elif vol >= 100_000:
            score += 1
            reasons.append("godtagbar likviditet")
        elif vol > 0:
            score -= 1
            reasons.append("låg likviditet")
    else:
        reasons.append("volym saknas")

    # Enkel konservativ riskbedömning
    risk = "MEDEL"
    if change >= 15:
        risk = "HÖG"
        score -= 1
    elif change <= -8:
        risk = "HÖG"

    signal = "AVVAKTA"
    if score >= 6 and change > 0:
        signal = "ÖVERVÄG"
    elif score <= 0:
        signal = "AVSTÅ"

    entry = price if price > 0 else None
    stop = round(price * 0.96, 4) if price > 0 and signal == "ÖVERVÄG" else None
    target1 = round(price * 1.06, 4) if price > 0 and signal == "ÖVERVÄG" else None
    target2 = round(price * 1.10, 4) if price > 0 and signal == "ÖVERVÄG" else None

    return {
        "score": round(score, 2),
        "signal": signal,
        "risk": risk,
        "trade_plan": {
            "action": "ÖVERVÄG" if signal == "ÖVERVÄG" else "AVVAKTA",
            "entry": entry,
            "stop_loss": stop,
            "target_1": target1,
            "target_2": target2,
            "risk_reward": 1.5 if stop and target1 else None,
            "sell_rule": "Ta delvinst vid mål 1. Flytta därefter stop-loss uppåt. Sälj om stop-loss träffas eller momentum bryts.",
        },
        "analysis": {
            "observation": f"Rörelse {change:.2f}% med volym {volume if volume is not None else 'saknas'}",
            "context": "Score baseras på TradePilots momentum-, volym-, likviditets- och risklogik.",
            "bullish_scenario": "Fortsatt uppgång bör bekräftas av fortsatt styrka och helst ökande volym.",
            "bearish_scenario": "Prisdata, likviditet eller momentum försämras.",
            "reasons": reasons,
        },
    }
