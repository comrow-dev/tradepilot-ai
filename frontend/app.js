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

let lastResults = [];
let scanRunning = false;

function showLoading(show) {
  if (loadingEl) {
    loadingEl.classList.toggle("hidden", !show);
  }

  if (scanButton) {
    scanButton.disabled = show;
    scanButton.textContent = show
      ? "⏳ ANALYSERAR..."
      : "🔍 SCAN MARKNADEN";
  }
}

function showError(message) {
  if (!errorEl) return;

  errorEl.textContent = message || "";
  errorEl.classList.toggle("hidden", !message);
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const n = Number(value);

  if (!Number.isFinite(n)) {
    return String(value);
  }

  return n.toLocaleString("sv-SE", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
}

function getScore(item) {
  const n = Number(item?.score);
  return Number.isFinite(n) ? n : 0;
}

function getTicker(item) {
  return (
    item?.symbol ||
    item?.ticker ||
    item?.ticker_symbol ||
    item?.name ||
    "UNKNOWN"
  );
}

function getName(item) {
  return (
    item?.company_name ||
    item?.company ||
    item?.name ||
    item?.companyName ||
    getTicker(item)
  );
}

function getPrice(item) {
  return (
    item?.price ??
    item?.current_price ??
    item?.currentPrice ??
    item?.close
  );
}

function getChange(item) {
  return (
    item?.change_pct ??
    item?.change_percent ??
    item?.changePercent ??
    item?.percent_change ??
    item?.gain
  );
}

function getVolume(item) {
  return (
    item?.volume ??
    item?.current_volume ??
    item?.avg_volume
  );
}

function getMarketCap(item) {
  return (
    item?.market_cap ??
    item?.market_cap_m ??
    item?.marketCap ??
    item?.market_capitalization
  );
}

function getSignal(item) {
  return item?.signal || "ÖVERVÄG";
}

function getRisk(item) {
  return item?.risk || "—";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function renderResults(items) {
  if (!resultsEl) return;

  if (!Array.isArray(items) || items.length === 0) {
    resultsEl.innerHTML = `
      <div class="empty">
        <div class="empty-icon">📡</div>
        <h3>Inga kandidater hittades</h3>
        <p>
          Scanningen kördes, men inga aktier klarade filtren just nu.
        </p>
      </div>
    `;

    return;
  }

  const sorted = [...items].sort(
    (a, b) => getScore(b) - getScore(a)
  );

  lastResults = sorted;

  resultsEl.innerHTML = sorted
    .map((item, index) => {
      const score = getScore(item);
      const ticker = getTicker(item);
      const name = getName(item);
      const price = getPrice(item);
      const change = getChange(item);
      const volume = getVolume(item);
      const marketCap = getMarketCap(item);
      const signal = getSignal(item);
      const risk = getRisk(item);

      const reasons = Array.isArray(item?.reasons)
        ? item.reasons
        : [];

      const tradePlan = item?.trade_plan || {};

      const entry =
        tradePlan?.entry ??
        tradePlan?.entry_price;

      const stop =
        tradePlan?.stop ??
        tradePlan?.stop_loss;

      const target =
        tradePlan?.target ??
        tradePlan?.take_profit;

      const changeText =
        change === null ||
        change === undefined ||
        change === ""
          ? "—"
          : `${Number(change) >= 0 ? "+" : ""}${formatNumber(change)}%`;

      const reasonHtml = reasons.length
        ? reasons
            .slice(0, 4)
            .map(
              reason =>
                `<span>• ${escapeHtml(reason)}</span>`
            )
            .join("")
        : `<span>• Ingen ytterligare förklaring tillgänglig</span>`;

      return `
        <article class="card opportunity-card">

          <div class="top">

            <div>
              <div class="ticker">
                ${escapeHtml(ticker)}
              </div>

              <div class="muted">
                ${escapeHtml(name)}
              </div>
            </div>

            <div style="text-align:right">

              <div class="gain">
                ${escapeHtml(changeText)}
              </div>

              <div class="muted">
                ${escapeHtml(signal)}
              </div>

            </div>

          </div>

          <div class="metrics">

            <div class="metric">
              <small>PRIS</small>
              ${price == null ? "—" : formatNumber(price)}
            </div>

            <div class="metric">
              <small>VOLUME</small>
              ${volume == null ? "—" : formatNumber(volume, 0)}
            </div>

            <div class="metric">
              <small>MARKET CAP</small>
              ${
                marketCap == null
                  ? "—"
                  : formatNumber(marketCap, 0)
              }
            </div>

            <div class="metric">
              <small>RISK</small>
              ${escapeHtml(risk)}
            </div>

          </div>

          <div class="scoreline">

            <div class="scoreline-head">

              <span>
                TRADEPILOT SCORE
              </span>

              <strong>
                ${formatNumber(score, 0)}/100
              </strong>

            </div>

            <div class="scorebg">

              <div
                class="scorefill"
                style="width:${Math.max(
                  0,
                  Math.min(100, score)
                )}%"
              ></div>

            </div>

          </div>

          <div class="expert">

            <b>
              ${escapeHtml(signal)}
              · Kandidat #${index + 1}
            </b>

            ${reasonHtml}

            ${
              entry != null ||
              stop != null ||
              target != null
                ? `
                  <span>
                    Entry:
                    ${
                      entry == null
                        ? "—"
                        : escapeHtml(
                            formatNumber(entry)
                          )
                    }
                  </span>

                  <span>
                    Stop:
                    ${
                      stop == null
                        ? "—"
                        : escapeHtml(
                            formatNumber(stop)
                          )
                    }
                  </span>

                  <span>
                    Target:
                    ${
                      target == null
                        ? "—"
                        : escapeHtml(
                            formatNumber(target)
                          )
                    }
                  </span>
                `
                : ""
            }

          </div>

        </article>
      `;
    })
    .join("");
}

function updateStats(items, payload) {
  const list = Array.isArray(items)
    ? items
    : [];

  const scores = list
    .map(getScore)
    .filter(Number.isFinite);

  const highest = scores.length
    ? Math.max(...scores)
    : 0;

  const activeSignals = list.filter(item => {
    const signal = String(
      getSignal(item)
    ).toUpperCase();

    return (
      signal !== "AVVAKTA" &&
      signal !== "NEUTRAL"
    );
  }).length;

  if (signalCountEl) {
    signalCountEl.textContent =
      activeSignals;
  }

  if (highestScoreEl) {
    highestScoreEl.textContent =
      highest
        ? `${formatNumber(highest, 0)}/100`
        : "—";
  }

  const scanned =
    payload?.scanned ??
    payload?.scanned_count ??
    payload?.count ??
    list.length;

  if (scannedCountEl) {
    scannedCountEl.textContent =
      formatNumber(scanned, 0);
  }

  if (lastScanEl) {
    lastScanEl.textContent =
      new Date().toLocaleTimeString(
        "sv-SE",
        {
          hour: "2-digit",
          minute: "2-digit"
        }
      );
  }
}

async function scanMarket() {
  if (scanRunning) return;

  scanRunning = true;

  showLoading(true);
  showError("");

  try {
    const response = await fetch(
      `${API_BASE}/api/scan?limit=50`,
      {
        method: "GET",
        headers: {
          "Accept": "application/json"
        },
        cache: "no-store"
      }
    );

    const text =
      await response.text();

    let data;

    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(
        `Servern returnerade ett ogiltigt svar (${response.status}).`
      );
    }

    if (
      !response.ok ||
      data?.ok === false
    ) {
      throw new Error(
        data?.detail ||
        `Scan misslyckades (${response.status}).`
      );
    }

    const items =
      Array.isArray(data?.results)
        ? data.results
        : Array.isArray(data)
          ? data
          : [];

    renderResults(items);
    updateStats(items, data);

  } catch (error) {

    console.error(
      "TradePilot scan error:",
      error
    );

    showError(
      `Kunde inte genomföra scan: ${
        error.message || "okänt fel"
      }`
    );

  } finally {

    scanRunning = false;
    showLoading(false);
  }
}

function addChatMessage(
  text,
  type = "ai"
) {
  if (!chatMessages) return;

  const div =
    document.createElement("div");

  div.className =
    `chat-message ${type}`;

  div.textContent = text;

  chatMessages.appendChild(div);

  chatMessages.scrollTop =
    chatMessages.scrollHeight;
}

async function askAI() {
  const question =
    chatInput?.value?.trim();

  if (!question) return;

  addChatMessage(
    question,
    "user"
  );

  chatInput.value = "";

  if (chatButton) {
    chatButton.disabled = true;
    chatButton.textContent =
      "SKICKAR...";
  }

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
            message: question,
            question,

            context: {
              results: lastResults
            }
          })
        }
      );

    const text =
      await response.text();

    let data;

    try {
      data = JSON.parse(text);
    } catch {
      throw new Error(
        "Ogiltigt svar från AI-servern."
      );
    }

    if (!response.ok) {
      throw new Error(
        data?.detail ||
        `Chat-fel (${response.status}).`
      );
    }

    const answer =
      data?.answer ||
      data?.response ||
      data?.message ||
      data?.text;

    if (!answer) {
      throw new Error(
        "AI-servern skickade inget svar."
      );
    }

    addChatMessage(
      answer,
      "ai"
    );

  } catch (error) {

    console.error(
      "TradePilot chat error:",
      error
    );

    addChatMessage(
      `Jag kunde inte svara just nu. ${
        error.message ||
        "Kontrollera att /api/chat finns i backend."
      }`,
      "ai"
    );

  } finally {

    if (chatButton) {
      chatButton.disabled = false;
      chatButton.textContent =
        "SKICKA";
    }
  }
}

if (scanButton) {
  scanButton.addEventListener(
    "click",
    scanMarket
  );
}

if (chatButton) {
  chatButton.addEventListener(
    "click",
    askAI
  );
}

if (chatInput) {
  chatInput.addEventListener(
    "keydown",
    event => {
      if (event.key === "Enter") {
        event.preventDefault();
        askAI();
      }
    }
  );
}

// Automatisk scanning var 3:e minut.
setInterval(
  () => {
    if (!document.hidden) {
      scanMarket();
    }
  },
  3 * 60 * 1000
);

// Första scan när sidan laddas.
document.addEventListener(
  "DOMContentLoaded",
  () => {
    scanMarket();
  }
);
