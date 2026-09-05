from datetime import datetime, timezone
import os
import time
from backend.engine.data import Finnhub
from backend.engine.technical import technical_snapshot
from backend.engine.intelligence import market_regime, news_catalysts, fundamental_snapshot
from backend.engine.scoring import score_candidate
from backend.engine.learning import record_signal
from backend.daytrading_source import get_daytrading_signal

SECTOR_ETFS={"Technology":"XLK","Financials":"XLF","Healthcare":"XLV","Energy":"XLE","Industrials":"XLI","Consumer Discretionary":"XLY","Communication Services":"XLC","Consumer Staples":"XLP","Utilities":"XLU","Real Estate":"XLRE","Materials":"XLB"}

def market_context(fh):
    snap=fh.market_snapshot(); ctx=market_regime(snap); sectors={}
    for name,etf in SECTOR_ETFS.items():
        try:
            sectors[name]=fh.quote(etf).get("dp"); time.sleep(0.05)
        except Exception: sectors[name]=None
    ctx["sector_changes_pct"]=sectors
    return ctx

def sector_from_profile(profile):
    ind=(profile or {}).get("finnhubIndustry","").lower()
    for sector,keys in {"Technology":["technology","semiconductor","software"],"Financials":["bank","financial","insurance"],"Healthcare":["healthcare","biotech","drug"],"Energy":["oil","gas","energy"],"Industrials":["industrial","machinery","aerospace"],"Consumer Discretionary":["retail","automotive","leisure"],"Communication Services":["media","telecom"],"Consumer Staples":["food","beverage","household"],"Utilities":["utility"],"Real Estate":["real estate","reit"],"Materials":["material","chemical","mining"]}.items():
        if any(k in ind for k in keys): return sector
    return None

def timeframe_data(fh,symbol):
    out={}
    for res,days in (("D",400),("60",60),("15",20)):
        try: out[res]=technical_snapshot(fh.candles(symbol,res,days))
        except Exception: out[res]={"available":False}
    return out

def candidate(fh,item,market):
    s=item.get("symbol"); q=fh.quote(s); price=q.get("c"); prev=q.get("pc")
    if not price or not prev or price<=0:return None
    change=(float(price)-float(prev))/float(prev)*100
    profile=fh.company_profile(s); metrics=fh.metrics(s); fund=fundamental_snapshot(metrics,profile)
    tfs=timeframe_data(fh,s); tech=tfs.get("D",{})
    news=news_catalysts(fh.company_news(s,7))
    try: rec=fh.recommendation_trends(s)[:3]
    except: rec=[]
    try: insider=fh.insider_transactions(s)
    except: insider=[]
    dt=get_daytrading_signal(s,item.get("description"))
    sector=sector_from_profile(profile); sector_change=(market.get("sector_changes_pct") or {}).get(sector)
    m=dict(market); m["sector"]=sector; m["sector_strength"]=float(sector_change) if sector_change is not None else 0
    data_points=[price,prev,tech.get("rsi14"),tech.get("rvol20"),fund.get("revenue_growth"),sector_change]
    c={"symbol":s,"company_name":item.get("description") or profile.get("name") or "","price":price,"change_pct":change,"volume":q.get("v"),"technical":tech,"timeframes":tfs,"fundamentals":fund,"market":m,"catalysts":news,"analyst_trends":rec,"insider":insider,"daytrading":dt,"data_completeness":sum(v is not None for v in data_points)/len(data_points),"detected_at":datetime.now(timezone.utc).isoformat()}
    result=score_candidate(c); result.update({k:c[k] for k in ["symbol","company_name","price","change_pct","volume","technical","timeframes","fundamentals","catalysts","analyst_trends","insider","daytrading","detected_at"]})
    result["market"]=m; result["signal_id"]=record_signal(result)
    return result

def scan_market(limit=25,universe_limit=None):
    if universe_limit is None: universe_limit=int(os.getenv("TRADEPILOT_UNIVERSE_LIMIT","500"))
    universe_limit=min(universe_limit,int(os.getenv("TRADEPILOT_PREFILTER_LIMIT","30")))
    deep_limit=min(max(3,limit),int(os.getenv("TRADEPILOT_DEEP_LIMIT","3")))
    fh=Finnhub(); market=market_context(fh); symbols=fh.symbols("US"); movers=[]
    for item in symbols[:universe_limit]:
        s=item.get("symbol")
        if not s or "." in s or "^" in s: continue
        try:
            q=fh.quote(s); c=q.get("c"); pc=q.get("pc")
            if c and pc and float(c)>1:movers.append((item,(float(c)-float(pc))/float(pc)*100))
        except Exception: continue
        time.sleep(0.12)
    movers=sorted(movers,key=lambda x:x[1],reverse=True)[:deep_limit]
    results=[]
    for item,_ in movers:
        try:
            r=candidate(fh,item,market)
            if r:results.append(r)
        except Exception:continue
        time.sleep(0.15)
    results.sort(key=lambda x:(x.get("score",0),x.get("confidence",0)),reverse=True)
    return {"ok":True,"source":"Finnhub","count":len(results[:limit]),"results":results[:limit],"market":market,"scanned_at":datetime.now(timezone.utc).isoformat(),"universe_considered":len(symbols[:universe_limit]),"prefiltered":len(movers)}
