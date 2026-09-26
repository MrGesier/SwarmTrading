import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  Download,
  FlaskConical,
  Grid2X2,
  Layers3,
  Pause,
  Play,
  Radio,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import type { State, Strategy, Transition } from "./types";
import {
  PriceChart,
  Liquidity,
  Spark,
  Phase,
  fmt,
  signed,
  clock,
} from "./charts";
import "./style.css";
import { Help } from "./help";
import { Technical } from "./technical";
import { DarwinLab } from "./darwin";
import { DarwinFactory } from "./factory";
import { API, wsUrl } from "./api";
const horizonLabel = (h: number) => (h >= 60 ? `${h / 60} min` : `${h}s`);

const routes = [
  { name: "Marché", icon: Grid2X2, path: "/" },
  { name: "Diagnostic des signaux", icon: Zap, path: "/intent" },
  { name: "Population des signaux", icon: Workflow, path: "/research" },
  { name: "Replay du marché", icon: RotateCcw, path: "/replay" },
  { name: "Recherche et trades", icon: FlaskConical, path: "/darwin" },
  { name: "Factory", icon: Workflow, path: "/factory" },
];
function Panel({
  title,
  label,
  children,
  className = "",
}: {
  title: string;
  label?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <h2>
          {title}
          <Help label={title} />
        </h2>
        <span>
          {label}
          <Help label={String(label)} />
        </span>
      </div>
      {children}
    </section>
  );
}
function Metric({
  label,
  value,
  sub,
  color = "",
  values,
}: {
  label: string;
  value: string;
  sub: string;
  color?: string;
  values?: number[];
}) {
  return (
    <div className="metric">
      <span className="eyebrow">
        {label}
        <Help label={label} />
      </span>
      <div className={`metric-value ${color}`}>{value}</div>
      <span className="metric-sub">{sub}</span>
      {values && (
        <Spark
          values={values}
          color={
            color === "purple"
              ? "#ad9be9"
              : color === "blue"
                ? "#70b9ed"
                : "#59ddb2"
          }
        />
      )}
    </div>
  );
}

