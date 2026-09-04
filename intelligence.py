from datetime import datetime, timezone
from backend.engine.technical import technical_snapshot

SECTOR_ETFS={
    "Technology":"XLK","Semiconductors":"SOXX","Financials":"XLF","Healthcare":"XLV",
    "Energy":"XLE","Industrials":"XLI","Consumer Discretionary":"XLY","Communication Services":"XLC",
    "Consumer Staples":"XLP","Utilities":"XLU","Real Estate":"XLRE","Materials":"XLB"
}

def pct(a,b):
    try: return (float(a)/float(b)-1)*100
    except: return None

def market_regime(snapshot):
    spy=snapshot.get("SPY",{}); qqq=snapshot.get("QQQ",{}); iw=snapshot.get("IWM",{})
    changes=[x.get("dp") for x in (spy,qqq,iw) if isinstance(x,dict) and x.get("dp") is not None]
    avg=sum(map(float,changes))/len(changes) if changes else 0
    if avg >= 0.6: regime="RISK_ON"
    elif avg <= -0.6: regime="RISK_OFF"
    else: regime="NEUTRAL"
    return {"regime":regime,"breadth_proxy":avg,"index_changes":{k:v.get("dp") for k,v in snapshot.items()}}

def news_catalysts(news):
    items=[]
    for n in news or []:
        title=(n.get("headline") or n.get("title") or "").strip()
        summary=(n.get("summary") or "").strip()
        text=(title+" "+summary).lower()
        tags=[]
        for key,words in {
            "earnings":["earnings","revenue","eps","quarter"],"guidance":["guidance","outlook","forecast"],
            "contract":["contract","order","deal"],"m&a":["acquisition","acquire","merger"],
            "insider":["insider","director bought","insider buying"],"analyst":["upgrade","downgrade","price target"],
            "regulatory":["approval","fda","regulator"],
        }.items():
            if any(w in text for w in words): tags.append(key)
        items.append({"headline":title,"summary":summary[:500],"url":n.get("url"),"datetime":n.get("datetime"),"catalysts":tags})
    return items[:20]

def fundamental_snapshot(metrics,profile):
    m=(metrics or {}).get("metric",metrics or {})
    keys={
        "revenue_growth":"revenueGrowthTTMYoy","eps_growth":"epsGrowthTTMYoy","roe":"roeTTM",
        "roa":"roaTTM","debt_equity":"totalDebtToEquityQuarterly","pe":"peBasicExclExtraTTM",
        "price_sales":"psTTM","beta":"beta","52w_high":"52WeekHigh","52w_low":"52WeekLow"
    }
    out={k:m.get(v) for k,v in keys.items()}
    out["company_name"]=(profile or {}).get("name")
    out["industry"]=(profile or {}).get("finnhubIndustry")
    out["exchange"]=(profile or {}).get("exchange")
    return out
