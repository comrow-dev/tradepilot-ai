# TradePilot AI 4.0

En komplett Render-klar version med en Command Center-dashboard inspirerad av agentgränssnittet du visade.

## Funktioner
- ATLAS som samordnande AI-agent
- 7 specialistagenter: NOVA, ORION, SPECTRA, HUNTER, VECTOR, SCOUT, CLOSER
- Agentstatus och arbetsbelastning
- ATLAS aktivitets-/uppgiftslogg
- Small-cap scanner via Finnhub
- TradePilot Score 0–100
- Entry, stop-loss, target 1 och risk/reward
- AI-frågor via OpenAI Responses API
- Automatisk scanning var 3:e minut när dashboarden är öppen
- `/` serverar frontend direkt från FastAPI så att Render inte hamnar på `Not Found`
- Render health check på `/api/health`

## Render
Build Command:
`pip install -r backend/requirements.txt`

Start Command:
`uvicorn backend.main:app --host 0.0.0.0 --port $PORT`

Environment:
- `FINNHUB_API_KEY` = din Finnhub-nyckel
- `OPENAI_API_KEY` = valfri OpenAI-nyckel
- `OPENAI_MODEL` = valfri modell, standard `gpt-5-mini`

## Viktigt
Detta är ett analysverktyg, inte personlig investeringsrådgivning. Score och trade-plan är heuristiska signaler och ska verifieras mot aktuell marknadsdata.
