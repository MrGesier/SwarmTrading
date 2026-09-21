import React, { useCallback, useEffect, useState } from "react";
import { BrainCircuit, Crown, Database, Dna, FlaskConical, GitBranch, Hammer, RefreshCw, Scale, Send, ShieldAlert, ShieldCheck, Skull, Trophy, Zap } from "lucide-react";
import { fmt, signed } from "./charts";
import { API } from "./api";

type Lifetime = {
  epochs_seen?: number;
  cumulative_return_bps?: number;
  mean_fitness?: number;
  lifetime_closed_trades?: number;
  scale_epochs?: number;
  kill_epochs?: number;
};

type Leader = {
  strategy_id: string;
  family: string;
  horizon: number;
  generation: number;
  status: string;
  pnl: number;
  return_bps: number;
  max_drawdown_bps: number;
  turnover_x: number;
  fees: number;
  orders: number;
  closed_trades: number;
  win_rate: number | null;
  sample_seconds: number;
  position: number;
  signal: number;
  live_fitness: number;
  raw_fitness?: number;
  evidence_weight?: number;
  trade_z?: number;
  multiple_test_threshold_z?: number;
  multiple_test_pass?: boolean;
  profit_factor?: number | null;
  payoff_ratio?: number | null;
  mean_trade_bps?: number;
  alpha_vs_market_bps?: number;
  lifetime?: Lifetime;
};

type Strategy = {
  id: string;
  parent_id?: string | null;
  generation: number;
  family: string;
  horizon: number;
  threshold: number;
  gain: number;
  status: string;
  mutation?: Record<string, unknown>;
};

type Lesson = {
  id: number;
  ts: number;
  kind: string;
  strategy_id?: string | null;
  confidence: number;
  payload: Record<string, unknown>;
};

type Experiment = {
  id: number;
  parent_id: string;
  child_ids: string[];
  parameter: string;
  factors: number[];
  hypothesis: string;
  rationale: string;
  confidence: number;
  status: string;
  winner_id?: string | null;
  created_ts: number;
};

type LlmUsage = {
  calls: number;
  ok_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  agents: Array<{ agent_id: string; model: string; runtime?: string; provider?: string; calls: number; ok_calls: number; prompt_tokens: number; completion_tokens: number; estimated_cost_usd?: number; avg_latency_ms: number }>;
  estimated_cost_usd?: number;
};

type DarwinState = {
  symbol: string;
  mode: string;
  population: number;
  historical_population: number;
  status_counts: Record<string, number>;
  champion: Strategy | null;
  leaderboard: Leader[];
  recent_trades?: Array<{strategy_id:string;opened_at:number|null;closed_at:number;direction:string;entry_mid:number|null;exit_mid:number;net_pnl_usd:number;fees_usd:number|null;reason:string}>;
  auto_epoch_enabled?: boolean;
  cycle?: {seconds_remaining: number; trigger: string};
  epoch_seconds: number;
  seconds_since_epoch: number;
  lessons: Lesson[];
  epochs: Array<{ id: number; ts: number; champion_id: string | null; eligible: number; killed: number; created: number }>;
  paper: { notional_usd: number; fee_bps: number; fee_stress_multiplier?: number };
  judge_config: { multiple_testing_guard?: boolean; multiple_test_threshold_z?: number };
  benchmark?: { market_return_bps: number; buy_hold_after_entry_fee_bps: number; sample_seconds: number };
  experiments?: Experiment[];
  llm_usage_24h?: LlmUsage;
  error?: string;
};

type ResearchState = {
  evidence: { population: number; eligible: number; multiple_test_pass: number; threshold_z: number; median_evidence_weight: number; best_trade_z: number };
  market: { regime: string; health: string; volatility: number | null; spread_bps: number | null; flow: number | null; weighted_imbalance: number | null };
  benchmark: { market_return_bps: number; buy_hold_after_entry_fee_bps: number; sample_seconds: number };
  experiments: Experiment[];
  llm_usage_24h: LlmUsage;
  family_cells: Array<{ family: string; horizon: number; n: number; mean_live_fitness: number; mean_return_bps: number; evidence_pass: number }>;
  paper_only: boolean;
};

