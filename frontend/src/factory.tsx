import React, { useEffect, useMemo, useRef, useState } from "react";
import { BrainCircuit, Crown, FastForward, FlaskConical, Pause, Play, RotateCcw, Shield, Sparkles, Wrench, X } from "lucide-react";
import { API, wsUrl } from "./api";

export type FactoryEvent = {
  id: number; ts: number; type: string; agent_id?: string | null; strategy_id?: string | null;
  payload: Record<string, any>; agent_name?: string; persona?: string; icon?: string; label?: string;
};
type Agent = { id:string; name:string; color:string; role:string; function:string; inputs:string[]; outputs:string[]; status:string; detail:string; brain_status:string; brain_class?:string; capital_permission:string; llm?:{runtime?:string;provider?:string;model?:string;reasoning_effort?:string;available?:boolean;last?:any} };
type FactoryState = {
  ts:number; symbol:string; mode:string; population:number; historical_population:number;
  market:{health:string; price?:number|null; regime:string; benchmark_return_bps:number};
  champion?:{id:string; metrics:any}|null; agents:Agent[]; experiments:any[]; leaderboard:any[]; lessons:any[];
  status_counts:Record<string,number>; execution:any; research:any; evolution?:any; engineer?:any; brain_policy?:any; openbot?:any;
};

const persona: Record<string,{emoji:string; badge:string; title:string; room:string; species:string}> = {
  atlas:{emoji:"🦉",badge:"🧭",title:"Atlas Owl",species:"conductor",room:"Control Tower"},
  curie:{emoji:"🐸",badge:"🧪",title:"Curie Frog",species:"scientist",room:"Idea Lab"},
  evolve:{emoji:"🦎",badge:"🔨",title:"Evolve Chameleon",species:"genome smith",room:"Mutation Forge"},
  forge:{emoji:"🤖",badge:"⚙️",title:"Forge Bot",species:"paper operator",room:"Paper Floor"},
  judge:{emoji:"🦁",badge:"⚖️",title:"Judge Lion",species:"arbiter",room:"Selection Court"},
  mnemosyne:{emoji:"🐙",badge:"📚",title:"Memory Octopus",species:"archivist",room:"Memory Vault"},
  cerberus:{emoji:"🐺",badge:"🛡️",title:"Cerberus Hound",species:"guardian",room:"Risk Gate"},
  hermes:{emoji:"🐦",badge:"📨",title:"Hermes Bird",species:"courier",room:"Execution Dock"},
};

const eventToken: Record<string,string> = {
  hypothesis_created:"📜", mutation_created:"🧬", judge_decision:"🔖", strategy_killed:"💀", champion_promoted:"👑",
  lesson_saved:"📚", epoch_started:"⏱️", epoch_completed:"🏁", paper_activity:"⚙️", risk_gate_blocked:"🛡️", agent_finished:"✨", factory_started:"🏭", epoch_deferred:"⏳", experiment_resolved:"🏆", engineer_task_prepared:"🧑‍💻",
};
const fmt=(n:any,d=1)=>Number.isFinite(Number(n))?Number(n).toFixed(d):"—";
const signed=(n:any,d=1)=>Number.isFinite(Number(n))?`${Number(n)>=0?"+":""}${Number(n).toFixed(d)}`:"—";
const time=(ts:number)=>new Date(ts*1000).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit",second:"2-digit"});

function Character({agent, selected, active, dimmed, onClick}:{agent:Agent;selected:boolean;active:boolean;dimmed:boolean;onClick:()=>void}){
  const p=persona[agent.id]??{emoji:"✨",badge:"⚙️",title:"Factory Sprite",species:"agent",room:"Factory"};
  return <button className={`troll-node character-${agent.id} ${selected?"selected":""} ${active?"active":""} ${dimmed?"dimmed":""}`} style={{"--agent":agent.color} as React.CSSProperties} onClick={onClick}>
    <span className="troll-room">{p.room}</span>
    <span className="troll-avatar"><span className="troll-emoji">{p.emoji}</span><span className="troll-badge">{p.badge}</span><span className="troll-glow" /></span>
    <b>{agent.name}</b><small>{p.title} · {p.species}</small>
    <span className={`troll-status ${agent.status.toLowerCase()}`}>{agent.status}</span>
    <em>{agent.llm?.model??agent.brain_status}</em><span className={`brain-class ${String(agent.brain_class??"").toLowerCase()}`}>{agent.brain_class??agent.brain_status}</span>
  </button>
}

