TradePilot AI – Agent Network / Mission Control (säkerhetskontrollerad v2)

Detta kopplar aktivitetsstatus till verkliga steg i befintliga scannerkoden.
Det skapar INTE åtta fristående autonoma LLM-agenter.
Statusminnet är processlokalt och nollställs vid omstart.

INSTALLATION I GITHUB CODESPACES
1. Packa upp ZIP-filen på din dator.
2. Ladda upp agent_runtime.py och apply_agent_network_patch.py till projektets ROTMAPP
   (samma nivå som mapparna backend/ och frontend/).
3. Öppna terminalen i Codespaces och kontrollera att du står i projektets rotmapp.
4. Kör: python apply_agent_network_patch.py
5. Kör: python -m compileall backend
6. Om båda stegen lyckas, granska Source Control och pusha ändringarna.

SÄKERHET
- Skriptet gör en förkontroll av flera viktiga kodankare innan ändringar påbörjas.
- Varje kodersättning kräver exakt en träff.
- Befintliga main.py, pipeline.py, app.js och index.html säkerhetskopieras med suffix
  .before-agent-network.bak innan de skrivs.
- Om skriptet avbryter, forcera inte ändringen. Skicka felmeddelandet.
- Det här är inte en fullständig transaktionell databaslik rollback. Om ett oväntat
  filsystemsfel inträffar mitt under skrivningen kan manuellt återställande från
  säkerhetskopior behövas.

BEGRÄNSNINGAR
- Låsning och status delas bara inom en backend-process. Vid flera Render-workers
  eller instanser behövs delad lagring/låsning, exempelvis Redis eller databas.
- Frontend hämtar status var tredje sekund medan sidan är öppen.
- Patchen ändrar inte aktieuniversum, datakällor eller TradePilot Score.
