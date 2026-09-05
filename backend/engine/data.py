const API="https://tradepilot-ai-uykw.onrender.com";

const statusEl=document.getElementById("status"),
results=document.getElementById("results"),
summary=document.getElementById("summary"),
charts=document.getElementById("charts");

let latestScan=null;

function esc(v){
  return String(v??"").replace(/[&<>"']/g,c=>({
    "&":"&amp;",
    "<":"&lt;",
    ">":"&gt;",
    '"':"&quot;",
    "'":"&#039;"
  }[c]));
}

function num(v){
  return v==null||Number.isNaN(Number(v))?null:Number(v);
}

function fmt(v,d=2){
  const n=num(v);
  return n==null?"—":n.toFixed(d);
}

async function health(){
  try{
    const r=await fetch(API+"/api/health");
    const x=await r.json();

    statusEl.textContent=x.market_data
      ? `Backend ansluten · ${x.learning?.closed_trades||0} avslutade`
      : "Marknadsdata saknas";
  }catch{
    statusEl.textContent="Backend ej ansluten";
  }
}

function renderSummary(x){
  const a=x.results||[];

  const avg=a.length
    ? a.reduce((s,x)=>s+(num(x.score)||0),0)/a.length
    : 0;

  const buys=a.filter(s=>s.signal==="KÖPSETUP").length;

  summary.innerHTML=
    `<div class="stat"><small>MARKNAD</small><b>${esc(x.market?.regime||"—")}</b></div>`+
    `<div class="stat"><small>KANDIDATER</small><b>${a.length}</b></div>`+
    `<div class="stat"><small>SNITT SCORE</small><b>${avg.toFixed(0)}</b></div>`+
    `<div class="stat"><small>KÖPSETUP</small><b>${buys}</b></div>`;
}

function renderCharts(x){
  const a=(x.results||[]).slice(0,8);

  if(!a.length){
    charts.innerHTML="";
    return;
  }

  const maxRR=Math.max(
    2,
    ...a.map(s=>num(s.trade_plan?.risk_reward)||0)
  );

  const score=a.map(s=>{
    const v=Math.max(
      0,
      Math.min(100,num(s.score)||0)
    );

    return `
      <div class="bar-row">
        <b>${esc(s.symbol)}</b>
        <div class="bar-bg">
          <div class="bar-fill" style="width:${v}%"></div>
        </div>
        <span>${v.toFixed(0)}</span>
      </div>`;
  }).join("");

  const rr=a.map(s=>{
    const v=Math.max(
      0,
      num(s.trade_plan?.risk_reward)||0
    );

    return `
      <div class="bar-row">
        <b>${esc(s.symbol)}</b>
        <div class="bar-bg">
          <div class="bar-fill" style="width:${Math.min(100,v/maxRR*100)}%"></div>
        </div>
        <span>${v.toFixed(1)}</span>
      </div>`;
  }).join("");

  charts.innerHTML=
    `<div class="chart-card">
      <div class="chart-title">Score – bästa kandidater</div>
      <div class="bars">${score}</div>
    </div>`+
    `<div class="chart-card">
      <div class="chart-title">Risk / reward</div>
      <div class="bars">${rr}</div>
    </div>`;
}

function render(x){
  latestScan=x;

  renderSummary(x);
  renderCharts(x);

  if(!x.results?.length){
    results.innerHTML=
      '<div class="empty">Inga kandidater hittades just nu.</div>';
    return;
  }

  const regime=x.market?.regime||"—";

  results.innerHTML=x.results.map(s=>{
    const d=s.daytrading||{},
    t=s.technical||{},
    p=s.trade_plan||{};

    const score=Math.max(
      0,
      Math.min(100,num(s.score)||0)
    );

    return `
      <article class="card">

        <div class="top">
          <div>
            <div class="ticker">${esc(s.symbol)}</div>
            <div class="muted">
              ${esc(s.company_name)} · ${fmt(s.price)}
            </div>
          </div>

          <div class="gain">
            ${fmt(s.change_pct)}%
          </div>
        </div>

        <div class="scoreline">
          <div class="scoreline-head">
            <span>TradePilot score</span>
            <b>${score.toFixed(0)}/100</b>
          </div>

          <div class="scorebg">
            <div class="scorefill"
                 style="width:${score}%"></div>
          </div>
        </div>

        <div class="metrics">

          <div class="metric">
            <small>CONFIDENCE</small>
            ${esc(s.confidence)}%
          </div>

          <div class="metric">
            <small>SIGNAL</small>
            ${esc(s.signal)}
          </div>

          <div class="metric">
            <small>RISK</small>
            ${esc(s.risk)}
          </div>

          <div class="metric">
            <small>RVOL</small>
            ${fmt(t.rvol20,1)}x
          </div>

        </div>

        <div class="metrics">
