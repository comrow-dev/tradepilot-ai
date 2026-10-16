def n(v, d=0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def score_candidate(c):
    t = c.get("technical", {})
    f = c.get("fundamentals", {})
    m = c.get("market", {})
    news = c.get("catalysts", [])
    dt = c.get("daytrading", {})

    pts = 0
    reasons = []

    change = n(c.get("change_pct"))
    rvol = n(t.get("rvol20"))
    rsi = n(t.get("rsi14"), 50)
    ret20 = n(t.get("return20_pct"))
    ret60 = n(t.get("return60_pct"))
    atr = n(t.get("atr14"))
    price = n(c.get("price"))

    # Momentum – kort sikt väger tungt för små/micro caps.
    if ret20 > 12:
        pts += 12
        reasons.append("starkt 20-dagars momentum")
    elif ret20 > 8:
        pts += 10
        reasons.append("starkt 20-dagars momentum")
    elif ret20 > 3:
        pts += 7
        reasons.append("positivt 20-dagars momentum")
    elif ret20 > 0:
        pts += 3

    if ret60 > 20:
        pts += 7
        reasons.append("stark längre trend")
    elif ret60 > 10:
        pts += 5
        reasons.append("stark längre trend")
    elif ret60 > 0:
        pts += 2

    # Dagens rörelse – positiv rörelse är bra, men extrem pump får riskpenalty.
    if 2 <= change <= 12:
        pts += 5
        reasons.append(f"positiv dagsrörelse {change:.1f}%")
    elif 0 < change < 2:
        pts += 2
    elif change > 20:
        pts -= 4
        reasons.append("extrem dagsuppgång – ökad retracementrisk")
    elif change < -8:
        pts -= 5
        reasons.append("svag dagsrörelse")

    # Relative volume – en av de viktigaste signalerna för nya småbolagsrörelser.
    if rvol >= 5:
        pts += 15
        reasons.append(f"mycket stark relativ volym {rvol:.1f}x")
    elif rvol >= 3:
        pts += 13
        reasons.append(f"stark relativ volym {rvol:.1f}x")
    elif rvol >= 2:
        pts += 10
        reasons.append(f"relativ volym {rvol:.1f}x")
    elif rvol >= 1.2:
        pts += 5

    # Trend / technical.
    if t.get("trend") == "BULLISH":
        pts += 8
        reasons.append("bullish trend")
    elif t.get("trend") == "BEARISH":
        pts -= 5
        reasons.append("bearish trend")

    if t.get("breakout20"):
        pts += 8
        reasons.append("nära/över 20-dagars breakout")

    if t.get("breakdown20"):
        pts -= 8
        reasons.append("nära 20-dagars breakdown")

    # RSI quality.
    if 50 <= rsi <= 68:
        pts += 8
        reasons.append("RSI i konstruktivt intervall")
    elif 68 < rsi <= 75:
        pts += 3
        reasons.append("RSI stark men börjar bli hög")
    elif rsi > 75:
        pts -= 5
        reasons.append("överköpt RSI")
    elif rsi < 30:
        pts -= 3
        reasons.append("översåld – hög osäkerhet")

    # Market / sector.
    regime = m.get("regime")
    if regime == "RISK_ON":
        pts += 8
        reasons.append("risk-on marknad")
    elif regime == "RISK_OFF":
        pts -= 8
        reasons.append("risk-off marknad")

    sec = n(m.get("sector_strength"))
    if sec > 1:
        pts += 7
        reasons.append("stark relativ sektor")
    elif sec < -1:
        pts -= 5
        reasons.append("svag relativ sektor")

    # Catalyst.
    catalyst_scores = [
        n(x.get("catalyst_score"), 0)
        for x in news
        if isinstance(x, dict)
    ]
    max_catalyst = max(catalyst_scores, default=0)

    # Endast identifierade katalysatorer får påverka score.
    catalyst_items = [
        x for x in news
        if isinstance(x, dict) and n(x.get("catalyst_score"), 0) > 0
    ]

    if catalyst_items:
        pts += 7
        reasons.append(
            f"{len(catalyst_items)} identifierad(e) nyhetskatalysator(er)"
        )

    if any(x.get("catalysts") for x in catalyst_items):
        pts += 3

    catalyst_bonus = min(10, round(max_catalyst / 10))
    if catalyst_bonus > 0:
        pts += catalyst_bonus
        reasons.append(
            f"starkaste nyhetskatalysator {round(max_catalyst)}/100"
        )

    # Fundamentals.
    rg = n(f.get("revenue_growth"))
    roe = n(f.get("roe"))
    if rg > 10:
        pts += 5
        reasons.append("omsättningstillväxt")
    if roe > 10:
        pts += 5
        reasons.append("positiv ROE")

    # External expert/daytrading layer används endast för confidence.
    expert_signal = dt.get("signal")
    confidence = 50

    if expert_signal in ("POSITIV", "POSITIV_KONTEXT"):
        confidence += 5
    elif expert_signal in ("NEGATIV", "NEGATIV_KONTEXT"):
        confidence -= 5

    if c.get("data_completeness", 0) >= 0.8:
        confidence += 10

    if regime in ("RISK_ON", "RISK_OFF"):
        confidence += 5

    if max_catalyst >= 70:
        confidence += 5

    # Extra confidence när flera oberoende signaler pekar åt samma håll.
    positive_confirmations = sum([
        ret20 > 3,
        ret60 > 10,
        rvol >= 2,
        t.get("trend") == "BULLISH",
        bool(t.get("breakout20")),
        50 <= rsi <= 68,
        max_catalyst >= 50,
    ])

    if positive_confirmations >= 5:
        confidence += 8
    elif positive_confirmations >= 4:
        confidence += 5

    confidence = max(0, min(100, confidence))
    score = max(0, min(100, pts + 50))

    # Risk classification.
    risk = (
        "LÅG"
        if atr and price and atr / price < 0.02
        else "MEDEL"
    )

    if atr and price and atr / price > 0.05:
        risk = "HÖG"

    entry = price if price > 0 else None
    stop = (price - 1.5 * atr) if entry and atr else None
    target1 = (price + 3 * atr) if entry and atr else None
    target2 = (price + 5 * atr) if entry and atr else None

    rr = (
        (target1 - entry) / (entry - stop)
        if entry and stop and target1 and entry > stop
        else None
    )

    # KÖPSETUP kräver aktuell positiv volym.
    raw_volume = c.get("volume")
    volume_available = (
        raw_volume is not None and n(raw_volume, -1) > 0
    )

    if risk == "HÖG":
        reasons.append("hög risk – KÖPSETUP spärras")

    if not volume_available:
        reasons.append(
            "aktuell volym saknas eller är ogiltig – KÖPSETUP spärras"
        )

    # KÖPSETUP:
    # 70+ score + tillräcklig confidence + bra R/R + ej hög risk
    # + verifierad aktuell volym.
    if (
        score >= 70
        and confidence >= 60
        and rr
        and rr >= 1.8
        and risk != "HÖG"
        and volume_available
    ):
        signal = "KÖPSETUP"
    elif score >= 70:
        signal = "STARK ÖVERVÄG"
    elif score >= 60:
        signal = "ÖVERVÄG"
    elif score < 40:
        signal = "AVSTÅ"
    else:
        signal = "AVVAKTA"

    return {
        "score": round(score, 1),
        "confidence": round(confidence),
        "signal": signal,
        "risk": risk,
        "reasons": reasons,
        "trade_plan": {
            "action": (
                signal
                if signal in ("KÖPSETUP", "STARK ÖVERVÄG", "ÖVERVÄG")
                else "AVVAKTA"
            ),
            "entry": round(entry, 4) if entry else None,
            "stop_loss": round(stop, 4) if stop else None,
            "target_1": round(target1, 4) if target1 else None,
            "target_2": round(target2, 4) if target2 else None,
            "risk_reward": round(rr, 2) if rr else None,
            "sell_rule": (
                "Ta delvinst vid mål 1 och följ stop-loss; avbryt setupen om breakout faller tillbaka."
                if signal in ("KÖPSETUP", "STARK ÖVERVÄG", "ÖVERVÄG")
                else None
            ),
        },
        "analysis": {
            "reasons": reasons,
            "market_regime": regime,
            "rvol": rvol,
            "rsi14": rsi,
            "atr14": atr,
            "max_catalyst_score": round(max_catalyst),
            "positive_confirmations": positive_confirmations,
        },
    }
