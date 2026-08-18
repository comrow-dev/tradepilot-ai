# TradePilot AI — riktig backendversion

Detta är en riktig backend/frontend-struktur, inte demoaktier.

## 1. Marknadsdata
Backend använder Alpha Vantage. Dokumentationen stöder globala aktiesymboler och intraday-data; realtid kräver rätt data-entitlement/abonnemang. Appen visar därför inte påhittade realtidspriser. https://www.alphavantage.co/documentation/

## 2. AI
Chatboten använder OpenAI Responses API när OPENAI_API_KEY finns. OpenAI:s API faktureras separat från ChatGPT-abonnemanget. https://platform.openai.com/overview

## 3. Starta backend
Python 3.11+
pip install -r backend/requirements.txt
export ALPHAVANTAGE_API_KEY="..."
export OPENAI_API_KEY="..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000

Windows PowerShell:
$env:ALPHAVANTAGE_API_KEY="..."
$env:OPENAI_API_KEY="..."
uvicorn backend.main:app --host 0.0.0.0 --port 8000

## 4. Starta frontend
Öppna frontend/index.html lokalt för enkel testning, eller servera mappen med en HTTPS-webbserver.

## Viktigt för produktionsversionen
- Global IPO/new-listing-feed behöver kopplas till en licensierad IPO-datakälla.
- Realtidsdata behöver rätt börsabonnemang/data-entitlements.
- Lägg till autentisering så att appen verkligen är privat.
- Lägg API-nycklar endast på servern.
- Lägg till pushnotiser.
- Lägg till portfölj och positioner.
- Lägg till paper trading och full trade journal.
- Riktig orderläggning ska vara avstängd tills strategin är backtestad och paper-tradad.
