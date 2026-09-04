import os, sqlite3, json
from datetime import datetime, timezone
DB=os.getenv('TRADEPILOT_DB','tradepilot.db')

def connect():
    c=sqlite3.connect(DB)
    c.execute('''CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY AUTOINCREMENT,symbol TEXT,detected_at TEXT,entry REAL,stop REAL,target REAL,score REAL,confidence REAL,signal TEXT,outcome TEXT,exit_price REAL,pnl_pct REAL,metadata TEXT)''')
    c.commit(); return c

def record_signal(c):
    with connect() as db:
        cur=db.execute('INSERT INTO signals(symbol,detected_at,entry,stop,target,score,confidence,signal,metadata) VALUES(?,?,?,?,?,?,?,?,?)',(c.get('symbol'),c.get('detected_at',datetime.now(timezone.utc).isoformat()),c.get('trade_plan',{}).get('entry'),c.get('trade_plan',{}).get('stop_loss'),c.get('trade_plan',{}).get('target_1'),c.get('score'),c.get('confidence'),c.get('signal'),json.dumps(c,default=str)))
        return cur.lastrowid

def close_signal(signal_id, outcome, exit_price, pnl_pct):
    if outcome not in ('WIN','LOSS','FLAT'): raise ValueError('Ogiltigt outcome')
    with connect() as db: db.execute('UPDATE signals SET outcome=?,exit_price=?,pnl_pct=? WHERE id=?',(outcome,float(exit_price),float(pnl_pct),int(signal_id)))
    return {'id':signal_id,'outcome':outcome,'exit_price':exit_price,'pnl_pct':pnl_pct}

def summary():
    with connect() as db:
        total,wins,avg,avg_score=db.execute("SELECT COUNT(*),SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END),AVG(pnl_pct),AVG(score) FROM signals WHERE outcome IS NOT NULL").fetchone()
        open_count=db.execute("SELECT COUNT(*) FROM signals WHERE outcome IS NULL").fetchone()[0]
        return {'closed_trades':total or 0,'open_signals':open_count or 0,'wins':wins or 0,'win_rate':round(wins/total*100,1) if total else None,'avg_pnl_pct':round(avg,3) if avg is not None else None,'avg_score':round(avg_score,1) if avg_score is not None else None}
