from statistics import mean
from backend.engine.costs import apply_round_trip
from backend.engine.scoring import score_candidate
from backend.engine.technical import technical_snapshot


def _candidate(symbol, closes, highs, lows, volumes, i):
    price=float(closes[i]); prev=float(closes[i-1])
    window={'c':closes[:i+1],'h':highs[:i+1],'l':lows[:i+1],'v':volumes[:i+1]}
    return {'symbol':symbol,'price':price,'change_pct':(price/prev-1)*100,
            'technical':technical_snapshot(window),'fundamentals':{},
            'market':{'regime':'NEUTRAL','sector_strength':0},'catalysts':[],
            'daytrading':{},'data_completeness':0.8}


def evaluate_segment(symbol, candles, start, end, min_score=60, horizon=5):
    c=candles.get('c') or []; h=candles.get('h') or []; l=candles.get('l') or []; v=candles.get('v') or []
    trades=[]
    end=min(end,len(c)-1)
    # Only score bars in the requested segment. Indicators use data available up to i only.
    for i in range(max(start,60), end):
        r=score_candidate(_candidate(symbol,c,h,l,v,i))
        if r['score'] < min_score or r['signal'] not in ('KÖPSETUP','ÖVERVÄG'): continue
        entry=float(c[i]); stop=r['trade_plan'].get('stop_loss'); target=r['trade_plan'].get('target_1')
        if not stop or not target or stop>=entry: continue
        exit_price=None; outcome='FLAT'; exit_i=min(i+horizon,end)
        for j in range(i+1,min(i+horizon+1,len(c))):
            # Conservative ordering: if both are touched in one bar, assume stop first.
            if float(l[j])<=stop:
                exit_price=stop; exit_i=j; outcome='LOSS'; break
            if float(h[j])>=target:
                exit_price=target; exit_i=j; outcome='WIN'; break
        if exit_price is None:
            exit_price=float(c[exit_i]); outcome='WIN' if exit_price>entry else ('LOSS' if exit_price<entry else 'FLAT')
        net=apply_round_trip(entry,exit_price)
        trades.append({'entry_index':i,'exit_index':exit_i,'entry':entry,'exit':exit_price,'net_pnl_pct':net,'outcome':outcome,'score':r['score']})
    return trades


def metrics(trades):
    n=len(trades); wins=sum(t['outcome']=='WIN' for t in trades); pnls=[t['net_pnl_pct'] for t in trades]
    gross=sum(pnls)
    return {'trade_count':n,'wins':wins,'losses':sum(t['outcome']=='LOSS' for t in trades),'win_rate':round(wins/n*100,1) if n else None,'avg_pnl_pct':round(mean(pnls),3) if pnls else None,'total_pnl_pct':round(gross,3),'profit_factor':round(sum(x for x in pnls if x>0)/abs(sum(x for x in pnls if x<0)),2) if any(x<0 for x in pnls) else None}


def walk_forward(fh,symbol,lookback=900,train_days=400,test_days=100,step=100):
    candles=fh.candles(symbol,'D',max(lookback+80,1000)); n=len(candles.get('c') or [])
    if n < train_days+test_days+80: return {'symbol':symbol,'error':'Inte tillräckligt med historik'}
    start=max(60,n-lookback); windows=[]; i=start
    thresholds=[55,60,65,70]
    while i+train_days+test_days<=n:
        train_start=i; train_end=i+train_days; test_end=train_end+test_days
        train_results={t:metrics(evaluate_segment(symbol,candles,train_start,train_end,min_score=t)) for t in thresholds}
        # Select only from training data. Tie-break toward the higher threshold.
        valid=[(k,v) for k,v in train_results.items() if v['trade_count']>=3 and v['avg_pnl_pct'] is not None]
        chosen=max(valid,key=lambda kv:(kv[1]['total_pnl_pct'],kv[0]))[0] if valid else 60
        test_trades=evaluate_segment(symbol,candles,train_end,test_end,min_score=chosen)
        windows.append({'train':{'start':train_start,'end':train_end-1,'threshold_results':train_results},'selected_min_score':chosen,'test':{'start':train_end,'end':test_end-1,**metrics(test_trades)}})
        i+=step
    all_test=[]
    for w in windows:
        all_test.extend(evaluate_segment(symbol,candles,w['test']['start'],w['test']['end'],w['selected_min_score']))
    return {'symbol':symbol,'method':'rolling walk-forward; threshold selected on train only and frozen on following OOS test','windows':windows,'oos_summary':metrics(all_test),'note':'OOS-resultat använder modellerade kostnader. Ingen parameter väljs från testperioden.'}
