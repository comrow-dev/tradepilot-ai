const API = localStorage.getItem("tradepilot_api") || "http://localhost:8000";
const statusEl = document.getElementById("status");
const results = document.getElementById("results");

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"
  }[c]));
}

async function health() {
  try {
    const r = await fetch(API + "/api/health");
    const x = await r.json();
    statusEl.textContent = x.market_data ? "Finnhub ansluten" : "Finnhub-nyckel saknas";
  } catch {
    statusEl.textContent = "Backend ej ansluten";
  }
}

async function scan() {
  results.innerHTML = '<div class="empty">Skannar riktiga marknadsdata...</div>';
  try {
    const r = await fetch(API + "/api/scan");
    const x = await r.json();
    if (!r.ok) throw new Error(x.detail || "Scan error");

    if (!x.results?.length) {
      results.innerHTML = '<div class="empty">Inga kandidater hittades just nu.</div>';
      return;
    }

    results.innerHTML = x.results.map(s => {
      const dt = s.daytrading || {};
      return `
      <article class="card">
        <div class="top">
          <div>
            <div class="ticker">${esc(s.symbol)}</div>
            <div class="muted">${esc(s.company_name)} · Pris ${esc(s.price)}</div>
          </div>
          <div class="gain">${Number(s.change_pct).toFixed(2)}%</div>
        </div>
        <div class="metrics">
          <div class="metric"><small>TRADEPILOT SCORE</small>${esc(s.score)}</div>
          <div class="metric"><small>SIGNAL</small>${esc(s.signal)}</div>
          <div class="metric"><small>RISK</small>${esc(s.risk)}</div>
        </div>
        <div class="expert">
          <b>Daytrading.se — extra lager</b>
          <span>Signal: ${esc(dt.signal || "EJ TILLGÄNGLIG")}</span>
          <span>Expert-score: ${esc(dt.expert_score ?? 0)}</span>
          <span>Nämnd: ${dt.mentioned ? "Ja" : "Nej"}</span>
        </div>
      </article>`;
    }).join("");
  } catch (e) {
    results.innerHTML = `<div class="empty">Kunde inte skanna: ${esc(e.message)}</div>`;
  }
}

document.getElementById("scan").onclick = scan;

document.getElementById("form").onsubmit = async e => {
  e.preventDefault();
  const input = document.getElementById("input");
  const text = input.value.trim();
  if (!text) return;

  const box = document.getElementById("messages");
  box.innerHTML += `<div class="msg user">${esc(text)}</div>`;
  input.value = "";

  try {
    const r = await fetch(API + "/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: text})
    });
    const x = await r.json();
    box.innerHTML += `<div class="msg ai">${esc(x.answer)}</div>`;
  } catch {
    box.innerHTML += '<div class="msg ai">Backend är inte ansluten.</div>';
  }
};

health();
