import re
from datetime import datetime, timezone

from backend.engine.intelligence import news_catalysts

MAX_MARKET_CAP_MILLIONS = 2000
MAX_DIAGNOSTIC_CANDIDATES = 50

_STOP_SYMBOLS = {
    "A","AI","AM","AN","AS","AT","BE","BY","CAN","CEO","CFO","CO","DO","FOR","FROM","GDP","GO","HAS","IN","IS","IT","ITS","NEWS","NEW","NO","OF","ON","OR","Q1","Q2","Q3","Q4","THE","TO","US","USA","USD","VS","WE","WITH","YOU","UK","EU","UAE","UN","NATO","OPEC","SEC","NASA","ISS","IEA","RBI","IPO","IBM"
}

_COMPANY_SUFFIXES = re.compile(r"\b(incorporated|inc|corp|corporation|company|co|plc|limited|ltd|holdings|holding|group|sa|ag|nv|lp|llc)\b", re.I)

def _normalize_company_name(value):
    text = str(value or "").lower()
    text = _COMPANY_SUFFIXES.sub(" ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())

_SYMBOL_DIRECTORY_CACHE = None

def _stock_symbol_directory(fh):
    global _SYMBOL_DIRECTORY_CACHE
    if _SYMBOL_DIRECTORY_CACHE is not None:
        return _SYMBOL_DIRECTORY_CACHE
    try:
        rows = fh.request("/stock/symbol", {"exchange": "US"}, timeout=20) or []
    except Exception:
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = row.get("symbol") or row.get("displaySymbol")
        name = row.get("description") or row.get("name")
        if not symbol or not name or row.get("type") not in (None, "Common Stock"):
            continue
        normalized = _normalize_company_name(name)
        if len(normalized) >= 5:
            result.append((str(symbol).upper(), normalized, str(name)))
    _SYMBOL_DIRECTORY_CACHE = result
    return result

def _company_name_symbols(item,directory):
    text=_normalize_company_name(" ".join([str(item.get("headline") or ""),str(item.get("summary") or "")]))
    if not text: return []
    out=[]
    for symbol,name,_ in directory:
        if re.search(r"(?<![a-z0-9])"+re.escape(name)+r"(?![a-z0-9])",text): out.append(symbol)
    return out

def _related_symbols(item):
    related=item.get("related")
    if not related: return []
    vals=related if isinstance(related,list) else re.split(r"[,;\s]+",str(related))
    return _clean_symbols(vals)

def _headline_symbols(item):
    text=" ".join([str(item.get("headline") or ""),str(item.get("summary") or "")])
    tokens=re.findall(r"(?<![A-Za-z0-9])\$([A-Z][A-Z0-9.-]{0,5})(?![A-Za-z0-9])",text)
    tokens += re.findall(r"\b(?:NASDAQ|NYSE|AMEX|OTC)(?:\s*:\s*)([A-Z][A-Z0-9.-]{0,5})\b",text)
    return _clean_symbols(tokens)

def _clean_symbols(values):
    out=[]
    for value in values:
        symbol=str(value).strip().upper().lstrip("$")
        if not symbol or symbol in _STOP_SYMBOLS or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,5}",symbol): continue
        if symbol not in out: out.append(symbol)
    return out

def _verify_symbol(fh,symbol):
    try:
        profile=fh.company_profile(symbol)
        if not profile or not profile.get("name"): return False,None,"company_not_found"
        raw_cap=profile.get("marketCapitalization")
        if raw_cap is None: return False,None,"no_market_cap"
        cap=float(raw_cap)
        if cap<=0: return False,cap,"invalid_market_cap"
        if cap>MAX_MARKET_CAP_MILLIONS: return False,cap,"large_cap"
        quote=fh.quote(symbol); price=quote.get("c")
        if price is None or float(price)<=0: return False,cap,"invalid_quote"
        return True,cap,"accepted"
    except (TypeError,ValueError): return False,None,"invalid_profile_data"
    except Exception: return False,None,"verification_error"

def discover_news_candidates(fh,days=2,limit=25):
    raw_news=fh.market_news(days=days)
    # Directory lookup is cached for the lifetime of the Render worker.
    symbol_directory=_stock_symbol_directory(fh)
    discovered=[]; seen=set(); diagnostic_seen=set(); inspected=0; with_symbols=0; rejected_large=0; rejected_catalyst=0; diagnostics=[]
    for item in raw_news or []:
        inspected+=1
        symbols=_related_symbols(item)+_headline_symbols(item)+_company_name_symbols(item,symbol_directory)
        symbols=list(dict.fromkeys(symbols))
        if not symbols: continue
        with_symbols+=1
        analyzed=news_catalysts([item]); article=analyzed[0] if analyzed else {}; score=article.get("catalyst_score",0) or 0
        for symbol in symbols:
            if symbol in diagnostic_seen: continue
            diagnostic_seen.add(symbol)
            if score<=0:
                rejected_catalyst+=1
                if len(diagnostics)<MAX_DIAGNOSTIC_CANDIDATES: diagnostics.append({"symbol":symbol,"status":"rejected","reason":"no_catalyst","market_cap_millions":None,"catalyst_score":0,"headline":item.get("headline")})
                continue
            ok,cap,reason=_verify_symbol(fh,symbol)
            if not ok:
                if reason=="large_cap": rejected_large+=1
                if len(diagnostics)<MAX_DIAGNOSTIC_CANDIDATES: diagnostics.append({"symbol":symbol,"status":"rejected","reason":reason,"market_cap_millions":round(cap,2) if cap is not None else None,"catalyst_score":score,"headline":article.get("headline") or item.get("headline")})
                continue
            if symbol in seen: continue
            seen.add(symbol)
            discovered.append({"symbol":symbol,"market_cap_millions":round(cap,2),"headline":article.get("headline"),"summary":article.get("summary"),"source":article.get("source"),"url":article.get("url"),"datetime":article.get("datetime"),"catalysts":article.get("catalysts",[]),"catalyst_type":article.get("catalyst_type","NONE"),"catalyst_score":score})
            if len(diagnostics)<MAX_DIAGNOSTIC_CANDIDATES: diagnostics.append({"symbol":symbol,"status":"accepted","reason":"accepted","market_cap_millions":round(cap,2),"catalyst_score":score,"headline":article.get("headline")})
            if len(discovered)>=limit: break
        if len(discovered)>=limit: break
    discovered.sort(key=lambda x:(x.get("catalyst_score",0),x.get("datetime") or ""),reverse=True)
    return {"ok":True,"count":len(discovered),"results":discovered[:limit],"diagnostics":{"articles_inspected":inspected,"articles_with_symbol_candidates":with_symbols,"candidates_rejected_large_cap":rejected_large,"candidates_rejected_no_catalyst":rejected_catalyst,"max_market_cap_millions":MAX_MARKET_CAP_MILLIONS,"candidate_diagnostics":diagnostics,"symbol_directory_cached":True},"discovered_at":datetime.now(timezone.utc).isoformat()}
