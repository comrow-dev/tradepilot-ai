from math import sqrt


def _f(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def sma(values, n):
    vals = [_f(v) for v in values if _f(v) is not None]
    return sum(vals[-n:]) / n if len(vals) >= n else None


def ema(values, n):
    vals = [_f(v) for v in values if _f(v) is not None]
    if len(vals) < n: return None
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    for x in vals[n:]: e = x * k + e * (1-k)
    return e


def rsi(closes, n=14):
    vals = [_f(v) for v in closes]
    if len(vals) < n + 1: return None
    gains, losses = [], []
    for a,b in zip(vals[-n-1:-1], vals[-n:]):
        d=b-a; gains.append(max(d,0)); losses.append(max(-d,0))
    ag=sum(gains)/n; al=sum(losses)/n
    if al == 0: return 100.0
    return 100 - 100/(1 + ag/al)


def atr(highs, lows, closes, n=14):
    h=list(map(_f, highs)); l=list(map(_f,lows)); c=list(map(_f,closes))
    if len(c) < n+1: return None
    trs=[]
    for i in range(1,len(c)):
        trs.append(max(h[i]-l[i], abs(h[i]-c[i-1]), abs(l[i]-c[i-1])))
    return sum(trs[-n:])/n if len(trs)>=n else None


def macd(closes):
    fast=ema(closes,12); slow=ema(closes,26)
    if fast is None or slow is None: return None
    # Approximate signal from rolling MACD history when enough data exists.
    vals=[_f(v) for v in closes]
    hist=[]
    for i in range(26, len(vals)+1):
        ef=ema(vals[:i],12); es=ema(vals[:i],26)
        if ef is not None and es is not None: hist.append(ef-es)
    signal=ema(hist,9) if len(hist)>=9 else None
    return {"macd":fast-slow,"signal":signal,"histogram":(fast-slow-signal if signal is not None else None)}


def vwap(highs,lows,closes,volumes):
    if not closes or not volumes: return None
    tp=[]; vv=[]
    for h,l,c,v in zip(highs,lows,closes,volumes):
        try: tp.append((float(h)+float(l)+float(c))/3); vv.append(float(v))
        except: pass
    den=sum(vv)
    return sum(a*b for a,b in zip(tp,vv))/den if den else None


def technical_snapshot(candles):
    c=candles or {}
    closes=c.get("c") or []; highs=c.get("h") or []; lows=c.get("l") or []; vols=c.get("v") or []
    if not closes: return {"available":False}
    last=float(closes[-1]); out={"available":True,"last":last}
    for label,n in (("sma20",20),("sma50",50),("sma200",200)):
        out[label]=sma(closes,n)
    out["ema20"]=ema(closes,20); out["rsi14"]=rsi(closes); out["atr14"]=atr(highs,lows,closes); out["macd"]=macd(closes)
    out["vwap"]=vwap(highs[-20:],lows[-20:],closes[-20:],vols[-20:]) if len(vols)>=20 else None
    out["high20"]=max(map(float,highs[-20:])) if len(highs)>=20 else None
    out["low20"]=min(map(float,lows[-20:])) if len(lows)>=20 else None
    out["high52"]=max(map(float,highs[-252:])) if len(highs)>=252 else None
    out["low52"]=min(map(float,lows[-252:])) if len(lows)>=252 else None
    if len(closes)>=21:
        out["return20_pct"]=(last/float(closes[-21])-1)*100
    if len(closes)>=61:
        out["return60_pct"]=(last/float(closes[-61])-1)*100
    avg20=sma(vols,20)
    out["avg_volume20"]=avg20
    out["rvol20"]=(float(vols[-1])/avg20) if avg20 else None
    out["trend"]="BULLISH" if out.get("sma20") and last>out["sma20"] and (not out.get("sma50") or last>out["sma50"]) else "BEARISH" if out.get("sma20") and last<out["sma20"] else "NEUTRAL"
    out["breakout20"]=bool(out.get("high20") and last >= out["high20"]*0.998)
    out["breakdown20"]=bool(out.get("low20") and last <= out["low20"]*1.002)
    out["distance_vwap_pct"]=(last/out["vwap"]-1)*100 if out.get("vwap") else None
    return out