function Conveyor({label, hot=false}:{label:string;hot?:boolean}){return <div className={`factory-conveyor ${hot?"hot":""}`}><span /><span /><span /><small>{label}</small></div>}

const courierRoute=(type?:string)=>{
  if(type==="hypothesis_created") return "curie-evolve";
  if(type==="mutation_created") return "evolve-forge";
  if(type==="judge_decision"||type==="strategy_killed") return "forge-judge";
  if(type==="lesson_saved"||type==="experiment_resolved") return "judge-memory";
  if(type==="champion_promoted") return "judge-atlas";
  if(type==="engineer_task_prepared") return "codex-floor";
  return "core";
};
function EventCourier({event}:{event?:FactoryEvent}){if(!event)return null;return <div key={event.id} className={`event-courier route-${courierRoute(event.type)}`}><span>{eventToken[event.type]??"⚡"}</span><small>{event.type.replaceAll("_"," ")}</small></div>}
function JudgeStamp({event}:{event?:FactoryEvent}){if(!event||event.type!=="judge_decision")return null;const d=String(event.payload?.decision??"WAIT").toUpperCase();return <div key={`judge-${event.id}`} className={`judge-stamp ${d.toLowerCase()}`}><b>{d}</b><small>{event.strategy_id??"strategy"}</small></div>}
function CrownBurst({event}:{event?:FactoryEvent}){if(!event||event.type!=="champion_promoted")return null;return <div key={`crown-${event.id}`} className="crown-burst"><i>✨</i><i>👑</i><i>✨</i><i>★</i><i>✨</i></div>}

function Sparkline({values,label}:{values:number[];label:string}){
  const clean=values.filter(v=>Number.isFinite(v));
  if(clean.length<2)return <div className="evo-spark empty"><small>{label}</small><span>collecting epochs…</span></div>;
  const min=Math.min(...clean), max=Math.max(...clean), span=Math.max(1e-9,max-min);
  const points=clean.map((v,i)=>`${(i/(clean.length-1))*100},${38-((v-min)/span)*34}`).join(" ");
  return <div className="evo-spark"><small>{label}</small><svg viewBox="0 0 100 42" preserveAspectRatio="none"><polyline points={points}/></svg><b>{signed(clean.at(-1),1)}</b></div>;
}
function deltaClass(v:any, inverse=false){const n=Number(v);if(!Number.isFinite(n)||Math.abs(n)<1e-9)return "";const good=inverse?n<0:n>0;return good?"positive":"negative"}

