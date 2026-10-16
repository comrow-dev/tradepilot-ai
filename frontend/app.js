const API_BASE = window.location.origin;

const scanButton = document.getElementById("scanButton");
const resultsEl = document.getElementById("results");
const loadingEl = document.getElementById("loading");
const errorEl = document.getElementById("error");

const signalCountEl = document.getElementById("signalCount");
const highestScoreEl = document.getElementById("highestScore");
const scannedCountEl = document.getElementById("scannedCount");
const lastScanEl = document.getElementById("lastScan");

const chatInput = document.getElementById("chatInput");
const chatButton = document.getElementById("chatButton");
const chatMessages = document.getElementById("chatMessages");

let lastScanData = null;

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function setLoading(loading) {
  loadingEl.classList.toggle("hidden", !loading);
  scanButton.disabled = loading;
  scanButton.textContent = loading
    ? "⏳ SCANNAR..."
    : "🔍 SCAN MARKNADEN";
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove("hidden");
}

function clearError() {
  errorEl.textContent = "";
  errorEl.classList.add("hidden");
}

function number(value, decimals = 2) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const n = Number(value);

  if (!Number.isFinite(n)) {
    return "—";
  }

  return n.toLocaleString("sv-SE", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function percent(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const n = Number(value);

  if (!Number.isFinite(n)) {
    return "—";
  }

  return `${n > 0 ? "+" : ""}${number(n, 2)}%`;
}

function scoreClass(score) {
  const n = Number(score);

  if (n >= 80) return "score-high";
  if (n >= 70) return "score-good";
  if (n >= 50) return "score-mid";

  return "score-low";
}

function signalClass(signal) {
  const s = String(signal || "").toUpperCase();

  if (s.includes("KÖP")) {
    return "signal-buy";
  }

  if (
    s.includes("ÖVERVÄG") ||
    s.includes("BEVAKA") ||
    s.includes("AVVAKTA")
  ) {
    return "signal-watch";
  }

  return "signal-sell";
}

function getResults(data) {
  if (Array.isArray(data)) {
    return data;
  }

  if (Array.isArray(data?.results)) {
    return data.results;
  }

  if (Array.isArray(data?.candidates)) {
    return data.candidates;
  }

  if (Array.isArray(data?.data)) {
    return data.data;
  }

  return [];
}

function getSymbol(item) {
  return (
    item.symbol ||
    item.ticker ||
    item.ticker_symbol ||
    "N/A"
  );
}

function getCompany(item) {
  return (
    item.company_name ||
    item.company ||
    item.name ||
    "Okänt bolag"
  );
}

function getTechnical(item) {
  return item.technical || {};
}

function getTradePlan(item) {
  return item.trade_plan || item.tradePlan || {};
}

function getPrice(item) {
  return (
    item.price ??
    item.current_price ??
    item.last_price
  );
}

function getChange(item) {
  return (
    item.change_pct ??
    item.change_percent ??
    item.percent_change ??
    item.change
  );
}

function getVolume(item) {
  return (
    item.volume ??
    item.current_volume ??
    item.avg_volume
  );
}

function getMarketCap(item) {
  const value =
    item.market_cap ??
    item.market_cap_m ??
    item.market_cap_millions;

  if (value === null || value === undefined) {
    return "—";
  }

  const n = Number(value);

  if (!Number.isFinite(n)) {
    return escapeHtml(value);
  }

  if (n < 1000) {
    return `$${number(n, 1)}M`;
  }

  return `$${number(n / 1000, 2)}B`;
}

function getSignal(item) {
  return (
    item.signal ||
    item.action ||
    item.recommendation ||
    "ÖVERVÄG"
  );
}

function getRisk(item) {
  return item.risk || "—";
}

function getConfidence(item) {
  return (
    item.confidence ??
    item.confidence_score
  );
}

function getReasons(item) {
  if (Array.isArray(item.reasons)) {
    return item.reasons;
  }

  if (item.reason) {
    return [item.reason];
  }

  return [];
}

function renderStats(items) {
  const signals = items.filter(item => {
    const signal = String(getSignal(item)).toUpperCase();

    return (
      signal.includes("KÖP") ||
      signal.includes("ÖVERVÄG")
    );
  });

  const scores = items
    .map(item => Number(item.score))
    .filter(Number.isFinite);

  const highest =
    scores.length > 0
      ? Math.max(...scores)
      : null;

  signalCountEl.textContent = signals.length;
  highestScoreEl.textContent =
    highest === null
      ? "—"
      : `${number(highest, 0)}/100`;

  scannedCountEl.textContent = items.length;

  lastScanEl.textContent =
    new Date().toLocaleTimeString("sv-SE", {
      hour: "2-digit",
      minute: "2-digit"
    });
}

function renderResults(data) {
  lastScanData = data;

  const items = getResults(data);

  renderStats(items);

  if (!items.length) {
    resultsEl.innerHTML = `
      <div class="empty">
        <div style="font-size:28px">📡</div>
        <strong>Inga kandidater hittades</strong>
        <p>TradePilot fick inget resultat från scannern.</p>
      </div>
    `;

    return;
  }

  const sorted = [...items].sort(
    (a, b) =>
      Number(b.score ?? 0) -
      Number(a.score ?? 0)
  );

  resultsEl.innerHTML = sorted
    .map((item, index) => {

      const symbol = getSymbol(item);
      const company = getCompany(item);

      const score = Number(
        item.score ?? 0
      );

      const signal = getSignal(item);
      const risk = getRisk(item);
      const confidence = getConfidence(item);

      const price = getPrice(item);
      const change = getChange(item);
      const volume = getVolume(item);

      const technical =
        getTechnical(item);

      const tradePlan =
        getTradePlan(item);

      const rvol =
        technical.rvol20 ??
        technical.relative_volume;

      const rsi =
        technical.rsi14 ??
        technical.rsi;

      const reasons =
        getReasons(item);

      const scoreWidth =
        Math.max(
          0,
          Math.min(100, score)
        );

      return `
        <article class="card">

          <div class="top">

            <div>
              <div class="ticker">
                ${index + 1}. ${escapeHtml(symbol)}
              </div>

              <div class="muted">
                ${escapeHtml(company)}
              </div>
            </div>

            <div style="text-align:right">

              <div class="gain">
                ${percent(change)}
              </div>

              <div class="muted">
                ${escapeHtml(signal)}
              </div>

            </div>

          </div>

          <div class="metrics">

            <div class="metric">
              <small>SCORE</small>
              <b class="${scoreClass(score)}">
                ${number(score, 0)}/100
              </b>
            </div>

            <div class="metric">
              <small>PRIS</small>
              <b>
                ${price == null
                  ? "—"
                  : number(price, 2)}
              </b>
            </div>

            <div class="metric">
              <small>RVOL</small>
              <b>
                ${rvol == null
                  ? "—"
                  : `${number(rvol, 1)}x`}
              </b>
            </div>

            <div class="metric">
              <small>RSI</small>
              <b>
                ${rsi == null
                  ? "—"
                  : number(rsi, 1)}
              </b>
            </div>

          </div>

          <div class="metrics">

            <div class="metric">
              <small>MARKNADSVÄRDE</small>
              <b>
                ${getMarketCap(item)}
              </b>
            </div>

            <div class="metric">
              <small>RISK</small>
              <b>
                ${escapeHtml(risk)}
              </b>
            </div>

            <div class="metric">
              <small>CONFIDENCE</small>
              <b>
                ${confidence == null
                  ? "—"
                  : `${number(confidence, 0)}%`}
              </b>
            </div>

            <div class="metric">
              <small>VOLYM</small>
              <b>
                ${volume == null
                  ? "—"
                  : number(volume, 0)}
              </b>
            </div>

          </div>

          <div class="scoreline">

            <div class="scoreline-head">
              <span>TRADEPILOT SCORE</span>
              <span>${number(score, 0)}/100</span>
            </div>

            <div class="scorebg">
              <div
                class="scorefill"
                style="width:${scoreWidth}%"
              ></div>
            </div>

          </div>

          <div class="expert">

            <b class="${signalClass(signal)}">
              ${escapeHtml(signal)}
            </b>

            <span>
              Risk: ${escapeHtml(risk)}
            </span>

            <span>
              Confidence:
              ${confidence == null
                ? "—"
                : `${number(confidence, 0)}%`}
            </span>

          </div>

          ${
            reasons.length
              ? `
                <div class="reasons">
                  ${reasons
                    .slice(0, 5)
                    .map(
                      reason =>
                        `• ${escapeHtml(reason)}`
                    )
                    .join("<br>")}
                </div>
              `
              : ""
          }

          ${
            tradePlan &&
            (
              tradePlan.entry ||
              tradePlan.stop_loss ||
              tradePlan.target_1 ||
              tradePlan.target_2
            )
              ? `
                <div class="trade-plan">

                  <b>🎯 Trade Plan</b>

                  <div class="metrics">

                    <div class="metric">
                      <small>ENTRY</small>
                      <b>
                        ${tradePlan.entry == null
                          ? "—"
                          : number(tradePlan.entry, 2)}
                      </b>
                    </div>

                    <div class="metric">
                      <small>STOP LOSS</small>
                      <b>
                        ${tradePlan.stop_loss == null
                          ? "—"
                          : number(tradePlan.stop_loss, 2)}
                      </b>
                    </div>

                    <div class="metric">
                      <small>TARGET 1</small>
                      <b>
                        ${tradePlan.target_1 == null
                          ? "—"
                          : number(tradePlan.target_1, 2)}
                      </b>
                    </div>

                    <div class="metric">
                      <small>TARGET 2</small>
                      <b>
                        ${tradePlan.target_2 == null
                          ? "—"
                          : number(tradePlan.target_2, 2)}
                      </b>
                    </div>

                  </div>

                  ${
                    tradePlan.risk_reward
                      ? `<div class="muted">
                          Risk/Reward:
                          ${number(
                            tradePlan.risk_reward,
                            2
                          )}
                        </div>`
                      : ""
                  }

                </div>
              `
              : ""
          }

        </article>
      `;
    })
    .join("");
}

async function scanMarket() {

  setLoading(true);
  clearError();

  try {

    const response =
      await fetch(
        `${API_BASE}/api/scan?limit=25`,
        {
          method: "GET",
          headers: {
            "Accept": "application/json"
          }
        }
      );

    if (!response.ok) {

      let message =
        `HTTP ${response.status}`;

      try {
        const errorData =
          await response.json();

        if (errorData.detail) {
          message =
            errorData.detail;
        }

      } catch (_) {}

      throw new Error(message);
    }

    const data =
      await response.json();

    renderResults(data);

  } catch (error) {

    console.error(error);

    showError(
      `Kunde inte hämta marknadsdata: ${error.message}`
    );

    resultsEl.innerHTML = `
      <div class="empty">
        <strong>Scan misslyckades</strong>
        <p>Kontrollera Render/API och försök igen.</p>
      </div>
    `;

  } finally {

    setLoading(false);
  }
}

async function sendChat() {

  const message =
    chatInput.value.trim();

  if (!message) return;

  chatMessages.innerHTML += `
    <div class="msg user">
      ${escapeHtml(message)}
    </div>
  `;

  chatInput.value = "";

  chatMessages.innerHTML += `
    <div class="msg ai" id="aiThinking">
      Analyserar...
    </div>
  `;

  try {

    const response =
      await fetch(
        `${API_BASE}/api/chat`,
        {
          method: "POST",
          headers: {
            "Content-Type":
              "application/json",
            "Accept":
              "application/json"
          },
          body: JSON.stringify({
            message,
            context: lastScanData
          })
        }
      );

    const data =
      await response.json();

    const thinking =
      document.getElementById(
        "aiThinking"
      );

    if (thinking) {

      thinking.id = "";

      thinking.textContent =
        data.answer ||
        data.detail ||
        "AI:n kunde inte svara.";
    }

  } catch (error) {

    const thinking =
      document.getElementById(
        "aiThinking"
      );

    if (thinking) {

      thinking.id = "";

      thinking.textContent =
        "Kunde inte kontakta TradePilot AI.";
    }
  }
}

scanButton.addEventListener(
  "click",
  scanMarket
);

chatButton.addEventListener(
  "click",
  sendChat
);

chatInput.addEventListener(
  "keydown",
  event => {

    if (
      event.key === "Enter"
    ) {

      event.preventDefault();

      sendChat();
    }
  }
);

scanMarket();

setInterval(
  scanMarket,
  180000
);
