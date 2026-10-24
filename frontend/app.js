const $ = id => document.getElementById(id);
let busy = false;

function fmt(n, d=2){ return Number(n||0).toFixed(d); }

function agentCard(a){
  const load = Math.min(100, Number(a.load||0)*10);
  return `<div class="agent-card">
    <div class="agent-line">
      <div class="agent-dot">${a.id.slice(0,2)}</div>
      <div><b>${a.id}</b><small>${a.role}</small></div>
      <span class="agent-status">● ${a.status}</span>
    </div>
    <div class="load"><span>Aktuell belastning</span><b>${a.load}/10</b></div>
    <div class="loadbar"><span style="width:${load}%"></span></div>
  </div>`;
}

function opportunity(x){
  const cls = x.change_pct >= 0 ? "up" : "down";
  const chips = (x.reasons||[]).map(r=>`<span class="chip">${r}</span>`).join("");
  const inf = x.influencer || {};
  const infScore = Number(inf.influencer_sentiment_score || 0);
  const infText = inf.mentions
    ? `Influencer/web: ${infScore >= 0 ? "+" : ""}${infScore.toFixed(2)} · ${inf.mentions} omnämnande(n)`
    : "Influencer/web: ingen träff";

  return `<article class="op-card">
    <div class="op-top">
      <div><div class="sym">${x.symbol}</div><div class="name">${x.company_name||x.name||""}</div></div>
      <div class="score">${x.score}<small>/100</small></div>
    </div>
    <div class="price">$${fmt(x.price)} <span class="${cls}">${x.change_pct>=0?"+":""}${fmt(x.change_pct)}%</span></div>
    <div class="chips"><span class="chip">${infText}</span>${chips}</div>
    <div class="plan">
      <div><span>ENTRY</span><b>$${fmt(x.trade_plan.entry)}</b></div>
      <div><span>STOP</span><b>$${fmt(x.trade_plan.stop_loss)}</b></div>
      <div><span>TARGET 1</span><b>$${fmt(x.trade_plan.target_1)}</b></div>
      <div><span>R/R</span><b>${fmt(x.trade_plan.risk_reward)}x</b></div>
    </div>
  </article>`;
}

function activityRow(x){
  const t = new Date(x.time*1000).toLocaleTimeString("sv-SE",{hour:"2-digit",minute:"2-digit"});
  return `<div class="activity-row">
    <div class="activity-top"><b>ATLAS</b><span>→</span><b>${x.agent}</b><span class="badge">${x.status}</span></div>
    <div class="activity-task">${x.task}</div>
    <div class="ticket">${x.id} • ${t}</div>
  </div>`;
}

async function loadAgents(){
  const d = await (await fetch("/api/agents")).json();
  if(d.ok) $("agents").innerHTML = d.agents.map(agentCard).join("");
}

async function loadActivity(){
  const d = await (await fetch("/api/activity")).json();
  if(d.ok) $("activity").innerHTML = d.items.map(activityRow).join("");
}

function scanParams(){
  return new URLSearchParams({
    limit: 25,
    min_price: .5,
    max_price: $("maxPrice").value,
    min_market_cap_m: 2,
    max_market_cap_m: $("maxCap").value,
    min_score: $("minScore").value
  });
}

async function scan(){
  if(busy) return;
  busy = true;
  $("message").textContent = "ATLAS samordnar scan…";
  $("progressBar").style.width = "20%";
  $("progressText").textContent = "20%";
  try{
    const d = await (await fetch("/api/scan?"+scanParams())).json();
    if(!d.ok){
      $("message").innerHTML = `<span class="error">${d.error}</span>`;
      $("results").innerHTML = "";
      $("dataState").textContent = "SAKNAS";
      return;
    }
    const max = d.results.length ? Math.max(...d.results.map(x=>x.score)) : 0;
    $("candidateCount").textContent = d.results.length;
    $("highestScore").textContent = max || "—";
    $("dataState").textContent = "LIVE";
    $("lastScan").textContent = "Senast "+new Date(d.timestamp).toLocaleTimeString("sv-SE",{hour:"2-digit",minute:"2-digit"});
    $("message").textContent = d.results.length ? `${d.results.length} kandidater kvalificerade.` : "Ingen kandidat klarade filtret.";
    $("results").innerHTML = d.results.map(opportunity).join("");
    $("progressBar").style.width = "100%";
    $("progressText").textContent = "100%";
    $("headline").textContent = d.results.length
      ? `ATLAS har prioriterat ${d.results.length} kandidater. Högsta score: ${max}/100.`
      : "Scanner klar. Inga kandidater passerade dagens filter.";
  }catch(e){
    $("message").innerHTML = `<span class="error">Backend-fel: ${e.message}</span>`;
  }finally{
    busy = false;
  }
}

async function health(){
  try{
    const d = await (await fetch("/api/health")).json();
    $("status").textContent = d.market_data ? "LIVE" : "API KEY SAKNAS";
    $("sideStatus").textContent = d.market_data ? "Market data online" : "API key saknas";
    $("dataState").textContent = d.market_data ? "LIVE" : "—";
  }catch(e){
    $("status").textContent = "OFFLINE";
    $("sideStatus").textContent = "Backend offline";
  }
}

$("scanBtn").onclick = scan;
$("refreshBtn").onclick = async()=>{ await loadAgents(); await loadActivity(); await health(); await scan(); };
$("askBtn").onclick = async()=>{
  const q = $("question").value.trim();
  if(!q) return;
  $("answer").textContent = "ATLAS analyserar…";
  try{
    const d = await (await fetch("/api/ask?question="+encodeURIComponent(q),{method:"POST"})).json();
    $("answer").textContent = d.answer || "Inget svar.";
  }catch(e){ $("answer").textContent = "AI-fel: "+e.message; }
};

(async()=>{
  await health();
  await loadAgents();
  await loadActivity();
  await scan();
  setInterval(scan, 180000);
  setInterval(loadActivity, 30000);
})();
