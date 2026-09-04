from backend.engine.technical import technical_snapshot
from backend.engine.scoring import score_candidate
from backend.engine.costs import apply_round_trip, cost_model, round_trip_cost_pct

def backtest_symbol(fh,symbol,lookback=250):
    candles=fh.candles(symbol,'D',max(lookback+220,500)); closes=candles.get('c') or []; highs=candles.get('h') or []; lows=candles.get('l') or []
    n=len(closes)
    if n<80:return {'symbol':symbol,'error':'Inte tillräckligt med historik'}
    start=max(60,n-lookback); trades=[]
    for i in range(start,n-5):
        window={'c':closes[:i+1],'h':highs[:i+1],'l':lows[:i+1],'v':(candles.get('v') or [])[:i+1]}; price=float(closes[i])
        c={'symbol':symbol,'price':price,'change_pct':(price/float(closes[i-1])-1)*100,'technical':technical_snapshot(window),'fundamentals':{},'market':{'regime':'NEUTRAL','sector_strength':0},'catalysts':[],'daytrading':{},'data_completeness':0.8}
        r=score_candidate(c)
        if r['signal'] not in ('KÖPSETUP','ÖVERVÄG') or not r['trade_plan']['stop_loss']:continue
        entry=price; stop=r['trade_plan']['stop_loss']; target=r['trade_plan']['target_1']; exit_price=None; outcome='OPEN'; exit_i=None
        for j in range(i+1,min(i+6,n)):
            if float(lows[j])<=stop:exit_price=stop;outcome='LOSS';exit_i=j;break
            if float(highs[j])>=target:exit_price=target;outcome='WIN';exit_i=j;break
        if exit_price is None:exit_i=min(i+5,n-1);exit_price=float(closes[exit_i]);outcome='WIN' if exit_price>entry else ('LOSS' if exit_price<entry else 'FLAT')
        pnl=apply_round_trip(entry,exit_price); trades.append({'entry_index':i,'exit_index':exit_i,'entry':round(entry,4),'exit':round(exit_price,4),'gross_pnl_pct':round((exit_price/entry-1)*100,3),'net_pnl_pct':round(pnl,3),'outcome':outcome,'score':r['score']})
    wins=sum(t['outcome']=='WIN' for t in trades); total=len(trades); avg=sum(t['net_pnl_pct'] for t in trades)/total if total else None
    return {'symbol':symbol,'trades':trades,'trade_count':total,'wins':wins,'losses':sum(t['outcome']=='LOSS' for t in trades),'win_rate':round(wins/total*100,1) if total else None,'avg_pnl_pct':round(avg,3) if avg is not None else None,'cost_model':cost_model(),'round_trip_cost_pct':round(round_trip_cost_pct(),3),'note':'Första valideringsmotorn. Kostnader är modellerade, men detta är inte ännu ett bevis på framtida lönsamhet.'}

def walk_forward_symbol(fh,symbol,lookback=750,train_days=400,test_days=100,step=100):
    candles=fh.candles(symbol,'D',max(lookback+80,800)); n=len(candles.get('c') or [])
    if n<train_days+test_days+80:return {'symbol':symbol,'error':'Inte tillräckligt med historik för walk-forward'}
    windows=[]; end=n
    start=max(0,n-lookback)
    while start+train_days+test_days<=end:
        test_start=start+train_days; windows.append({'train_start':start,'train_end':test_start-1,'test_start':test_start,'test_end':min(test_start+test_days-1,end-1)})
        start+=step
    results=[]
    for w in windows:
        # Out-of-sample segment only: scoring parameters are frozen; no tuning on test data.
        seg={k:(v[w['test_start']:w['test_end']+1] if isinstance(v,list) else v) for k,v in candles.items()}
        if len(seg.get('c',[]))<20:continue
        results.append({'window':w,'test_bars':len(seg['c']),'status':'OOS_SEGMENT_READY'})
    return {'symbol':symbol,'windows':results,'method':'rolling train/test windows with frozen parameters','warning':'Träningsdelen används ännu inte för automatisk parameteroptimering; OOS-fönstren är därför en strukturell validering, inte ett optimerat walk-forward-resultat.'}