type StrategyDetail = {
  strategy: Strategy;
  lineage: Strategy[];
  history: Array<{ epoch_id: number; ts: number; return_bps: number; max_drawdown_bps: number; fitness: number; decision: string; closed_trades: number; details?: Record<string, unknown> }>;
};

type ExecutionState = {
  venue: string;
  enabled: boolean;
  network: string;
  sdk_installed: boolean;
  credentials_present: boolean;
  mainnet_unlocked: boolean;
  ready: boolean;
  max_notional_usd: number;
  mode: string;
};

type AgentView = {
  id: string;
  name: string;
  color: string;
  role: string;
  function: string;
  code_path: string;
  inputs: string[];
  outputs: string[];
  llm_capable: boolean;
  brain_class?: string;
  capital_permission: string;
  order: number;
  status: string;
  detail: string;
  brain_status?: string;
  llm?: { enabled?: boolean; available?: boolean; runtime?: string; provider?: string; model?: string; reasoning_effort?: string; authority?: string; last?: { ok?: boolean; latency_ms?: number; error?: string } | null };
};

type AgentsState = { architecture: string; champion_id: string | null; market_health: string; agents: AgentView[] };

const agentIcon: Record<string, React.ReactNode> = {
  atlas: <Crown size={17} />, curie: <FlaskConical size={17} />, evolve: <GitBranch size={17} />, forge: <Hammer size={17} />,
  judge: <Scale size={17} />, mnemosyne: <Database size={17} />, cerberus: <ShieldAlert size={17} />, hermes: <Send size={17} />,
};

const horizonLabel = (h: number) => (h >= 60 ? `${h / 60}m` : `${h}s`);
const duration = (seconds: number) => seconds < 60 ? `${Math.round(seconds)}s` : seconds < 3600 ? `${Math.round(seconds / 60)}m` : `${(seconds / 3600).toFixed(1)}h`;
const pct = (x?: number) => `${Math.round((x ?? 0) * 100)}%`;
const tokenFmt = (x?: number) => (x ?? 0) >= 1000 ? `${((x ?? 0) / 1000).toFixed(1)}k` : String(x ?? 0);

