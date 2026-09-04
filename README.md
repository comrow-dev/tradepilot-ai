# TradePilot AI

TradePilot är en egen trading- och beslutsmotor med målet att hitta mätbar riskjusterad edge.

## Kärna
- Finnhub marknadsdata
- teknisk analys och multi-timeframe
- marknadsregim och sektorstyrka
- fundamenta, nyheter, analytiker- och insiderdata
- Daytrading.se som separat extern informationskälla
- egen 0–100 scoring + confidence
- ATR-baserad risk/reward
- signalhistorik i SQLite
- backtest med modellerad spread, slippage och courtage
- riktig rolling walk-forward/OOS med parametertröskel vald enbart på träningsdelen
- SEC EDGAR-verifiering som separat officiell datakälla
- cachning av Daytrading.se-källan för att minska onödiga upprepade hämtningar
- API för att stänga och följa upp signaler

## Viktig princip
Vi lägger inte till funktioner bara för att de låter bra. En faktor ska kunna mätas mot historiska resultat och helst överleva out-of-sample-testning innan den får större vikt i modellen.

Backtesten är en valideringsmotor, inte ett löfte om framtida avkastning.

## Start
```bash
pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Miljövariabler:
- `FINNHUB_API_KEY`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `DAYTRADING_SOURCE_URL`
- `TRADEPILOT_DB`
- `TRADEPILOT_COMMISSION_PCT` (per sida, standard 0.02%)
- `TRADEPILOT_SLIPPAGE_PCT` (per sida, standard 0.05%)
- `TRADEPILOT_SPREAD_PCT` (round-trip, standard 0.05%)
- `TRADEPILOT_UNIVERSE_LIMIT` (standard 500)
- `SEC_USER_AGENT` (rekommenderas: identifiera app + kontakt vid SEC-anrop)
