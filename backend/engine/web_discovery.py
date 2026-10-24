"""TradePilot public web/news discovery layer."""
from .influencer import discover_influencer_signals

def discover_web_candidates(max_items=100):
    return [
        {"ticker":x["ticker"],"source":x["source"],"title":x["title"],"url":x["url"],
         "author":x.get("author"),"sentiment":x.get("sentiment",0),"timestamp":x.get("timestamp")}
        for x in discover_influencer_signals(max_items)
    ]
