from datetime import datetime, timezone
from backend.engine.technical import technical_snapshot

SECTOR_ETFS={"Technology":"XLK","Semiconductors":"SOXX","Financials":"XLF","Healthcare":"XLV","Energy":"XLE","Industrials":"XLI","Consumer Discretionary":"XLY","Communication Services":"XLC","Consumer Staples":"XLP","Utilities":"XLU","Real Estate":"XLRE","Materials":"XLB"}

def pct(a,b):
    try:return (float(a)/float(b)-1)*100
    except (TypeError,ValueError,ZeroDivisionError):return None

def market_regime(snapshot):
    vals=[x.get("dp") for x in (snapshot.get("SPY",{}),snapshot.get("QQQ",{}),snapshot.get("IWM",{})) if isinstance(x,dict) and x.get("dp") is not None]
    avg=sum(map(float,vals))/len(vals) if vals else 0
    regime="RISK_ON" if avg>=.6 else "RISK_OFF" if avg<=-.6 else "NEUTRAL"
    return {"regime":regime,"breadth_proxy":avg,"index_changes":{k:v.get("dp") for k,v in snapshot.items()}}

_TAGS={
"contract":["contract","order","deal","agreement","awarded"],
"m&a":["acquisition","acquire","merger","merges","takeover"],
"regulatory":["approval","approved","fda","regulator","clearance"],
"clinical":["clinical trial","phase 1","phase 2","phase 3","trial results"],
"guidance":["guidance","outlook","forecast","raises guidance","cuts guidance"],
"earnings":["earnings","revenue","eps","quarter","profit"],
"partnership":["partnership","partnered","collaboration","strategic alliance"],
"financing":["offering","financing","private placement","registered direct"],
"insider":["insider","director bought","insider buying"],
"analyst":["upgrade","downgrade","price target"]}

_WEIGHT={"contract":22,"m&a":25,"regulatory":24,"clinical":24,"guidance":20,"partnership":17,"earnings":14,"financing":8,"insider":8,"analyst":6}

def _dt(v):
    try:
        if isinstance(v,(int,float)): return datetime.fromtimestamp(v,tz=timezone.utc)
        if isinstance(v,str):
            d=datetime.fromisoformat(v.strip().replace("Z","+00:00"))
            return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError,ValueError,OverflowError): pass
    return None

def _score(tags,age,move=None,rvol=None):
    s=sum(_WEIGHT.get(x,0) for x in tags)
    if age is not None: s += 18 if age<=6 else 14 if age<=24 else 8 if age<=72 else 3 if age<=168 else 0
    try:
        a=abs(float(move)); s += 10 if a>=8 else 7 if a>=4 else 4 if a>=2 else 0
    except (TypeError,ValueError): pass
    try:
        r=float(rvol); s += 8 if r>=4 else 5 if r>=2 else 2 if r>=1.2 else 0
    except (TypeError,ValueError): pass
    return max(0,min(100,s))

def news_catalysts(news,price_change_pct=None,rvol=None):
    out=[]; now=datetime.now(timezone.utc)
    for n in news or []:
        title=(n.get("headline") or n.get("title") or "").strip()
        summary=(n.get("summary") or "").strip()
        text=(title+" "+summary).lower()
        tags=[k for k,words in _TAGS.items() if any(w in text for w in words)]
        d=_dt(n.get("datetime"))
        age=max(0,(now-d).total_seconds()/3600) if d else None

        # Färskhet får inte i sig göra en allmän nyhet till en katalysator.
        # Endast identifierade bolagsspecifika katalysatortyper kan få score.
        score=_score(tags,age,price_change_pct,rvol) if tags else 0

        out.append({
            "headline":title,
            "summary":summary[:500],
            "url":n.get("url"),
            "source":n.get("source"),
            "datetime":n.get("datetime"),
            "catalysts":tags,
            "catalyst_type":tags[0] if tags else "NONE",
            "catalyst_score":score,
            "age_hours":round(age,1) if age is not None else None,
        })
    out.sort(key=lambda x:(x["catalyst_score"],-(x["age_hours"] or 999999)),reverse=True)
    return out[:20]

def fundamental_snapshot(metrics,profile):
    m=(metrics or {}).get("metric",metrics or {})
    keys={"revenue_growth":"revenueGrowthTTMYoy","eps_growth":"epsGrowthTTMYoy","roe":"roeTTM","roa":"roaTTM","debt_equity":"totalDebtToEquityQuarterly","pe":"peBasicExclExtraTTM","price_sales":"psTTM","beta":"beta","52w_high":"52WeekHigh","52w_low":"52WeekLow"}
    out={k:m.get(v) for k,v in keys.items()}
    out["company_name"]=(profile or {}).get("name"); out["industry"]=(profile or {}).get("finnhubIndustry"); out["exchange"]=(profile or {}).get("exchange")
    return out
