import os
import requests
from datetime import datetime, timezone

SEC_BASE='https://data.sec.gov'
UA=os.getenv('SEC_USER_AGENT','TradePilotAI research contact@example.com')

class SEC:
    def __init__(self, user_agent=None):
        self.headers={'User-Agent': user_agent or UA, 'Accept-Encoding':'gzip, deflate'}
        self._tickers=None
    def _get(self, url, timeout=20):
        r=requests.get(url, headers=self.headers, timeout=timeout)
        r.raise_for_status()
        return r.json()
    def ticker_map(self):
        if self._tickers is None:
            data=self._get(f'{SEC_BASE}/files/company_tickers.json')
            self._tickers={str(v['ticker']).upper():str(v['cik_str']).zfill(10) for v in data.values()}
        return self._tickers
    def cik_for(self, symbol):
        return self.ticker_map().get(symbol.upper())
    def submissions(self, symbol):
        cik=self.cik_for(symbol)
        if not cik: return {'available':False,'symbol':symbol,'reason':'Ingen SEC CIK hittades'}
        d=self._get(f'{SEC_BASE}/submissions/CIK{cik}.json')
        recent=d.get('filings',{}).get('recent',{})
        rows=[]
        for i,form in enumerate(recent.get('form',[])):
            if form in ('10-K','10-Q','8-K','20-F','6-K','3','4','5'):
                rows.append({'form':form,'filing_date':recent.get('filingDate',[None])[i], 'accession':recent.get('accessionNumber',[None])[i], 'primary_document':recent.get('primaryDocument',[None])[i]})
            if len(rows)>=20: break
        return {'available':True,'symbol':symbol.upper(),'cik':cik,'company':d.get('name'),'exchange':d.get('exchanges'), 'filings':rows,'source':'SEC EDGAR','retrieved_at':datetime.now(timezone.utc).isoformat()}