function App() {
  const [route, setRoute] = useState(location.pathname),
    [symbol, setSymbol] = useState("BTCUSDT"),
    [mode] = useState("live"),
    [horizon, setHorizon] = useState(5);
  const [live, setLive] = useState<State | null>(null),
    [connection, setConnection] = useState("Connecting to local engine…"),
    [connected, setConnected] = useState(false);
  const [vwap, setVwap] = useState(true),
    [detail, setDetail] = useState<Strategy | Transition | null>(null);
  const [frames, setFrames] = useState<State[]>([]),
    [cursor, setCursor] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [error, setError] = useState("");
  const [priceDelta, setPriceDelta] = useState(10),
    [vol, setVol] = useState(1),
    [flow, setFlow] = useState(0),
    [result, setResult] = useState<{
      consensus: number;
      flips: number;
      base_consensus: number;
      ready: boolean;
    } | null>(null);
  const [family, setFamily] = useState("All families");
  const replay = route === "/replay";
  const s = replay ? (frames[cursor] ?? live) : live;
  useEffect(() => {
    if (!detail) return;
    const previous = document.activeElement as HTMLElement | null;
    const modal = document.querySelector<HTMLElement>(".detail-modal");
    modal?.querySelector<HTMLElement>("button")?.focus();
    const trap = (e: KeyboardEvent) => {
      if (e.key === "Tab") {
        e.preventDefault();
        modal?.querySelector<HTMLElement>("button")?.focus();
      }
    };
    modal?.addEventListener("keydown", trap);
    return () => {
      modal?.removeEventListener("keydown", trap);
      previous?.focus();
    };
  }, [detail]);
  function navigate(path: string) {
    history.pushState({}, "", path);
    setRoute(path);
    setDetail(null);
  }
  useEffect(() => {
    const pop = () => setRoute(location.pathname);
    window.addEventListener("popstate", pop);
    return () => window.removeEventListener("popstate", pop);
  }, []);
  useEffect(() => {
    let stop = false,
      ws: WebSocket,
      timer: ReturnType<typeof setTimeout>,
      watchdog: ReturnType<typeof setInterval>;
    let last = Date.now();
    setLive(null);
    setFrames([]);
    setResult(null);
    setConnected(false);
    setConnection("Connecting to market stream…");
    function connect() {
      ws = new WebSocket(wsUrl(`/ws?symbol=${symbol}&mode=${mode}`));
      ws.onmessage = (e) => {
        if (stop) return;
        last = Date.now();
        const data = JSON.parse(e.data);
        if (data.features) {
          setLive(data);
          setConnected(true);
          setConnection("");
        } else {
          setConnected(false);
          setConnection(
            `${data.status} · ${data.message || "Waiting for an exchange snapshot"}`,
          );
        }
      };
      ws.onclose = () => {
        if (!stop) {
          setConnected(false);
          setConnection("Engine disconnected · reconnecting…");
          timer = setTimeout(connect, 2000);
        }
      };
      ws.onerror = () => ws.close();
    }
    connect();
    watchdog = setInterval(() => {
      if (Date.now() - last > 4000) {
        setConnected(false);
        setConnection("Data stream is stale · RISK_OFF");
      }
    }, 1000);
    return () => {
      stop = true;
      clearTimeout(timer);
      clearInterval(watchdog);
      ws.close();
    };
  }, [symbol, mode]);
  useEffect(() => {
    if (!playing || !replay) return;
    const id = setInterval(
      () =>
        setCursor((c) => {
          if (c >= frames.length - 1) {
            setPlaying(false);
            return c;
          }
          return Math.min(c + speed, frames.length - 1);
        }),
      500,
    );
    return () => clearInterval(id);
  }, [playing, replay, speed, frames.length]);
  useEffect(() => {
    if (route !== "/intent" || !live) return;
    const abort = new AbortController();
    const timeout = setTimeout(async () => {
      try {
        const r = await fetch(`${API}/api/counterfactual`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol,
            mode,
            price_bp: priceDelta,
            vol_scale: vol,
            flow_delta: flow,
            horizon,
          }),
          signal: abort.signal,
        });
        if (!r.ok) throw new Error("Scenario unavailable");
        setResult(await r.json());
      } catch (e) {
        if (!abort.signal.aborted) setError(String(e));
      }
    }, 200);
    return () => {
      clearTimeout(timeout);
      abort.abort();
    };
  }, [route, symbol, mode, horizon, priceDelta, vol, flow, live?.timestamp]);
  async function loadReplay() {
    setError("");
    setPlaying(false);
    try {
      const r = await fetch(`${API}/api/replay?symbol=${symbol}&mode=${mode}`);
      if (!r.ok) throw new Error("Could not load recording");
      const data: State[] = await r.json();
      setFrames(data);
      setCursor(0);
      if (!data.length)
        setError("No frames yet. Let the stream run for a few seconds.");
    } catch (e) {
      setError(String(e));
    }
  }
  function seek(time: number) {
    if (frames.length)
      setCursor(
        frames.reduce(
          (best, f, i) =>
            Math.abs(f.timestamp - time) <
            Math.abs(frames[best].timestamp - time)
              ? i
              : best,
          0,
        ),
      );
  }
  async function exportState() {
    try {
      const r = await fetch(`${API}/api/export?symbol=${symbol}&mode=${mode}`);
      if (!r.ok) throw new Error("Export failed");
      const blob = await r.blob(),
        url = URL.createObjectURL(blob),
        a = document.createElement("a");
      a.href = url;
      a.download = `swarmtrade-${symbol}-${mode}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(String(e));
    }
  }
  const scoped = s?.strategies.filter((g) => g.horizon === horizon) ?? [];
  const currentHorizon = s?.cone.find((c) => c.horizon === horizon);
  const currentConsensus =
    s?.cone.find((c) => c.horizon === horizon)?.consensus ?? 0;
  const isHealthy =
    !!s && (replay || connected) && s.health.status === "HEALTHY";
  const currentIntent = isHealthy ? s?.intent.state : "RISK_OFF";
  return (
    <div className="app">
      <aside className="sidebar">
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            navigate("/");
          }}
        >
          <span className="brand-icon">
            <img
              src="/mister-gesier-logo.png"
              alt="Crêtes des Pyrénées et courbe de trading"
            />
          </span>
          <span>
            SWARM <span className="brand-light">TRADE</span>
            <small className="byline">by Mister Gésier</small>
          </span>
        </a>
        <div className="nav-label">
          DARWIN <span>V0.11</span>
        </div>
        <nav>
          {routes.filter(r => ["/", "/darwin", "/factory"].includes(r.path)).map((r) => (
            <a
              key={r.path}
              className={route === r.path ? "active" : ""}
              href={r.path}
              onClick={(e) => {
                e.preventDefault();
                navigate(r.path);
              }}
            >
              <r.icon size={18} />
              {r.name}
              {route === r.path && <span className="nav-indicator" />}
            </a>
          ))}
          <details className="nav-advanced"><summary>Diagnostics avancés</summary>{routes.filter(r => !["/", "/darwin", "/factory"].includes(r.path)).map(r => <a key={r.path} href={r.path} className={route===r.path?"active":""} onClick={e=>{e.preventDefault();navigate(r.path)}}><r.icon size={16}/>{r.name}</a>)}</details>
        </nav>
        <div className="sidebar-note">
          <Layers3 size={19} />
          <strong>Observe. Infer. Anticipate.</strong>
          <p>
            Independent hypotheses.
            <br />
            One synchronized market state.
          </p>
        </div>
        <div className="engine-status">
          <span className={`dot ${isHealthy ? "" : "amber-dot"}`} />
          <div>
            {isHealthy ? "Engine operational" : "Engine waiting"}
            <small>{s?.swarm.raw ?? 320} signaux du marché</small>
          </div>
        </div>
        <div className="read-only">
          <ShieldCheck size={15} /> GUARDED <span>EXECUTION</span>
        </div>
      </aside>
      <div className="workspace">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>
              {routes.find((r) => r.path === route)?.name ?? "Marché"}
            </strong>
          </div>
          <div className="top-right">
            <span className="research-badge">RESEARCH BUILD</span>
            <span className="utc">
              {s ? clock(s.timestamp) : "—"} <small>LOCAL</small>
            </span>
            <button
              className="icon-button"
              onClick={exportState}
              aria-label="Export current state"
            >
              <Download size={17} />
            </button>
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                SWARM TRADE{" "}
                <span className="heading-byline">
                  BY MISTER GÉSIER · PYRÉNÉES
                </span>
              </div>
              <h1>
                {routes.find((r) => r.path === route)?.name ?? "Marché"}
                <span className="heading-dot" />
              </h1>
              <p>
                {route === "/intent"
                  ? "Explore the market states that could move the swarm."
                  : route === "/research"
                    ? "Inspect independent hypotheses and effective support."
                    : route === "/darwin"
                      ? "Consultez les trades clôturés, les positions et les résultats de chaque stratégie."
                      : route === "/factory"
                        ? "Suivez les cycles automatiques, les mutations et leur performance mesurée."
                      : replay
                        ? "Rewind the whole terminal to the information available then."
                        : "Market structure, collective intent, and the space between."}
              </p>
            </div>
            <div className="page-actions">
              <button
                className="secondary"
                onClick={() => {
                  navigate("/replay");
                  void loadReplay();
                }}
              >
                <RotateCcw size={15} /> Replay du marché
              </button>
              <span className="paper">
                <ShieldCheck size={14} /> {route === "/darwin" || route === "/factory" ? "Trading simulé" : "Lecture seule"}
              </span>
            </div>
          </div>
          <div className="market-bar">
            <div className="symbol-pick">
              <span className="coin">
                {symbol === "BTCUSDT" ? "₿" : symbol === "ETHUSDT" ? "Ξ" : "◎"}
              </span>
              <div>
                <select
                  aria-label="Market symbol"
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                >
                  {["BTCUSDT", "ETHUSDT", "SOLUSDT"].map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
                <small>
                  {mode === "live" ? "Hyperliquid perps" : "Synthetic market"}
                </small>
              </div>
            </div>
            <div className="market-price">
              {s ? fmt(s.features.mid, s.features.mid < 1000 ? 3 : 2) : "—"}
              <small
                className={
                  (s?.features.returns["30"] ?? 0) >= 0
                    ? "positive"
                    : "negative"
                }
              >
                {s ? signed(s.features.returns["30"], 1) : "—"} bp{" "}
                <span>/ 30s</span>
              </small>
            </div>
            <div className="market-stat">
              <small>
                SPREAD <Help label="SPREAD" />
              </small>
              <b>
                {s ? fmt(s.features.spread) : "—"} <em>bp</em>
              </b>
            </div>
            <div className="market-stat regime">
              <small>
                REGIME <Help label="REGIME" />
              </small>
              <b>
                <span className="dot amber-dot" />
                {s?.regime ?? "WARMING UP"}
              </b>
            </div>
            <div className="stream-controls">
              <span className="paper-source">Hyperliquid · données actuelles · PAPER</span>
              {route !== "/darwin" && route !== "/factory" && <><select
                aria-label="Strategy horizon"
                value={horizon}
                onChange={(e) => setHorizon(Number(e.target.value))}
              >
                <option value={1}>1s horizon</option>
                <option value={5}>5s horizon</option>
                <option value={30}>30s horizon</option>
                <option value={60}>1 min horizon</option>
                <option value={180}>3 min horizon</option>
              </select>
              <Help label="Horizon" /></>}
            </div>
          </div>
          {route !== "/darwin" && route !== "/factory" && s && currentHorizon && !currentHorizon.ready && (
            <div className="notice">
              <Activity size={15} />
              Horizon {horizonLabel(horizon)} en échauffement · encore{" "}
              {currentHorizon.remaining} s d’observation nécessaires. Les
              stratégies de cet horizon restent neutres.
            </div>
          )}
          {connection && (
            <div className="notice">
              <Radio size={16} />
              {connection}
            </div>
          )}
          {error && (
            <div className="notice error">
              {error}
              <button onClick={() => setError("")}>Dismiss</button>
            </div>
          )}
          {s && !isHealthy && (
            <div className="notice error">
              RISK_OFF ·{" "}
              {s.health.message || "Waiting for a consistent, fresh order book"}
            </div>
          )}
          {!s ? (
            <div className="empty">
              <Activity size={38} />
              <h2>Waiting for market state</h2>
              <p>
                {mode === "live"
                  ? "Connecting to Hyperliquid perp L2/trades/context feeds."
                  : "Starting the local engine and warming up the strategy population."}
              </p>
              <p>Waiting for the Darwin backend to become healthy.</p>
            </div>
          ) : (
            <>
              {route !== "/darwin" && route !== "/factory" && <div className="metrics">
                <Metric
                  label="MARKET INTENT"
                  value={currentIntent?.replaceAll("_", " ") ?? "—"}
                  sub={`${signed(s.intent.score, 0)} / 100 · global, non calibré`}
                  color={s.intent.score >= 0 ? "positive" : "negative"}
                />
                <Metric
                  label={`${horizonLabel(horizon)} CONSENSUS`}
                  value={
                    currentHorizon?.ready
                      ? signed(currentConsensus)
                      : "Échauffement"
                  }
                  sub={`${scoped.filter((g) => g.signal > 0).length} long · ${scoped.filter((g) => g.signal < 0).length} short · ${scoped.filter((g) => g.signal === 0).length} neutral`}
                  values={s.history.map(
                    (h) => h.horizon_consensus?.[String(horizon)] ?? 0,
                  )}
                  color={currentConsensus >= 0 ? "positive" : "negative"}
                />
                <Metric
                  label="SWARM ENTROPY"
                  value={fmt(s.entropy.swarm)}
                  sub="Weighted directional disagreement"
                  values={s.history.map((h) => h.swarm_entropy)}
                  color="purple"
                />
                <Metric
                  label="EFFECTIVE STRATEGIES"
                  value={
                    s.swarm.effective === null
                      ? "Warming up"
                      : fmt(s.swarm.effective, 1)
                  }
                  sub={`${s.swarm.active} active / ${s.swarm.raw} total · all horizons`}
                  values={undefined}
                  color="blue"
                />
              </div>}
              {route === "/darwin" && <DarwinLab symbol={symbol} mode={mode} />}
              {route === "/factory" && <DarwinFactory symbol={symbol} mode={mode} />}
              {replay && (
                <Panel
                  title="Time machine"
                  label={`${frames.length} available frames`}
                >
                  <div className="replay-controls">
                    <button className="secondary" onClick={loadReplay}>
                      <RotateCcw size={15} /> Capture session
                    </button>
                    <button
                      className="primary"
                      disabled={!frames.length}
                      onClick={() => setPlaying(!playing)}
                    >
                      {playing ? <Pause size={15} /> : <Play size={15} />}{" "}
                      {playing ? "Pause" : "Play"}
                    </button>
                    <select
                      aria-label="Replay speed"
                      value={speed}
                      onChange={(e) => setSpeed(Number(e.target.value))}
                    >
                      {[1, 5, 20, 100].map((n) => (
                        <option key={n} value={n}>
                          {n}×
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label="Replay position"
                      type="range"
                      min="0"
                      max={Math.max(0, frames.length - 1)}
                      value={cursor}
                      onChange={(e) => {
                        setPlaying(false);
                        setCursor(Number(e.target.value));
                      }}
                    />
                    <span>
                      {frames.length
                        ? `${cursor + 1} / ${frames.length} · ${clock(s.timestamp)}`
                        : "Capture a session to begin"}
                    </span>
                  </div>
                  <p className="panel-note">
                    {frames.length
                      ? "REPLAY · all panels show the selected recorded state. Click a candle to seek."
                      : "Current stream shown until a replay session is captured."}
                  </p>
                </Panel>
              )}
              {(route === "/" || replay) && (
                <>
                  <div className="cockpit-grid">
                    <div className="main-column">
                      <Panel
                        title="Price & trigger zones"
                        label={
                          <span className="chart-tools">
                            <span>5s candles</span>
                            <button
                              className={vwap ? "toggle selected" : "toggle"}
                              onClick={() => setVwap(!vwap)}
                            >
                              VWAP
                            </button>
                            <span className="live-label">
                              {replay && frames.length
                                ? "REPLAY"
                                : mode === "simulation"
                                  ? "SIMULATION"
                                  : "LIVE"}
                            </span>
                          </span>
                        }
                      >
                        <div className="chart-sub">
                          <b>{symbol.slice(0, -4)} / USDT</b>
                          <span>Midpoint</span>
                          <strong>{fmt(s.features.mid)}</strong>
                          <span className="gold">— VWAP</span>
                          <span className="positive">— Trigger zones</span>
                        </div>
                        <PriceChart
                          state={s}
                          vwap={vwap}
                          onSeek={replay ? seek : undefined}
                        />
                      </Panel>
                      <Panel
                        title="Liquidity landscape"
                        label={
                          <span className="heat-legend">
                            Resting depth <i /> Low → High
                          </span>
                        }
                      >
                        <Liquidity history={s.history} />
                        <div className="legend-row">
                          <span>
                            <i className="line-key" /> Midpoint
                          </span>
                          <span>Observed top 40 levels / side</span>
                          <span className="muted">TIME × PRICE</span>
                        </div>
                      </Panel>
                    </div>
                    <div className="right-column">
                      <Panel
                        title="Order-book physics"
                        label={<Activity size={15} />}
                      >
                        <div className="physics-intro">
                          <span
                            className={`dot ${isHealthy ? "" : "amber-dot"}`}
                          />
                          {isHealthy ? "Consistent book" : "Book unavailable"}
                          <span>{s.health.age_ms ?? "—"} ms</span>
                        </div>
                        {[
                          ["Book imbalance", s.features.imbalance, ""],
                          [
                            "Weighted imbalance",
                            s.features.weighted_imbalance,
                            "",
                          ],
                          ["Microprice delta", s.features.micro_delta, " bp"],
                          ["Trade-flow imbalance", s.features.flow, ""],
                        ].map(([label, value, unit]) => (
                          <div className="physics-row" key={String(label)}>
                            <span>
                              {label}
                              <Help label={String(label)} />
                            </span>
                            <b
                              className={
                                Number(value) >= 0 ? "positive" : "negative"
                              }
                            >
                              {signed(Number(value))}
                              {unit}
                            </b>
                            <div className="bipolar">
                              <i
                                style={{
                                  left:
                                    Number(value) >= 0
                                      ? "50%"
                                      : `${50 - Math.min(Math.abs(Number(value)) * 45, 45)}%`,
                                  width: `${Math.min(Math.abs(Number(value)) * 45, 45)}%`,
                                  background:
                                    Number(value) >= 0
                                      ? "var(--green)"
                                      : "var(--red)",
                                }}
                              />
                            </div>
                          </div>
                        ))}
                        <div className="depth-summary">
                          <div>
                            <small>Bid depth</small>
                            <b className="positive">
                              {fmt(s.features.bid_depth, 1)}
                            </b>
                          </div>
                          <div>
                            <small>Ask depth</small>
                            <b className="negative">
                              {fmt(s.features.ask_depth, 1)}
                            </b>
                          </div>
                          <div>
                            <small>Trades / sec</small>
                            <b>{fmt(s.features.intensity, 1)}</b>
                          </div>
                        </div>
                      </Panel>
                      <Panel
                        title="Strategy swarm"
                        label={`${horizonLabel(horizon)} horizon`}
                      >
                        <div className="swarm-labels">
                          <span>FAMILY</span>
                          <span>SHORT / NEUTRAL / LONG</span>
                        </div>
                        {s.families.map((f) => {
                          const gs = scoped.filter((g) => g.family === f.name),
                            values = [
                              gs.filter((g) => g.signal < 0),
                              gs.filter((g) => g.signal === 0),
                              gs.filter((g) => g.signal > 0),
                            ].map((a) =>
                              a.reduce((sum, g) => sum + g.weight, 0),
                            );
                          const total = values.reduce((a, b) => a + b, 0) || 1;
                          return (
                            <button
                              className="family-row"
                              key={f.name}
                              onClick={() => {
                                setFamily(f.name);
                                navigate("/research");
                              }}
                            >
                              <span>{f.name}</span>
                              <div className="stack">
                                {values.map((v, i) => (
                                  <i
                                    key={i}
                                    style={{
                                      width: `${(v / total) * 100}%`,
                                      background: [
                                        "var(--red)",
                                        "#344354",
                                        "var(--green)",
                                      ][i],
                                    }}
                                  />
                                ))}
                              </div>
                              <ChevronRight size={12} />
                            </button>
                          );
                        })}
                        <div className="swarm-bottom">
                          <span>Correlation-adjusted support</span>
                          <span className="positive">
                            N<sub>eff</sub> {fmt(s.swarm.effective ?? 0, 1)}
                          </span>
                        </div>
                      </Panel>
                    </div>
                  </div>
                  <div className="bottom-grid">
                    <Panel title="Trigger density" label="±30 bp">
                      <div className="trigger-chart">
                        {s.triggers
                          .filter((_, i) => i % 2 === 0)
                          .reverse()
                          .map((t) => (
                            <div
                              key={t.bp}
                              title={`Opposing depth: ${fmt(t.resistance)} base units`}
                            >
                              <span>{signed(t.bp, 0)} bp</span>
                              <i
                                style={{
                                  width: `${(t.density / Math.max(...s.triggers.map((t) => t.density), 1)) * 65}%`,
                                  background:
                                    t.bp > 0 ? "var(--green)" : "var(--red)",
                                }}
                              />
                              <b>{fmt(t.density, 1)}</b>
                            </div>
                          ))}
                      </div>
                      <p className="panel-note">
                        Effective strategies changing direction
                      </p>
                    </Panel>
                    <Panel title="Entropy stack" label="NORMALIZED 0–1">
                      <div className="entropy-value">
                        {fmt(s.entropy.market)}
                        <small>Market composite</small>
                      </div>
                      <div className="entropy-spark">
                        <Spark
                          values={s.history.map((h) => h.market_entropy)}
                          color="#ad9be9"
                          height={65}
                        />
                      </div>
                      {[
                        ["Price sign", s.entropy.price],
                        ["Trade aggressor", s.entropy.trade],
                        ["Book distribution", s.entropy.book],
                      ].map(([name, n]) => (
                        <div className="entropy-row" key={String(name)}>
                          <span>{name}</span>
                          <div>
                            <i style={{ width: `${Number(n) * 100}%` }} />
                          </div>
                          <b>{fmt(Number(n))}</b>
                        </div>
                      ))}
                    </Panel>
                    <Panel title="Signal timeline" label="EXPLAINABLE">
                      <div className="timeline">
                        {s.timeline.slice(0, 5).map((t, i) => (
                          <button
                            key={`${t.time}-${i}`}
                            onClick={() => setDetail(t)}
                          >
                            <span className="timeline-node" />
                            <span className="timeline-time">
                              {clock(t.time)}
                            </span>
                            <div>
                              <b
                                className={
                                  t.state.includes("LONG")
                                    ? "positive"
                                    : t.state.includes("SHORT")
                                      ? "negative"
                                      : ""
                                }
                              >
                                {t.state.replaceAll("_", " ")}
                              </b>
                              <small>
                                {t.previous.replaceAll("_", " ")}{" "}
                                <span>→ score {signed(t.score, 0)}</span>
                              </small>
                            </div>
                            <ArrowUpRight size={14} />
                          </button>
                        ))}
                        {!s.timeline.length && (
                          <p className="panel-note">
                            Waiting for the first state transition.
                          </p>
                        )}
                      </div>
                      <button
                        className="text-button"
                        onClick={() =>
                          setDetail({
                            time: s.timestamp,
                            state: s.intent.state,
                            previous: "CURRENT STATE",
                            score: s.intent.score,
                            reasons: s.intent.reasons,
                          })
                        }
                      >
                        Inspect current intent <ArrowUpRight size={14} />
                      </button>
                    </Panel>
                  </div>
                </>
              )}
              {route === "/intent" && (
                <div className="lab-grid">
                  <Panel
                    title="Counterfactual engine"
                    label={<SlidersHorizontal size={16} />}
                  >
                    <div className="lab-content">
                      <p>
                        Re-evaluate the same signaux du marché under a nearby
                        market state.
                      </p>
                      {[
                        {
                          label: "Price move",
                          value: priceDelta,
                          set: setPriceDelta,
                          min: -30,
                          max: 30,
                          step: 1,
                          text: `${signed(priceDelta, 0)} bp`,
                        },
                        {
                          label: "Volatility multiplier",
                          value: vol,
                          set: setVol,
                          min: 0.2,
                          max: 3,
                          step: 0.1,
                          text: `${fmt(vol, 1)}×`,
                        },
                        {
                          label: "Trade-flow shift",
                          value: flow,
                          set: setFlow,
                          min: -1,
                          max: 1,
                          step: 0.05,
                          text: signed(flow),
                        },
                      ].map((c) => (
                        <label className="slider-row" key={c.label}>
                          <span>
                            {c.label}
                            <b>{c.text}</b>
                          </span>
                          <input
                            type="range"
                            min={c.min}
                            max={c.max}
                            step={c.step}
                            value={c.value}
                            onChange={(e) => c.set(Number(e.target.value))}
                          />
                        </label>
                      ))}
                      <div className="projection">
                        <span>Projected consensus</span>
                        <strong>
                          {signed(result?.base_consensus ?? currentConsensus)}{" "}
                          <span>→</span>{" "}
                          <b>
                            {result?.ready
                              ? signed(result.consensus)
                              : "Échauffement"}
                          </b>
                        </strong>
                        <small>
                          {result ? fmt(result.flips, 1) : "—"} effective
                          strategies flip
                        </small>
                      </div>
                      <p className="panel-note">
                        Sensitivity analysis, not a forecast. Recomputed from
                        the current state; probabilities are not calibrated.
                      </p>
                    </div>
                  </Panel>
                  <Panel title="Entropy phase plane" label="STATE TRAIL">
                    <Phase history={s.history} />
                    <p className="panel-note">
                      X: market entropy · Y: entropy change per second
                    </p>
                  </Panel>
                  <Panel title="Consensus by horizon" label="EFFECTIVE SUPPORT">
                    <div className="lab-content">
                      {s.cone.map((c) => (
                        <div className="cone" key={c.horizon}>
                          <b>{horizonLabel(c.horizon)}</b>
                          <div className="bipolar">
                            <i
                              style={{
                                left:
                                  c.consensus >= 0
                                    ? "50%"
                                    : `${50 + c.consensus * 50}%`,
                                width: `${Math.abs(c.consensus) * 50}%`,
                                background:
                                  c.consensus >= 0
                                    ? "var(--green)"
                                    : "var(--red)",
                              }}
                            />
                          </div>
                          <strong
                            className={
                              c.consensus >= 0 ? "positive" : "negative"
                            }
                          >
                            {c.ready ? signed(c.consensus) : `${c.remaining}s…`}
                          </strong>
                        </div>
                      ))}
                      <p className="panel-note">
                        Each horizon is evaluated independently. Global intent
                        combines all five. Les horizons incomplets restent
                        neutres.
                      </p>
                    </div>
                  </Panel>
                  <Panel
                    title="Liquidity × trigger interaction"
                    label="COUNTERFACTUAL"
                  >
                    <div className="lab-content">
                      <table>
                        <thead>
                          <tr>
                            <th>Price move</th>
                            <th>Flips, effective</th>
                            <th>Path depth</th>
                          </tr>
                        </thead>
                        <tbody>
                          {s.triggers
                            .filter((t) =>
                              [-30, -20, -10, 10, 20, 30].includes(t.bp),
                            )
                            .map((t) => (
                              <tr key={t.bp}>
                                <td
                                  className={t.bp > 0 ? "positive" : "negative"}
                                >
                                  {signed(t.bp, 0)} bp
                                </td>
                                <td>{fmt(t.density, 2)}</td>
                                <td>{fmt(t.resistance, 1)}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                      <p className="panel-note">
                        Path depth covers the observed top 40 levels only. It is
                        a lower bound beyond the visible book.
                      </p>
                    </div>
                  </Panel>
                </div>
              )}
              {route === "/research" && (
                <>
                  <div className="research-summary">
                    <BookOpen size={20} />
                    <p>
                      <b>
                        320 génomes. Huit hypothèses. Cinq horizons, jusqu’à 3
                        minutes.
                      </b>
                      <br />
                      Effective count uses the participation ratio of the
                      rolling signal correlation matrix. Constant signals are
                      excluded.
                    </p>
                    <span className="tag">120-sample window</span>
                  </div>
                  <Panel
                    title="Strategy population"
                    label={
                      <select
                        aria-label="Filter strategy family"
                        value={family}
                        onChange={(e) => setFamily(e.target.value)}
                      >
                        <option>All families</option>
                        {s.families.map((f) => (
                          <option key={f.name}>{f.name}</option>
                        ))}
                      </select>
                    }
                  >
                    <div className="table-wrap">
                      <table className="strategy-table">
                        <thead>
                          <tr>
                            <th>GENOME</th>
                            <th>FAMILY</th>
                            <th>HORIZON</th>
                            <th>SIGNAL</th>
                            <th>EFFECTIVE WEIGHT</th>
                            <th>THRESHOLD</th>
                            <th />
                          </tr>
                        </thead>
                        <tbody>
                          {scoped
                            .filter(
                              (g) =>
                                family === "All families" ||
                                g.family === family,
                            )
                            .map((g) => (
                              <tr key={g.id}>
                                <td>
                                  <button onClick={() => setDetail(g)}>
                                    {g.id}
                                  </button>
                                </td>
                                <td>{g.family}</td>
                                <td>{horizonLabel(g.horizon)}</td>
                                <td
                                  className={
                                    g.signal > 0
                                      ? "positive"
                                      : g.signal < 0
                                        ? "negative"
                                        : ""
                                  }
                                >
                                  {signed(g.signal)}{" "}
                                  {g.signal > 0
                                    ? "LONG"
                                    : g.signal < 0
                                      ? "SHORT"
                                      : "NEUTRAL"}
                                </td>
                                <td>{fmt(g.weight, 3)}</td>
                                <td>{fmt(g.threshold, 3)}</td>
                                <td>
                                  <button
                                    className="icon-button"
                                    aria-label={`Inspect ${g.id}`}
                                    onClick={() => setDetail(g)}
                                  >
                                    <ArrowUpRight size={15} />
                                  </button>
                                </td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    </div>
                  </Panel>
                </>
              )}
              {route === "/intent" && <Technical state={s} horizon={horizon} />}
              <footer>
                <span>
                  <span className={`dot ${isHealthy ? "" : "amber-dot"}`} />
                  {replay && frames.length
                    ? "RECORDED STATE"
                    : isHealthy
                      ? "STATE SYNCHRONIZED"
                      : "RISK OFF"}{" "}
                  <i /> {s.venue} <i /> {symbol}
                </span>
                <span>
                  Sequence {s.health.sequence} <i /> No order execution <i />{" "}
                  V0.11
                </span>
              </footer>
            </>
          )}
        </main>
      </div>
      {detail && (
        <div className="modal-backdrop" onClick={() => setDetail(null)}>
          <section
            className="detail-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="detail-title"
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "Escape") setDetail(null);
            }}
            tabIndex={-1}
          >
            <button
              className="close-modal icon-button"
              aria-label="Close details"
              onClick={() => setDetail(null)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">
              {"id" in detail ? "STRATEGY X-RAY" : "CAUSAL EXPLANATION"}
            </span>
            <h2 id="detail-title">
              {"id" in detail ? detail.id : detail.state.replaceAll("_", " ")}
            </h2>
            {"id" in detail ? (
              <>
                <div className="detail-grid">
                  <Metric
                    label="SIGNAL"
                    value={signed(detail.signal)}
                    sub={detail.family}
                  />
                  <Metric
                    label="WEIGHT"
                    value={fmt(detail.weight, 3)}
                    sub={`${horizonLabel(detail.horizon)} horizon`}
                  />
                </div>
                <p>
                  Uses the shared market state with a{" "}
                  <b>{fmt(detail.gain, 2)}×</b> response gain and a{" "}
                  <b>{fmt(detail.threshold, 3)}</b> neutral threshold.
                </p>
                <p>
                  Signal is tanh(feature × gain), set to neutral below the
                  threshold. Weight discounts correlated and constant signals.
                </p>
                <pre>{JSON.stringify(detail, null, 2)}</pre>
              </>
            ) : (
              <>
                <p>
                  {clock(detail.time)} · {detail.previous} → {detail.state}
                </p>
                <ul>
                  {detail.reasons.map((r) => (
                    <li key={r}>{r}</li>
                  ))}
                </ul>
                <p className="panel-note">
                  Transparent heuristic model. These factors explain the score;
                  they do not establish predictive accuracy.
                </p>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
