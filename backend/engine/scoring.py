
def n(v,d=0):
    try:return float(v)
    except:return d

def score_candidate(c):
    t=c.get("technical",{}); f=c.get("fundamentals",{}); m=c.get("market",{}); news=c.get("catalysts",[]); dt=c.get("daytrading",{})
    pts=0; reasons=[]
    change=n(c.get("change_pct")); rvol=n(t.get("rvol20")); rsi=n(t.get("rsi14"),50); ret20=n(t.get("return20_pct")); ret60=n(t.get("return60_pct")); atr=n(t.get("atr14")); price=n(c.get("price"));
    # Momentum 20
    if ret20>8: pts+=10; reasons.append("starkt 20-dagars momentum")
    elif ret20>3: pts+=7; reasons.append("positivt 20-dagars momentum")
    elif ret20>0: pts+=3
    if ret60>10: pts+=5; reasons.append("stark längre trend")
    elif ret60>0: pts+=2
    # Relative volume 15
    if rvol>=4: pts+=15; reasons.append(f"relativ volym {rvol:.1f}x")
    elif rvol>=2: pts+=10; reasons.append(f"relativ volym {rvol:.1f}x")
    elif rvol>=1.2: pts+=5
    # Trend/technical 15
    if t.get("trend")=="BULLISH": pts+=8; reasons.append("bullish trend")
    elif t.get("trend")=="BEARISH": pts-=5; reasons.append("bearish trend")
    if t.get("breakout20"): pts+=7; reasons.append("nära/över 20-dagars breakout")
    if t.get("breakdown20"): pts-=7; reasons.append("nära 20-dagars breakdown")
    # RSI quality 10
    if 50<=rsi<=68: pts+=8; reasons.append("RSI i konstruktivt intervall")
    elif rsi>75: pts-=5; reasons.append("överköpt RSI")
    elif rsi<30: pts-=3; reasons.append("översåld – hög osäkerhet")
    # Market/sector proxy 15
    regime=m.get("regime")
    if regime=="RISK_ON": pts+=8; reasons.append("risk-on marknad")
    elif regime=="RISK_OFF": pts-=8; reasons.append("risk-off marknad")
    sec=n(m.get("sector_strength"));
    if sec>1: pts+=7; reasons.append("stark relativ sektor")
    elif sec<-1: pts-=5; reasons.append("svag relativ sektor")
    # Catalyst 10
    if news: pts+=7; reasons.append(f"{len(news)} färsk(a) nyhets-/katalysatorsignal(er)")
    if any(x.get("catalysts") for x in news): pts+=3
    # Fundamentals 10
    rg=n(f.get("revenue_growth")); roe=n(f.get("roe"))
    if rg>10: pts+=5; reasons.append("omsättningstillväxt")
    if roe>10: pts+=5; reasons.append("positiv ROE")
    # External expert layer: never controls base score; used only as context/confidence.
    expert_signal=dt.get("signal")
    confidence=50
    if expert_signal in ("POSITIV","POSITIV_KONTEXT"): confidence+=5
    elif expert_signal in ("NEGATIV","NEGATIV_KONTEXT"): confidence-=5
    if c.get("data_completeness",0)>=0.8: confidence+=10
    if regime in ("RISK_ON","RISK_OFF"): confidence+=5
    confidence=max(0,min(100,confidence))
    score=max(0,min(100,pts+50))
    risk="LÅG" if n(t.get("atr14")) and price and n(t.get("atr14"))/price<0.02 else "MEDEL"
    if n(t.get("atr14")) and price and n(t.get("atr14"))/price>0.05: risk="HÖG"
    entry=price if price>0 else None
    stop=(price-1.5*atr) if entry and atr else None
    target1=(price+3*atr) if entry and atr else None
    target2=(price+5*atr) if entry and atr else None
    rr=((target1-entry)/(entry-stop)) if entry and stop and target1 and entry>stop else None
    if score>=75 and confidence>=60 and rr and rr>=1.8: signal="KÖPSETUP"
    elif score>=60: signal="ÖVERVÄG"
    elif score<40: signal="AVSTÅ"
    else: signal="AVVAKTA"
    return {"score":round(score,1),"confidence":round(confidence),"signal":signal,"risk":risk,"reasons":reasons,
            "trade_plan":{"action":signal if signal in ("KÖPSETUP","ÖVERVÄG") else "AVVAKTA","entry":round(entry,4) if entry else None,"stop_loss":round(stop,4) if stop else None,"target_1":round(target1,4) if target1 else None,"target_2":round(target2,4) if target2 else None,"risk_reward":round(rr,2) if rr else None,"sell_rule":("Ta delvinst vid mål 1 och följ stop-loss; avbryt setupen om breakout faller tillbaka." if signal in ("KÖPSETUP","ÖVERVÄG") else None)},
            "analysis":{"reasons":reasons,"market_regime":regime,"rvol":rvol,"rsi14":rsi,"atr14":atr}}
