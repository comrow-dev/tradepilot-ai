"""Process-local observability for TradePilot's existing scanner steps."""
from datetime import datetime, timezone
from threading import RLock
from collections import deque

LOCK = RLock()
AGENTS = {
    "ATLAS": "Samordning", "NOVA": "Market Scanner", "ORION": "Momentum",
    "SPECTRA": "News & Catalyst", "HUNTER": "SEC / Filings",
    "VECTOR": "Fundamentals", "SCOUT": "Sentiment", "CLOSER": "Risk Manager",
}
STATE = {k: {"status": "VÄNTAR", "task": "Inväntar nästa scan", "completed": 0, "errors": 0}
         for k in AGENTS}
EVENTS = deque(maxlen=100)
SCAN = {"running": False, "scan_id": 0, "started_at": None, "finished_at": None, "last_error": None}


def _time():
    return datetime.now(timezone.utc).isoformat()


def set_agent(agent, status, task, detail=None):
    if agent not in AGENTS:
        return
    now = datetime.now(timezone.utc).timestamp()
    with LOCK:
        st = STATE[agent]
        st.update({"status": status, "task": task, "updated_at": _time()})
        if status == "KLAR":
            st["completed"] += 1
        elif status == "FEL":
            st["errors"] += 1
        EVENTS.appendleft({"id": f"EV-{SCAN['scan_id']}-{now}", "agent": agent,
                           "task": task, "status": status, "time": now, "detail": detail})


def begin_scan():
    with LOCK:
        if SCAN["running"]:
            return False
        SCAN.update({"running": True, "scan_id": SCAN["scan_id"] + 1,
                     "started_at": _time(), "finished_at": None, "last_error": None})
        for st in STATE.values():
            st.update({"status": "VÄNTAR", "task": "Inväntar arbetssteg"})
    set_agent("ATLAS", "ARBETAR", "Startar och samordnar marknadsscanning")
    return True


def finish_scan(error=None):
    with LOCK:
        SCAN.update({"running": False, "finished_at": _time(),
                     "last_error": str(error) if error else None})
    for key, st in list(STATE.items()):
        if st["status"] == "ARBETAR":
            set_agent(key, "FEL" if error else "KLAR",
                      "Scan avbröts" if error else "Arbetssteg slutfört",
                      str(error) if error else None)
    set_agent("ATLAS", "FEL" if error else "KLAR",
              "Scan misslyckades" if error else "Scan sammanställd",
              str(error) if error else None)


def snapshot():
    with LOCK:
        rows = [{"id": k, "role": v, **dict(STATE[k]),
                 "load": 10 if STATE[k]["status"] == "ARBETAR" else 0}
                for k, v in AGENTS.items()]
        return {"ok": True, "running": SCAN["running"], "scan": dict(SCAN), "agents": rows}


def activity(limit=40):
    with LOCK:
        return {"ok": True, "items": list(EVENTS)[:max(1, min(int(limit), 100))]}
