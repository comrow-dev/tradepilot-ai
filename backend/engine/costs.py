import os

def cost_model():
    return {
        'commission_pct': float(os.getenv('TRADEPILOT_COMMISSION_PCT','0.02')),
        'slippage_pct': float(os.getenv('TRADEPILOT_SLIPPAGE_PCT','0.05')),
        'spread_pct': float(os.getenv('TRADEPILOT_SPREAD_PCT','0.05')),
    }

def round_trip_cost_pct():
    c=cost_model(); return 2*c['commission_pct']+2*c['slippage_pct']+c['spread_pct']

def apply_round_trip(entry, exit_price):
    gross=(exit_price/entry-1)*100
    return gross-round_trip_cost_pct()
