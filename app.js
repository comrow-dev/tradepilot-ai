const API =
  localStorage.getItem("tradepilot_api") ||
  `${location.protocol}//${location.hostname.replace(/\.github\.dev$/, "-8000.app.github.dev")}`;

const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const scanButton = document.getElementById("scan");

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderResults(data) {
  if (!resultsEl) return;

  const results = Array.isArray(data.results) ? data.results : [];

  if (!results.length) {
    resultsEl.innerHTML = "<div>Inga resultat hittades.</div>";
    return;
  }

  resultsEl.innerHTML = results.map(x => {
    const tp = x.trade_plan || {};
    const dt = x.external_sources?.daytrading || {};
    const score = Number(x.score ?? 0);

    return `
      <div class="result-card">
        <h3>
          ${escapeHtml(x.symbol)}
          <span>TradePilot ${escapeHtml(score)}</span>
        </h3>

        <p>
          <strong>Bolag:</strong>
          ${escapeHtml(x.company_name || "Okänt")}
        </p>

        <p>
          <strong>Action:</strong>
          ${escapeHtml(tp.action || x.signal || "AVVAKTA")}
        </p>

        <p><strong>Pris:</strong> ${escapeHtml(x.price)}</p>
        <p><strong>Entry:</strong> ${escapeHtml(tp.entry)}</p>
        <p><strong>Stop-loss:</strong> ${escapeHtml(tp.stop_loss)}</p>
        <p><strong>Target 1:</strong> ${escapeHtml(tp.target_1)}</p>
        <p><strong>Target 2:</strong> ${escapeHtml(tp.target_2)}</p>
        <p><strong>Risk/Reward:</strong> ${escapeHtml(tp.risk_reward)}</p>

        <hr>

        <p>
          <strong>Daytrading.se:</strong>
          ${escapeHtml(dt.signal || "NEUTRAL")}
          ${dt.mentioned ? " – match hittad" : " – ingen match"}
        </p>
      </div>
    `;
  }).join("");
}

async function scan() {
  if (statusEl) {
    statusEl.textContent = "⏳ Skannar marknaden...";
  }

  if (scanButton) {
    scanButton.disabled = true;
  }

  try {
    const response = await fetch(`${API}/api/scan`);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    if (!data.ok) {
      throw new Error(data.error || "Skanningen misslyckades");
    }

    renderResults(data);

    if (statusEl) {
      statusEl.textContent =
        `✅ Klart – ${data.count ?? data.results?.length ?? 0} aktier analyserade`;
    }
  } catch (error) {
    console.error(error);

    if (statusEl) {
      statusEl.textContent = `❌ Fel: ${error.message}`;
    }

    if (resultsEl) {
      resultsEl.innerHTML =
        `<div class="error">Kunde inte hämta marknadsdata.</div>`;
    }
  } finally {
    if (scanButton) {
      scanButton.disabled = false;
    }
  }
}

if (scanButton) {
  scanButton.addEventListener("click", scan);
}

const form = document.getElementById("form");

if (form) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    await scan();
  });
}

window.scan = scan;
