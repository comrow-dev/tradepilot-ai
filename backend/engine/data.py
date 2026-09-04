import os, time
from datetime import datetime, timezone, timedelta
import requests

API_KEY=os.getenv("FINNHUB_API_KEY","")
BASE_URL="https://finnhub.io/api/v1"

class Finnhub:
    def __init__(self, key=None): self.key=key or API_KEY
    def request(self,path,params=None,timeout=15):
        if not self.key: raise RuntimeError("FINNHUB_API_KEY saknas")
        p=dict(params or {}); p["token"]=self.key
        r=requests.get(BASE_URL+path,params=p,timeout=timeout); r.raise_for_status(); d=r.json()
        if isinstance(d,dict) and d.get("error"): raise RuntimeError(str(d["error"]))
        return d
    def symbols(self, exchange="US"):
        return self.request("/stock/symbol",{"exchange":exchange})
    def quote(self,symbol): return self.request("/quote",{"symbol":symbol})
    def candles(self,symbol,resolution="D",days=400):
        now=int(datetime.now(timezone.utc).timestamp()); frm=now-days*86400
        return self.request("/stock/candle",{"symbol":symbol,"resolution":resolution,"from":frm,"to":now},timeout=20)
    def company_profile(self,symbol): return self.request("/stock/profile2",{"symbol":symbol})
    def metrics(self,symbol): return self.request("/stock/metric",{"symbol":symbol,"metric":"all"})
    def recommendation_trends(self,symbol): return self.request("/stock/recommendation",{"symbol":symbol})
    def insider_transactions(self,symbol): return self.request("/stock/insider-transactions",{"symbol":symbol})
    def company_news(self,symbol,days=7):
        end=datetime.now(timezone.utc).date(); start=end-timedelta(days=days)
        return self.request("/company-news",{"symbol":symbol,"from":start.isoformat(),"to":end.isoformat()},timeout=20)
    def market_news(self,category="general",days=2):
        return self.request("/news",{"category":category},timeout=20)

    def market_snapshot(self):
        symbols=["SPY","QQQ","IWM"]
        q={}
        for s in symbols:
            try: q[s]=self.quote(s)
            except Exception as e: q[s]={"error":str(e)}
        return q
