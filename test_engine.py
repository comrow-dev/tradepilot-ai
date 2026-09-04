from backend.engine.costs import apply_round_trip, round_trip_cost_pct
from backend.engine.scoring import score_candidate

def test_costs_reduce_return():
    assert round_trip_cost_pct() > 0
    assert apply_round_trip(100,110) < 10

def test_no_trade_has_no_sell_rule():
    r=score_candidate({'price':100,'change_pct':0,'technical':{'rvol20':0,'rsi14':50,'return20_pct':0,'return60_pct':0,'atr14':2,'trend':'BEARISH','breakout20':False,'breakdown20':True},'fundamentals':{},'market':{'regime':'RISK_OFF','sector_strength':-2},'catalysts':[],'daytrading':{},'data_completeness':0.2})
    assert r['signal'] in ('AVSTÅ','AVVAKTA')
    assert r['trade_plan']['sell_rule'] is None


def test_score_is_bounded_and_trade_plan_consistent():
    r=score_candidate({'price':100,'change_pct':2,'technical':{'rvol20':2,'rsi14':60,'return20_pct':6,'return60_pct':12,'atr14':2,'trend':'BULLISH','breakout20':True,'breakdown20':False},'fundamentals':{'revenue_growth':12,'roe':15},'market':{'regime':'RISK_ON','sector_strength':2},'catalysts':[{'catalysts':['earnings']}],'daytrading':{'signal':'POSITIV_KONTEXT'},'data_completeness':1})
    assert 0 <= r['score'] <= 100
    assert 0 <= r['confidence'] <= 100
    if r['trade_plan']['stop_loss']:
        assert r['trade_plan']['stop_loss'] < r['trade_plan']['entry']


def test_validation_module_imports():
    from backend.engine.validation import metrics
    assert metrics([])['trade_count'] == 0