export function DarwinFactory({symbol, mode}:{symbol:string;mode:string}){
  const [state,setState]=useState<FactoryState|null>(null), [events,setEvents]=useState<FactoryEvent[]>([]);
  const [selectedAgent,setSelectedAgent]=useState<string|null>(null), [selectedStrategy,setSelectedStrategy]=useState<any|null>(null);
  const [playback,setPlayback]=useState(false), [speed,setSpeed]=useState(1), [cursor,setCursor]=useState(-1);
  const [eventFilter,setEventFilter]=useState("all");
  const [engineerBusy,setEngineerBusy]=useState(false);
  const seen=useRef(new Set<number>());
  const addEvents=(incoming:FactoryEvent[])=>{setEvents(old=>{const next=[...old]; for(const e of incoming){if(!seen.current.has(e.id)){seen.current.add(e.id);next.push(e)}} return next.sort((a,b)=>a.id-b.id).slice(-240)});};
  useEffect(()=>{let stop=false; const load=async()=>{try{const [s,e,o]=await Promise.all([fetch(`${API}/api/factory/state?symbol=${symbol}&mode=${mode}`).then(r=>r.json()),fetch(`${API}/api/factory/events?symbol=${symbol}&mode=${mode}&limit=240`).then(r=>r.json()),fetch(`${API}/api/openbot/state`).then(r=>r.json()).catch(()=>null)]); if(!stop){setState({...s,openbot:o}); addEvents(e.events??[]);}}catch{}}; void load(); const timer=setInterval(load,5000); const ws=new WebSocket(wsUrl(`/ws/factory?symbol=${symbol}&mode=${mode}`)); ws.onmessage=(m)=>{try{const x=JSON.parse(m.data); if(x.events)addEvents(x.events);}catch{}}; return()=>{stop=true;clearInterval(timer);ws.close();};},[symbol,mode]);
  useEffect(()=>{if(!playback||!events.length)return; const t=setInterval(()=>setCursor(c=>c>=events.length-1?0:c+1),Math.max(180,1200/speed)); return()=>clearInterval(t);},[playback,speed,events.length]);
  useEffect(()=>{if(cursor>=events.length)setCursor(events.length-1)},[events.length,cursor]);
  const liveEvent=playback?(events[cursor]??events.at(-1)):events.at(-1);
  const activeAgent=liveEvent?.agent_id??null;
  const lastJudge=[...events].reverse().find(e=>e.type==="judge_decision");
  const selected=state?.agents.find(a=>a.id===selectedAgent)??null;
  const impactMetrics: Record<string,[string,string][]> = {
    atlas:[["Champion",state?.champion?.id??"none"],["Population",String(state?.population??0)],["Experiments",String(state?.experiments.length??0)]],
    curie:[["Running experiments",String(state?.experiments.filter(x=>x.status==="RUNNING").length??0)],["Resolved",String(state?.experiments.filter(x=>x.status==="RESOLVED").length??0)],["Evidence ready",String(state?.research?.eligible??0)]],
    evolve:[["Challengers",String(state?.status_counts.CHALLENGER??0)],["Ever created",String(state?.historical_population??0)],["Mutation budget","controlled"]],
    forge:[["Paper accounts",String(state?.population??0)],["Market",state?.market.health??"WAITING"],["Regime",state?.market.regime??"WAITING"]],
    judge:[["Evidence ready",String(state?.research?.eligible??0)],["Bias guard pass",String(state?.research?.multiple_test_pass??0)],["Last verdict",lastJudge?.payload?.decision??"WAIT"]],
    mnemosyne:[["Lessons loaded",String(state?.lessons.length??0)],["Event archive",String(events.length)],["Storage","SQLite"]],
    cerberus:[["Risk gate",state?.execution.ready?"ARMED":"LOCKED"],["Network",state?.execution.network??"testnet"],["Capital","hard-gated"]],
    hermes:[["Execution",state?.execution.ready?"READY":"LOCKED"],["Venue","Hyperliquid"],["Paper mode",state?.execution.ready?"optional":"yes"]],
  };
  const impactIds=useMemo(()=>{if(!selectedAgent)return new Set<string>(); const map:Record<string,string[]>={atlas:["curie","judge","mnemosyne"],curie:["atlas","evolve"],evolve:["curie","forge"],forge:["evolve","judge"],judge:["forge","atlas","mnemosyne"],mnemosyne:["judge","atlas"],cerberus:["atlas","hermes"],hermes:["cerberus"]}; return new Set([selectedAgent,...(map[selectedAgent]??[])]);},[selectedAgent]);
  const inspect=async(id:string)=>{try{setSelectedStrategy(await fetch(`${API}/api/darwin/strategy/${encodeURIComponent(id)}?symbol=${symbol}&mode=${mode}`).then(r=>r.json()));}catch{}};
  const prepareEngineerTask=async()=>{setEngineerBusy(true);try{await fetch(`${API}/api/engineer/task`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol,mode})});const fresh=await fetch(`${API}/api/factory/state?symbol=${symbol}&mode=${mode}`).then(r=>r.json());setState(fresh);}catch{}finally{setEngineerBusy(false)}};
  if(!state)return <div className="factory-loading"><span>🏭</span><b>Waking the factory crew…</b></div>;
  const A=(id:string)=>state.agents.find(a=>a.id===id)!;
  const isDim=(id:string)=>!!selectedAgent&&!impactIds.has(id);
  const eventKinds=["all","hypothesis_created","mutation_created","judge_decision","strategy_killed","champion_promoted","lesson_saved"];
  const recent=[...events].reverse().filter(e=>eventFilter==="all"||e.type===eventFilter).slice(0,60);
  const geneCatalog=state.research?.genome?.catalog??[];
  const evolution=state.evolution??{};
  const evoHistory=evolution.history??[];
  const latestEvolution=evolution.latest??null;
  const evoDelta=evolution.deltas??{};
  const trend=String(evolution.trend??"WAITING");
  return <div className="factory-page">
    <header className="factory-hero">
      <div><span className="factory-eyebrow">DARWIN FACTORY · CREW MODE</span><h2>Watch the factory learn.</h2><p>Different characters, real events, persistent generations — and an observable paper-research improvement trail.</p></div>
      <div className="factory-live"><span className="pulse-dot"/><b>{state.market.health}</b><small>{state.market.regime} · {state.symbol}</small></div>
    </header>
    <div className="factory-strip">
      <div><small>POPULATION</small><b>{state.population}</b><span>{state.status_counts.CHALLENGER??0} challengers</span></div>
      <div><small>CHAMPION</small><b className="gold">{state.champion?.id??"No crown yet"}</b><span>{state.champion?.metrics?`${signed(state.champion.metrics.return_bps)} bp`:"collecting evidence"}</span></div>
      <div><small>MARKET</small><b>{signed(state.market.benchmark_return_bps)} bp</b><span>epoch benchmark</span></div>
      <div><small>LAST VERDICT</small><b>{lastJudge?.payload?.decision??"WAIT"}</b><span>{lastJudge?.strategy_id??"Judge is watching"}</span></div>
      <div><small>OPENAI 24H</small><b>${fmt(state.research?.llm_usage_24h?.estimated_cost_usd??0,4)}</b><span>{state.research?.llm_usage_24h?.calls??0} calls</span></div>
    </div>

    <section className="factory-shell">
      <aside className="factory-side left">
        <div className="factory-panel-title"><BrainCircuit size={16}/> Factory pulse</div>
        <div className="pulse-card"><span>⚙️</span><div><b>{state.population} paper accounts</b><small>FORGE measures fills, fees & PnL</small></div></div>
        <div className="pulse-card"><span>🧪</span><div><b>{state.experiments.filter(x=>x.status==="RUNNING").length} experiments</b><small>controlled hypotheses alive</small></div></div>
        <div className="pulse-card"><span>🛡️</span><div><b>{state.execution.ready?"Execution armed":"Capital locked"}</b><small>{state.execution.network??"testnet"} · paper remains primary</small></div></div>
        <div className="pulse-card"><span>🧠</span><div><b>OpenAI research brain</b><small>Sol → Sol → Terra · Judge critic · Luna memory</small></div></div>
        <div className="pulse-card"><span>🧬</span><div><b>Genome V{state.research?.genome?.version??2}</b><small>{geneCatalog.length} bounded genes · one variable per experiment</small></div></div>
        <div className="pulse-card"><span>🤖</span><div><b>OpenBot {state.openbot?.enabled?"ONLINE":"OPTIONAL"}</b><small>{state.openbot?.enabled?"4 local AG-UI coworkers available":"bridge ready · install extras + token"}</small></div></div>
        <div className="genome-lab"><h4>Genome V2 genes</h4><div>{geneCatalog.map((g:any)=><span key={g.name} title={g.description}>{g.label??g.name}</span>)}</div></div>
        <div className="mini-leaders"><h4>Top genomes</h4>{state.leaderboard.slice(0,6).map((r,i)=><button key={r.strategy_id} onClick={()=>void inspect(r.strategy_id)}><span>{i+1}</span><b>{r.strategy_id}</b><em className={(r.return_bps??0)>=0?"positive":"negative"}>{signed(r.return_bps)} bp</em></button>)}</div>
      </aside>

      <main className="factory-floor">
        <div className="factory-smoke smoke-a"/><div className="factory-smoke smoke-b"/>
        <EventCourier event={liveEvent}/><JudgeStamp event={liveEvent}/><CrownBurst event={liveEvent}/>
        <div className="engineer-loft"><div className="engineer-avatar">🦝<span>🧑‍💻</span></div><div><small>ABOVE THE FACTORY · CODE ONLY</small><b>CODEX ENGINEER</b><p>{state.engineer?.engineer?.detail??"Engineering agent isolated from capital and trading authority."}</p></div><div className="engineer-meta"><span>{state.engineer?.engineer?.model??"gpt-6-astra"}</span><span>{state.engineer?.engineer?.enabled?"ENABLED":"MANUAL"}</span><button onClick={()=>void prepareEngineerTask()} disabled={engineerBusy}><Wrench size={13}/>{engineerBusy?"Preparing…":"Prepare task"}</button></div></div>
        <div className="brain-rail"><span><b>🧠 RESEARCH BRAINS</b> ATLAS Sol · CURIE Sol · EVOLVE Terra · JUDGE hybrid · MNEMOSYNE Luna</span><span><b>🤖 OPENBOT</b> {state.openbot?.enabled?"4 coworkers online":"bridge optional"}</span><span><b>⚙️ AUTHORITY CODE</b> FORGE · CERBERUS · HERMES</span></div>
        <div className="factory-row top">
          <Character agent={A("atlas")} selected={selectedAgent==="atlas"} active={activeAgent==="atlas"} dimmed={isDim("atlas")} onClick={()=>setSelectedAgent(selectedAgent==="atlas"?null:"atlas")}/>
          <Conveyor label="attention / budget" hot={activeAgent==="atlas"||activeAgent==="curie"}/>
          <Character agent={A("curie")} selected={selectedAgent==="curie"} active={activeAgent==="curie"} dimmed={isDim("curie")} onClick={()=>setSelectedAgent(selectedAgent==="curie"?null:"curie")}/>
          <Conveyor label="hypothesis" hot={liveEvent?.type==="hypothesis_created"}/>
          <Character agent={A("evolve")} selected={selectedAgent==="evolve"} active={activeAgent==="evolve"} dimmed={isDim("evolve")} onClick={()=>setSelectedAgent(selectedAgent==="evolve"?null:"evolve")}/>
        </div>
        <div className="factory-row middle">
          <Character agent={A("mnemosyne")} selected={selectedAgent==="mnemosyne"} active={activeAgent==="mnemosyne"} dimmed={isDim("mnemosyne")} onClick={()=>setSelectedAgent(selectedAgent==="mnemosyne"?null:"mnemosyne")}/>
          <Conveyor label="lessons ↺" hot={liveEvent?.type==="lesson_saved"}/>
          <div className="factory-core"><span className={`factory-token ${liveEvent?"show":""}`}>{eventToken[liveEvent?.type??""]??"⚡"}</span><b>{liveEvent?.label??"Factory waiting"}</b><small>{liveEvent?time(liveEvent.ts):"No event yet"}</small></div>
          <Conveyor label="challengers" hot={liveEvent?.type==="mutation_created"}/>
          <Character agent={A("forge")} selected={selectedAgent==="forge"} active={activeAgent==="forge"} dimmed={isDim("forge")} onClick={()=>setSelectedAgent(selectedAgent==="forge"?null:"forge")}/>
          <Conveyor label="evidence" hot={activeAgent==="forge"||activeAgent==="judge"}/>
          <Character agent={A("judge")} selected={selectedAgent==="judge"} active={activeAgent==="judge"} dimmed={isDim("judge")} onClick={()=>setSelectedAgent(selectedAgent==="judge"?null:"judge")}/>
        </div>
        <div className="capital-boundary"><span>CAPITAL BOUNDARY</span><i/></div>
        <div className="factory-row bottom">
          <div className="champion-pedestal"><Crown size={22}/><small>CHAMPION</small><b>{state.champion?.id??"empty"}</b></div>
          <Conveyor label="validated intent" hot={activeAgent==="cerberus"}/>
          <Character agent={A("cerberus")} selected={selectedAgent==="cerberus"} active={activeAgent==="cerberus"} dimmed={isDim("cerberus")} onClick={()=>setSelectedAgent(selectedAgent==="cerberus"?null:"cerberus")}/>
          <Conveyor label={state.execution.ready?"ALLOW / BLOCK":"LOCKED"} hot={activeAgent==="hermes"}/>
          <Character agent={A("hermes")} selected={selectedAgent==="hermes"} active={activeAgent==="hermes"} dimmed={isDim("hermes")} onClick={()=>setSelectedAgent(selectedAgent==="hermes"?null:"hermes")}/>
          <div className={`exchange-gate ${state.execution.ready?"ready":"locked"}`}><Shield size={24}/><b>HYPERLIQUID</b><small>{state.execution.ready?"guarded execution":"orders locked"}</small></div>
        </div>
      </main>

      <aside className="factory-side right">
        <div className="factory-panel-title"><Sparkles size={16}/> Impact inspector</div>
        {selected?<div className="impact-card" style={{"--agent":selected.color} as React.CSSProperties}><button onClick={()=>setSelectedAgent(null)}><X size={14}/></button><span className="impact-emoji">{persona[selected.id]?.emoji}<i>{persona[selected.id]?.badge}</i></span><h3>{selected.name}</h3><small>{persona[selected.id]?.title} · {selected.role}</small><p>{selected.function}</p><dl><dt>State</dt><dd>{selected.status}</dd><dt>Brain</dt><dd>{selected.llm?.runtime??selected.brain_status} · {selected.llm?.model??"code"}</dd><dt>Class</dt><dd>{selected.brain_class??"—"}</dd><dt>Capital</dt><dd>{selected.capital_permission}</dd></dl><div className="impact-metrics">{(impactMetrics[selected.id]??[]).map(([k,v])=><span key={k}><small>{k}</small><b>{v}</b></span>)}</div><h4>Inputs</h4><p>{selected.inputs.join(" · ")}</p><h4>Outputs</h4><p>{selected.outputs.join(" · ")}</p></div>:<div className="impact-empty"><span>👆</span><b>Click a character</b><p>Its dependencies, decisions and impact paths will light up.</p></div>}
        {selectedStrategy&&<div className="strategy-pop"><button onClick={()=>setSelectedStrategy(null)}><X size={13}/></button><small>GENOME V{selectedStrategy.strategy.genome_version??2} INSPECTOR</small><b>{selectedStrategy.strategy.id}</b><p>{selectedStrategy.lineage.map((x:any)=>x.id).reverse().join(" → ")}</p><span>{selectedStrategy.strategy.family} · {selectedStrategy.strategy.horizon}s · gen {selectedStrategy.strategy.generation}</span><div className="gene-grid">{geneCatalog.map((g:any)=><span key={g.name}><small>{g.label??g.name}</small><b>{fmt(selectedStrategy.strategy[g.name],g.kind==="int"?0:2)}{g.unit?` ${g.unit}`:""}</b></span>)}</div>{selectedStrategy.strategy.mutation?.parameter&&<div className="mutation-note"><small>LAST MUTATION</small><b>{selectedStrategy.strategy.mutation.parameter}</b><p>{String(selectedStrategy.strategy.mutation.from??"?")} → {String(selectedStrategy.strategy.mutation.to??"?")} · ×{fmt(selectedStrategy.strategy.mutation.factor,2)}</p></div>}</div>}
      </aside>
    </section>

    <section className="evolution-observatory">
      <div className="evolution-head">
        <div><span>EVOLUTION OBSERVATORY</span><h3>Is Darwin actually getting better?</h3><p>{evolution.definition??"Paper-research quality only; not a live-profitability forecast."}</p></div>
        <div className={`evolution-verdict ${trend.toLowerCase()}`}><small>TREND · {evolution.confidence??"LOW"} CONFIDENCE</small><b>{trend}</b><span>{evolution.epochs_observed??0} epochs · {evolution.champion_changes??0} champion changes</span></div>
      </div>
      <div className="evolution-kpis">
        <div><small>RESEARCH QUALITY</small><b>{latestEvolution?fmt(latestEvolution.research_quality_index,1):"—"}<i>/100</i></b><span className={deltaClass(evoDelta.research_quality_index)}>Δ {signed(evoDelta.research_quality_index)} pts</span></div>
        <div><small>CHAMPION ALPHA</small><b>{latestEvolution?signed(latestEvolution.champion_alpha_bps):"—"}<i> bp</i></b><span className={deltaClass(evoDelta.champion_alpha_bps)}>Δ {signed(evoDelta.champion_alpha_bps)} bp</span></div>
        <div><small>FEE-STRESS</small><b>{latestEvolution?signed(latestEvolution.champion_fee_stress_bps):"—"}<i> bp</i></b><span className={deltaClass(evoDelta.champion_fee_stress_bps)}>Δ {signed(evoDelta.champion_fee_stress_bps)} bp</span></div>
        <div><small>EVIDENCE</small><b>{latestEvolution?fmt(latestEvolution.champion_evidence_weight*100,0):"—"}<i>%</i></b><span className={deltaClass(evoDelta.champion_evidence_weight)}>Δ {signed((evoDelta.champion_evidence_weight??0)*100,0)} pp</span></div>
        <div><small>DRAWDOWN</small><b>{latestEvolution?fmt(latestEvolution.champion_drawdown_bps,1):"—"}<i> bp</i></b><span className={deltaClass(evoDelta.champion_drawdown_bps,true)}>Δ {signed(evoDelta.champion_drawdown_bps)} bp</span></div>
        <div><small>GENERATION</small><b>G{evolution.lineage?.max_generation??0}</b><span>{evolution.historical_population??state.historical_population} genomes seen</span></div>
      </div>
      <div className="evolution-grid">
        <div className="evolution-chart-card"><div className="evo-card-head"><b>Progress through epochs</b><small>rolling history stored in SQLite</small></div><div className="evo-sparks"><Sparkline label="Quality index" values={evoHistory.map((x:any)=>Number(x.research_quality_index))}/><Sparkline label="Champion alpha bp" values={evoHistory.map((x:any)=>Number(x.champion_alpha_bps))}/><Sparkline label="Fee stress bp" values={evoHistory.map((x:any)=>Number(x.champion_fee_stress_bps))}/></div><div className="epoch-ribbon">{evoHistory.slice(-16).map((x:any)=><span key={x.epoch_id} className={x.champion_id===state.champion?.id?"current":""} title={`Epoch ${x.epoch_id} · ${x.champion_id} · Q ${fmt(x.research_quality_index,1)}`}><i style={{height:`${Math.max(8,Math.min(100,Number(x.research_quality_index)||0))}%`}}/><small>E{x.epoch_id}</small></span>)}</div></div>
        <div className="evolution-chart-card"><div className="evo-card-head"><b>Lineage ladder</b><small>descendants that survived selection</small></div><div className="generation-ladder">{(evolution.lineage?.generation_counts??[]).map((g:any)=><div key={g.generation}><span>G{g.generation}</span><div><i style={{width:`${Math.max(2,(g.active/Math.max(1,g.total))*100)}%`}}/></div><b>{g.active}/{g.total}</b></div>)}</div><div className="family-wins"><small>CHAMPION EPOCHS BY FAMILY</small>{(evolution.lineage?.family_champion_epochs??[]).slice(0,5).map((f:any)=><span key={f.family}><b>{f.family}</b><i style={{width:`${Math.min(100,(f.epochs/Math.max(1,evolution.epochs_observed))*100)}%`}}/><em>{f.epochs}</em></span>)}</div></div>
        <div className="evolution-chart-card gene-evolution"><div className="evo-card-head"><b>What Darwin is changing</b><small>mutation pressure by gene</small></div>{(evolution.gene_evolution??[]).map((g:any)=><div className="gene-evo-row" key={g.name}><span><b>{g.label}</b><small>median {g.active_median==null?"—":fmt(g.active_median,g.name==="confirmation_ticks"?0:2)} {g.unit??""}</small></span><div><i style={{width:`${Math.min(100,(g.mutations/Math.max(1,...(evolution.gene_evolution??[]).map((x:any)=>x.mutations)))*100)}%`}}/></div><em>{g.mutations}×</em></div>)}</div>
      </div>
    </section>

    <section className="factory-playback">
      <div className="playback-head"><div><b>Factory recorder</b><small>{events.length} persisted events loaded · {playback?"PLAYBACK":"LIVE"}</small></div><div className="playback-controls"><button onClick={()=>{setPlayback(false);setCursor(events.length-1)}}><RotateCcw size={14}/></button><button className={playback?"active":""} onClick={()=>{setCursor(cursor<0?0:cursor);setPlayback(!playback)}}>{playback?<Pause size={15}/>:<Play size={15}/>}</button><button onClick={()=>setSpeed(speed===1?2:speed===2?4:speed===4?8:1)}><FastForward size={14}/> x{speed}</button></div></div>
      <div className="playback-scrub"><input type="range" min={0} max={Math.max(0,events.length-1)} value={Math.max(0,cursor<0?events.length-1:cursor)} onChange={e=>{setPlayback(false);setCursor(Number(e.target.value))}}/><span>{liveEvent?`${time(liveEvent.ts)} · ${liveEvent.type.replaceAll("_"," ")}`:"waiting"}</span></div>
      <div className="event-filters">{eventKinds.map(k=><button key={k} className={eventFilter===k?"active":""} onClick={()=>setEventFilter(k)}>{k==="all"?"ALL":`${eventToken[k]??"•"} ${k.replaceAll("_"," ")}`}</button>)}</div>
      <div className="factory-timeline">{recent.map(e=><button key={e.id} className={`${e.type} ${liveEvent?.id===e.id?"active":""}`} onClick={()=>{setPlayback(false);setCursor(events.findIndex(x=>x.id===e.id))}}><span>{eventToken[e.type]??"•"}</span><div><b>{e.agent_name??"SYSTEM"}</b><p>{e.label}</p></div><small>{time(e.ts)}</small></button>)}</div>
    </section>
  </div>
}
