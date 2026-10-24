"""TradePilot public influencer/social signal discovery."""
from __future__ import annotations
import os, re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
import requests
from xml.etree import ElementTree as ET

DEFAULT_FEEDS = [
    "https://www.reddit.com/r/stocks/.rss",
    "https://www.reddit.com/r/pennystocks/.rss",
    "https://www.reddit.com/r/Daytrading/.rss",
]
TICKER_RE = re.compile(r"(?<![A-Za-z0-9])\$([A-Z]{1,5})(?![A-Za-z0-9])")
BARE_TICKER_RE = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2,5})(?![A-Za-z0-9])")
STOP = {"THE","AND","FOR","ARE","BUT","NOT","YOU","ALL","CAN","HAS","HAD","WAS","THIS","THAT","WITH","FROM","HAVE","WILL","JUST","WHAT","WHEN","WHERE","HOW","WHY","NEW","NEWS","CEO","CFO","IPO","SEC","USA","USD","AI","ETF","EPS","GDP","DD","IMO","YOLO","ATH","ATL","CALL","PUT","NYSE","NASDAQ"}
POSITIVE = {"bullish":1.0,"buy":.8,"breakout":.9,"surge":.9,"strong":.5,"upside":.8,"catalyst":.7,"momentum":.6,"undervalued":.7,"beat":.6,"growth":.5}
NEGATIVE = {"bearish":-1.0,"sell":-.8,"dump":-.9,"offering":-.5,"dilution":-.9,"fraud":-1.0,"warning":-.7,"downside":-.8,"bankrupt":-1.0,"loss":-.5,"scam":-1.0,"rug":-.9}

def _feeds():
    raw = os.getenv("TRADEPILOT_INFLUENCER_FEEDS","").strip()
    return [x.strip() for x in raw.split(",") if x.strip()] if raw else DEFAULT_FEEDS

def _sentiment(text):
    low=text.lower(); score=0
    for w,v in POSITIVE.items():
        if w in low: score += v
    for w,v in NEGATIVE.items():
        if w in low: score += v
    return max(-1.0,min(1.0,score/3.0))

def _tickers(text):
    found={m.group(1) for m in TICKER_RE.finditer(text)}
    for m in BARE_TICKER_RE.finditer(text):
        if m.group(1) not in STOP: found.add(m.group(1))
    return sorted(found)

def _parse_feed(xml, source_url):
    root=ET.fromstring(xml); rows=[]
    for item in root.iter():
        tag=item.tag.lower()
        if not (tag.endswith("item") or tag.endswith("entry")): continue
        title=summary=author=""; link=source_url
        for child in list(item):
            c=child.tag.lower(); text=(child.text or "").strip()
            if c.endswith("title"): title=text
            elif c.endswith(("description","summary","content")): summary=text
            elif c.endswith("link"): link=child.attrib.get("href") or text or link
            elif c.endswith(("author","creator")): author=text
        text=f"{title} {summary}".strip()
        if text: rows.append({"title":title,"text":text,"url":link,"author":author,"source":urlparse(source_url).netloc})
    return rows

def discover_influencer_signals(max_items=100):
    s=requests.Session(); s.headers.update({"User-Agent":"TradePilotAI/1.0 public-feed-reader"})
    out=[]
    for feed in _feeds():
        try:
            r=s.get(feed,timeout=12); r.raise_for_status()
            for item in _parse_feed(r.text,feed):
                sentiment=_sentiment(item["text"])
                for ticker in _tickers(item["text"]):
                    out.append({"ticker":ticker,"sentiment":round(sentiment,3),"source":item["source"],"author":item["author"],"title":item["title"],"url":item["url"],"timestamp":datetime.now(timezone.utc).isoformat()})
                    if len(out)>=max_items: return out
        except Exception:
            continue
    return out

def aggregate_influencer_signals(signals):
    out={}
    for row in signals:
        t=row["ticker"]; b=out.setdefault(t,{"mentions":0,"sentiment_sum":0.0,"sources":set(),"authors":set(),"evidence":[]})
        b["mentions"]+=1; b["sentiment_sum"]+=float(row.get("sentiment",0)); b["sources"].add(row.get("source","unknown"))
        if row.get("author"): b["authors"].add(row["author"])
        if len(b["evidence"])<5: b["evidence"].append({"title":row.get("title"),"url":row.get("url"),"source":row.get("source"),"author":row.get("author"),"sentiment":row.get("sentiment")})
    for t,b in out.items():
        b["sentiment_score"]=round(max(-1,min(1,b["sentiment_sum"]/max(b["mentions"],1))),3)
        b["source_count"]=len(b["sources"]); b["author_count"]=len(b["authors"])
        b["sources"]=sorted(b["sources"]); b["authors"]=sorted(b["authors"]); del b["sentiment_sum"]
    return out
