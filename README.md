# TradePilot AI

Uppdaterad version där:
- Finnhub är huvudkälla för marknadsdata.
- TradePilots egen scoring är fortfarande huvudmotorn.
- Daytrading.se är ett separat extra expertlager och kan aldrig ensamt skapa en köp-/säljsignal.
- Saknad data markeras tydligt i stället för att fyllas med påhittade värden.

## Miljövariabler

```bash
FINNHUB_API_KEY=din_nyckel
OPENAI_API_KEY=din_nyckel
OPENAI_MODEL=gpt-5.6-luna
DAYTRADING_SOURCE_URL=https://www.daytrading.se/varldensbastaaktier
```

## Start

```bash
python -m pip install -r backend/requirements.txt
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

## Viktig arkitektur

`Finnhub -> kandidatdata -> TradePilot scoring -> Daytrading.se expertlager -> slutresultat`

Daytrading.se påverkar endast expertfältet. Den ersätter inte TradePilots scoring.

## Kontroll

```bash
python -m py_compile backend/main.py backend/auto_scan.py backend/scoring.py backend/daytrading_source.py
python -c "from backend.auto_scan import scan_market; print('IMPORT OK')"
```
