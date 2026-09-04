import os, re, time, requests
from bs4 import BeautifulSoup
SOURCE_URL=os.getenv('DAYTRADING_SOURCE_URL','https://www.daytrading.se/varldensbastaaktier')
_CACHE={'at':0.0,'text':''}

def _page():
    now=time.time()
    if now-_CACHE['at']<600 and _CACHE['text']: return _CACHE['text']
    r=requests.get(SOURCE_URL,timeout=10,headers={'User-Agent':'TradePilot AI/1.0'}); r.raise_for_status()
    text=BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True)
    _CACHE.update(at=now,text=text)
    return text

def get_daytrading_signal(symbol, company_name=''):
    try: text=_page()
    except Exception as e: return {'signal':'EJ_TILLGÄNGLIG','source':SOURCE_URL,'verified':False,'error':str(e)[:160]}
    hay=[x.strip().lower() for x in (symbol,company_name) if x and len(x.strip())>=2]
    low=text.lower(); mentioned=any(re.search(r'(?<![a-z0-9])'+re.escape(x)+r'(?![a-z0-9])',low) for x in hay)
    # This is deliberately conservative: a page mention is not treated as a recommendation.
    if not mentioned: signal='EJ_TRÄFF'
    else:
        pos=len(re.findall(r'\b(köp|köpvärd|köpläge|bäst|stark|positiv|uppsida|potential)\b',low))
        neg=len(re.findall(r'\b(sälj|svag|risk|negativ|undvik)\b',low))
        signal='OMNÄMND'
        if pos>neg and pos-neg>=3: signal='POSITIV_KONTEXT'
        elif neg>pos and neg-pos>=3: signal='NEGATIV_KONTEXT'
    return {'signal':signal,'mentioned':mentioned,'source':SOURCE_URL,'verified':False,'note':'Extern källa. TradePilot verifierar inte att en textpassage är en aktuell rekommendation.'}