export function DarwinLab({ symbol, mode }: { symbol: string; mode: string }) {
  const [state, setState] = useState<DarwinState | null>(null);
  const [research, setResearch] = useState<ResearchState | null>(null);
  const [execution, setExecution] = useState<ExecutionState | null>(null);
  const [agents, setAgents] = useState<AgentsState | null>(null);
  const [strategyDetail, setStrategyDetail] = useState<StrategyDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [d, x, a, r] = await Promise.all([
        fetch(`${API}/api/darwin/state?symbol=${symbol}&mode=${mode}`),
        fetch(`${API}/api/execution/hyperliquid/status`),
        fetch(`${API}/api/agents/state?symbol=${symbol}&mode=${mode}`),
        fetch(`${API}/api/darwin/research?symbol=${symbol}&mode=${mode}`),
      ]);
      if (!d.ok) throw new Error("Darwin state unavailable");
      setState(await d.json());
      if (x.ok) setExecution(await x.json());
      if (a.ok) setAgents(await a.json());
      if (r.ok) setResearch(await r.json());
    } catch (e) { setMessage(String(e)); }
  }, [symbol, mode]);

  useEffect(() => {
    setStrategyDetail(null);
    void refresh();
    const timer = setInterval(() => void refresh(), 2500);
    return () => clearInterval(timer);
  }, [refresh]);

  async function inspectStrategy(strategyId: string) {
    try {
      const r = await fetch(`${API}/api/darwin/strategy/${encodeURIComponent(strategyId)}?symbol=${symbol}&mode=${mode}`);
      if (r.ok) setStrategyDetail(await r.json());
    } catch { /* inspection is optional */ }
  }

  async function runJudge() {
    setBusy(true); setMessage("");
    try {
      const r = await fetch(`${API}/api/darwin/epoch?symbol=${symbol}&mode=${mode}&force=true`, { method: "POST" });
      if (!r.ok) throw new Error("Judge epoch failed");
      const result = await r.json();
      setMessage(!result.ran
        ? `Not enough evidence yet · best sample ${duration(result.max_sample_seconds ?? 0)} · max ${result.max_closed_trades ?? 0} closed trades.`
        : result.champion_id
          ? `Epoch ${result.epoch_id}: champion ${result.champion_id} · ${result.created} mutations · ${result.killed} killed · ${result.resolved_experiments ?? 0} experiments resolved.`
          : `Epoch ${result.epoch_id}: no champion promoted yet.`);
      await refresh();
    } catch (e) { setMessage(String(e)); } finally { setBusy(false); }
  }

  if (!state) return <div className="darwin-loading"><RefreshCw size={18} /> Initializing Darwin population…</div>;

  const championMetric = state.champion ? state.leaderboard.find((r) => r.strategy_id === state.champion?.id) : null;
  const usage = research?.llm_usage_24h ?? state.llm_usage_24h;
  const experiments = research?.experiments ?? state.experiments ?? [];

  return (
    <div className="darwin-lab">
      <div className="darwin-hero">
        <div>
          <span className="eyebrow"><Dna size={14} /> EVOLUTION ENGINE · V0.11 OPENAI BRAIN + OPENBOT</span>
          <h2>Résultats et activité paper</h2>
          <p>Chaque stratégie possède un compte simulé indépendant. Les résultats incluent les frais modélisés ; la sélection et les mutations se suivent dans Factory.</p>
        </div>
        <div className="judge-auto-note"><b>{state.auto_epoch_enabled?"JUDGE automatique activé":"JUDGE automatique désactivé"}</b><small>La sélection se déclenche à l’échéance si les preuves sont suffisantes.</small><details><summary>Commande manuelle facultative</summary><button onClick={runJudge} disabled={busy}><BrainCircuit size={16} /> {busy ? "Sélection…" : "Anticiper le cycle maintenant"}</button></details></div>
      </div>

      {message && <div className="darwin-message">{message}</div>}
      {state.error && <div className="darwin-message error">Darwin runtime: {state.error}</div>}

      <details className="advanced-panel"><summary>Architecture technique des agents</summary>{agents && <section className="agent-architecture">
        <div className="darwin-card-head"><span><BrainCircuit size={16} /> Agent architecture</span><small>{agents.architecture}</small></div>
        <div className="agent-flow">
          {agents.agents.map((agent, index) => <React.Fragment key={agent.id}>
            <article className="agent-card" style={{ "--agent-color": agent.color } as React.CSSProperties}>
              <div className="agent-card-top"><span className="agent-icon">{agentIcon[agent.id] ?? <BrainCircuit size={17} />}</span><div><b>{agent.name}</b><small>{agent.role}</small></div><span className={`agent-status ${agent.status.toLowerCase()}`}>{agent.status}</span></div>
              <p>{agent.function}</p><div className="agent-detail">{agent.detail}</div>
              <div className="agent-meta"><span><b>Code</b>{agent.code_path}</span><span><b>Brain</b>{agent.llm?.runtime ?? "code"} · {agent.llm?.model ?? "deterministic"}</span><span><b>Class</b>{agent.brain_class ?? agent.llm?.authority ?? "—"}</span><span><b>Capital</b>{agent.capital_permission.replaceAll("_", " ")}</span></div>
            </article>{index < agents.agents.length - 1 && <span className="agent-arrow">→</span>}
          </React.Fragment>)}
        </div>
        <div className="agent-safety-note"><ShieldCheck size={15} /> ATLAS/CURIE/EVOLVE/MNEMOSYNE reason with OpenAI; JUDGE is hybrid. FORGE/CERBERUS/HERMES remain deterministic authority code.</div>
      </section>}</details>

      <div className="darwin-kpis">
        <div><small>STRATÉGIES PAPER</small><b>{state.population}</b><span>{state.status_counts.CHALLENGER ?? 0} challengers · {state.historical_population} ever created</span></div>
        <div><small>CHAMPION</small><b className="positive">{state.champion?.id ?? "No promotion yet"}</b><span>{championMetric ? `${signed(championMetric.return_bps, 1)} bp · evidence ${pct(championMetric.evidence_weight)}` : "Waiting for sufficient evidence"}</span></div>
        <div><small>CAPITAL SIMULÉ / STRATÉGIE</small><b>${fmt(state.paper.notional_usd, 0)}</b><span>{fmt(state.paper.fee_bps, 1)} bp / fill</span></div>
        <div><small>PROCHAINE SÉLECTION</small><b>{duration(state.cycle?.seconds_remaining ?? Math.max(0, state.epoch_seconds - state.seconds_since_epoch))}</b><span>{state.cycle?.trigger==="AUTO_REPAIR"?"Cycle anticipé : problème détecté":`Cycle normal ${duration(state.epoch_seconds)}`}</span></div>
      </div>

      <details className="advanced-panel"><summary>Diagnostics de sélection et budget IA</summary><section className="research-cockpit">
        <div className="darwin-card-head"><span><FlaskConical size={16} /> Research cockpit</span><small>evidence before narrative</small></div>
        <div className="research-kpis">
          <div><small>EVIDENCE READY</small><b>{research?.evidence.eligible ?? 0}/{research?.evidence.population ?? state.population}</b><span>{research?.evidence.multiple_test_pass ?? 0} clear selection-bias guard</span></div>
          <div><small>ROBUSTNESS GATES</small><b>{state.judge_config.multiple_testing_guard === false ? "PARTIAL" : "ON"}</b><span>z ≥ {fmt(research?.evidence.threshold_z ?? state.judge_config.multiple_test_threshold_z ?? 0, 2)} · fees stress ×{fmt(state.paper.fee_stress_multiplier ?? 1.5, 1)}</span></div>
          <div><small>MARKET / BENCHMARK</small><b>{research?.market.regime ?? "WAITING"}</b><span>BTC {signed(research?.benchmark.market_return_bps ?? state.benchmark?.market_return_bps ?? 0, 1)} bp · vol {fmt(research?.market.volatility ?? 0, 2)}</span></div>
          <div><small>OPENAI · 24H</small><b>{usage?.calls ?? 0} calls · ${fmt(usage?.estimated_cost_usd ?? 0, 4)}</b><span>{tokenFmt((usage?.prompt_tokens ?? 0) + (usage?.completion_tokens ?? 0))} tokens · {usage?.ok_calls ?? 0} successful</span></div>
        </div>
      </section></details>

      <details className="advanced-panel"><summary>Détail par famille et horizon</summary>{research?.family_cells?.length ? <section className="darwin-card family-map-card">
        <div className="darwin-card-head"><span><Dna size={16} /> Family × horizon map</span><small>population cells · mean evidence-weighted fitness</small></div>
        <div className="family-map">{research.family_cells.slice(0, 16).map((cell) => <div className="family-cell" key={`${cell.family}-${cell.horizon}`}>
          <div><b>{cell.family}</b><span>{horizonLabel(cell.horizon)}</span></div>
          <strong className={cell.mean_live_fitness >= 0 ? "positive" : "negative"}>{signed(cell.mean_live_fitness, 1)}</strong>
          <small>{signed(cell.mean_return_bps, 1)} bp raw · {cell.evidence_pass}/{cell.n} pass</small>
        </div>)}</div>
      </section> : null}</details>

      <details className="advanced-panel"><summary>Quels indicateurs font réellement évoluer les stratégies ?</summary><p>Book pressure utilise l’imbalance pondérée du carnet. Order flow utilise le flux exécuté. Microprice utilise son écart au mid et le spread. Les autres familles exploitent les rendements et la volatilité ; Breakout ajoute le flux.</p><p>Les mutations ajustent huit paramètres d’entrée et de sortie. Les familles et leurs combinaisons de signaux restent prédéfinies : tous les indicateurs visibles dans Marché, notamment le VWAP et les diagnostics graphiques, ne sont pas automatiquement utilisés par Darwin. Le panneau Autocorrection teste la qualité du code, sans constituer une preuve de rentabilité.</p></details>
      <section className="darwin-card trade-journal">
        <div className="darwin-card-head"><span>Derniers trades paper clôturés</span><small>{state.symbol} · {state.mode} · toutes les stratégies</small></div>
        <p>Journal enregistré depuis cette mise à jour, conservé entre les cycles. Les anciennes opérations individuelles ne peuvent pas être reconstituées. Prix affichés : milieu du carnet, pas prix d'exécution.</p>
        {!(state.recent_trades??[]).length?<p className="journal-empty">Aucune clôture journalisée pour le moment. Les positions ouvertes apparaissent dans le classement ; le journal se remplit automatiquement après clôture.</p>:<div className="darwin-table-wrap"><table className="darwin-table"><thead><tr><th>Clôture</th><th>Stratégie</th><th>Sens</th><th>Entrée / sortie · prix repère</th><th>Net USD</th><th>Frais USD</th><th>Sortie</th></tr></thead><tbody>{(state.recent_trades??[]).slice(0,50).map((t,i)=><tr key={`${t.strategy_id}-${t.closed_at}-${i}`}><td>{new Date(t.closed_at*1000).toLocaleString()}</td><td><button className="strategy-name-button" onClick={()=>void inspectStrategy(t.strategy_id)}>{t.strategy_id}</button></td><td>{t.direction}</td><td>{t.entry_mid==null?"—":fmt(t.entry_mid,2)} / {fmt(t.exit_mid,2)}</td><td className={t.net_pnl_usd>=0?"positive":"negative"}>{signed(t.net_pnl_usd,2)}</td><td>{t.fees_usd==null?"—":fmt(t.fees_usd,2)}</td><td>{t.reason}</td></tr>)}</tbody></table></div>}
      </section>
      <div className="darwin-grid">
        <section className="darwin-card leaderboard-card">
          <div className="darwin-card-head"><span><Trophy size={16} /> Classement des stratégies paper</span><small>fenêtre courante · classement par score de recherche</small></div>
          <div className="darwin-table-wrap"><table className="darwin-table research-table">
            <caption>Les compteurs repartent à zéro à chaque cycle. Une stratégie sans trade peut devancer une stratégie en perte. Cliquer sur son nom ouvre son historique de cycles.</caption>
            <thead><tr><th>#</th><th>Stratégie</th><th>Horizon / génération</th><th>PnL net USD</th><th>Rendement %</th><th>Frais USD</th><th>Trades clos · cycle / antérieurs</th><th>Position</th></tr></thead>
            <tbody>{state.leaderboard.slice(0,20).map((r,i)=><tr key={r.strategy_id} className={r.status==="CHAMPION"?"champion-row":""}>
              <td>{i+1}</td><td><button className="strategy-name-button" onClick={()=>void inspectStrategy(r.strategy_id)} title={r.strategy_id}>{r.family}<small>{r.strategy_id}</small></button></td>
              <td>{horizonLabel(r.horizon)} · G{r.generation}</td><td className={r.pnl>=0?"positive":"negative"}>{signed(r.pnl,2)}</td><td>{signed(r.return_bps/100,2)} %</td><td>{fmt(r.fees,2)}</td>
              <td>{r.closed_trades} / {r.lifetime?.lifetime_closed_trades??0}<small>{r.closed_trades===0?"Aucune clôture ce cycle":""}</small></td><td>{r.position>0?"LONG":r.position<0?"SHORT":"À plat"}</td>
            </tr>)}</tbody>
          </table></div>
        </section>

        <section className="darwin-card execution-card">
          <div className="darwin-card-head"><span><Zap size={16} /> Hyperliquid execution</span><small>{execution?.network ?? "testnet"}</small></div>
          <div className={`execution-lock ${execution?.ready ? "ready" : ""}`}><ShieldCheck size={28} /><div><b>{execution?.ready ? "EXECUTION READY" : "EXECUTION LOCKED"}</b><span>{execution?.ready ? "Guarded connector configured" : "Research/paper mode only"}</span></div></div>
          <div className="execution-lines"><span>Official SDK <b>{execution?.sdk_installed ? "installed" : "not installed"}</b></span><span>API credentials <b>{execution?.credentials_present ? "present" : "absent"}</b></span><span>Enabled <b>{execution?.enabled ? "yes" : "no"}</b></span><span>Max order <b>${fmt(execution?.max_notional_usd ?? 0, 0)}</b></span></div>
          <p>Research can run continuously while the external-order path remains locked. CERBERUS/HERMES cannot turn paper evidence into capital without the explicit execution gates.</p>
        </section>
      </div>

      {strategyDetail && <section className="darwin-card strategy-inspector">
        <div className="darwin-card-head"><span><GitBranch size={16} /> Strategy inspector · <span className="mono">{strategyDetail.strategy.id}</span></span><button className="ghost-mini" onClick={() => setStrategyDetail(null)}>close</button></div>
        <div className="strategy-inspector-grid">
          <div><small>LINEAGE</small><p>{strategyDetail.lineage.map((x) => x.id).reverse().join(" → ")}</p><small>PARAMETERS</small><p>threshold {fmt(strategyDetail.strategy.threshold, 4)} · gain {fmt(strategyDetail.strategy.gain, 3)} · {strategyDetail.strategy.family} / {horizonLabel(strategyDetail.strategy.horizon)}</p></div>
          <div><small>HISTORICAL EPOCHS</small>{strategyDetail.history.length ? strategyDetail.history.slice(0, 8).map((h) => <div className="strategy-history-row" key={h.epoch_id}><b>#{h.epoch_id}</b><span className={h.return_bps >= 0 ? "positive" : "negative"}>{signed(h.return_bps, 1)} bp</span><span>DD {fmt(h.max_drawdown_bps, 1)}</span><span>{h.closed_trades} trades</span><em>{h.decision}</em></div>) : <p>No frozen epoch yet.</p>}</div>
        </div>
      </section>}

      <div className="darwin-grid lower">
        <section className="darwin-card experiment-card">
          <div className="darwin-card-head"><span><FlaskConical size={16} /> Experiment ledger</span><small>CURIE → EVOLVE → evidence</small></div>
          <div className="experiment-list">{experiments.length ? experiments.slice(0, 12).map((exp) => <div key={exp.id} className={`experiment-row ${exp.status.toLowerCase()}`}>
            <span className="experiment-id">#{exp.id}</span><div><b>{exp.parameter} × {exp.factors.map((x) => fmt(x, 3)).join(" / ")}</b><p>{exp.hypothesis}</p><small>parent <span className="mono">{exp.parent_id}</span> · {exp.child_ids.length} challengers · {Math.round(exp.confidence * 100)}% scientist confidence</small></div><span className="experiment-status">{exp.status}{exp.winner_id ? ` · ${exp.winner_id}` : ""}</span>
          </div>) : <p className="muted padded">No controlled experiment registered yet.</p>}</div>
        </section>

        <section className="darwin-card lifecycle-card">
          <div className="darwin-card-head"><span><Skull size={16} /> Selection history</span><small>{state.epochs.length} recent epochs</small></div>
          {state.epochs.length ? state.epochs.map((e) => <div className="epoch-row" key={e.id}><b>#{e.id}</b><span>{e.champion_id ?? "No champion"}</span><small>{e.eligible} eligible · {e.killed} killed · {e.created} born</small></div>) : <p className="muted padded">No completed selection epoch yet.</p>}
        </section>
      </div>

      <section className="darwin-card memory-card">
        <div className="darwin-card-head"><span><BrainCircuit size={16} /> Experience memory</span><small>SQLite · cumulative · evidence-backed</small></div>
        <div className="memory-list">{state.lessons.length ? state.lessons.map((lesson) => <div key={lesson.id}><span className="memory-icon">{lesson.kind === "champion" ? <Trophy size={14} /> : <Dna size={14} />}</span><div><b>{lesson.kind.replaceAll("_", " ")}</b><p>{JSON.stringify(lesson.payload)}</p></div><small>{Math.round(lesson.confidence * 100)}% conf.</small></div>) : <p className="muted">Aucune leçon enregistrée. Laisser Darwin collecter les observations : JUDGE interviendra automatiquement à la prochaine échéance.</p>}</div>
      </section>
    </div>
  );
}
