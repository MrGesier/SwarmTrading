import { useEffect, useState } from "react";
import type { State } from "./types";
import { Help } from "./help";
import { fmt, signed, clock } from "./charts";
import { API } from "./api";

type Cell = { bp: number; vol: number; consensus: number; flips: number };
type Analysis = {
  timestamp: number;
  horizon: number;
  ready: boolean;
  baseline: number;
  surface: Cell[][];
  fragility: { bp: number; consensus: number } | null;
  fragility_status: string;
};
type Cost = {
  timestamp: number;
  rows: {
    side: string;
    filled: number;
    fill_ratio: number;
    complete: boolean;
    vwap: number | null;
    impact_bps: number | null;
    fee_bps: number;
    total_bps: number | null;
  }[];
};
function Block({
  title,
  label,
  children,
}: {
  title: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>
          {title}
          <Help label={title} />
        </h2>
        <span>{label}</span>
      </div>
      {children}
    </section>
  );
}
export function Technical({
  state,
  horizon,
}: {
  state: State;
  horizon: number;
}) {
  const [analysis, setAnalysis] = useState<Analysis | null>(null),
    [cost, setCost] = useState<Cost | null>(null),
    [notional, setNotional] = useState(10000),
    [fee, setFee] = useState(10),
    [error, setError] = useState("");
  const [cell, setCell] = useState<Cell | null>(null);
  const [surfaceZoom, setSurfaceZoom] = useState(1);
  const symbol = state.symbol,
    mode = state.mode,
    tick = Math.floor(state.timestamp / 2);
  useEffect(() => {
    setAnalysis(null);
    setCost(null);
    setCell(null);
  }, [symbol, mode, horizon]);
  useEffect(() => setCost(null), [notional, fee]);
  useEffect(() => {
    const abort = new AbortController();
    async function fetchAnalysis() {
      try {
        const r = await fetch(
          `${API}/api/analysis?symbol=${symbol}&mode=${mode}&horizon=${horizon}`,
          { signal: abort.signal },
        );
        if (!r.ok) throw new Error("Analyse en attente du moteur.");
        const value = await r.json();
        if (!abort.signal.aborted) {
          setAnalysis(value);
          setError("");
        }
      } catch (e) {
        if (!abort.signal.aborted) setError(String(e));
      }
    }
    void fetchAnalysis();
    return () => abort.abort();
  }, [symbol, mode, horizon, tick]);
  useEffect(() => {
    const abort = new AbortController();
    async function fetchCost() {
      try {
        const r = await fetch(`${API}/api/cost-preview`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ symbol, mode, notional, fee_bps: fee }),
          signal: abort.signal,
        });
        if (!r.ok) throw new Error("Coût indisponible : carnet frais requis.");
        const value = await r.json();
        if (!abort.signal.aborted) setCost(value);
      } catch (e) {
        if (!abort.signal.aborted) setError(String(e));
      }
    }
    void fetchCost();
    return () => abort.abort();
  }, [symbol, mode, notional, fee, tick]);
  const fresh =
    state.health.status === "HEALTHY" &&
    Date.now() / 1000 - state.timestamp < 4;
  const ready = !!analysis?.ready && fresh;
  return (
    <div className="technical-section">
      <div className="technical-heading">
        <div>
          <span className="eyebrow">STRUCTURE → SENSIBILITÉ → COÛT</span>
          <h2>Analyse avancée</h2>
        </div>
        <span>
          {horizon >= 60 ? `${horizon / 60} min` : `${horizon} s`} ·{" "}
          {analysis ? clock(analysis.timestamp) : "—"}
        </span>
      </div>
      {error && <p className="panel-note negative">{error}</p>}
      <div className="lab-grid">
        <Block title="Trigger surface" label="PRIX × VOLATILITÉ">
          <div className="plot-toolbar surface-toolbar"><label>Zoom de la matrice<input type="range" aria-label="Zoom de la matrice de déclenchement" min="0.75" max="1.5" step="0.25" value={surfaceZoom} onChange={e=>setSurfaceZoom(Number(e.target.value))}/>{surfaceZoom}×</label><span>Instantané · pas un axe temporel</span></div>
          <div className="surface-content">
            {!ready ? (
              <p className="panel-note">
                {fresh
                  ? "Échauffement de cet horizon : les scénarios attendent un historique complet."
                  : "RISK_OFF · données fraîches requises."}
              </p>
            ) : (
              <>
                <div className="surface-grid" style={{minWidth:480*surfaceZoom, fontSize:11*surfaceZoom}}>
                  <span className="surface-axis">Vol. / Prix</span>
                  {analysis.surface[0].map((c) => (
                    <span className="surface-axis" key={c.bp}>
                      {signed(c.bp, 0)}
                    </span>
                  ))}
                  {analysis.surface.map((row) => (
                    <div className="surface-row" key={row[0].vol}>
                      <span className="surface-axis">{row[0].vol}×</span>
                      {row.map((c) => (
                        <button
                          key={c.bp}
                          className="surface-cell"
                          onMouseEnter={() => setCell(c)}
                          onFocus={() => setCell(c)}
                          onClick={() => setCell(c)}
                          aria-label={`${signed(c.bp, 0)} bp, volatilité ${c.vol} fois, consensus ${signed(c.consensus)}`}
                          style={{
                            background:
                              c.consensus >= 0
                                ? `rgba(89,221,178,${0.09 + Math.abs(c.consensus) * 0.65})`
                                : `rgba(237,125,139,${0.09 + Math.abs(c.consensus) * 0.65})`,
                          }}
                        >
                          {signed(c.consensus, 1)}
                        </button>
                      ))}
                    </div>
                  ))}
                </div>
                <p className="surface-detail">
                  {cell ? (
                    <>
                      {signed(cell.bp, 0)} bp · volatilité {cell.vol}× ·{" "}
                      <b>{fmt(cell.flips, 2)} effectives changent de signe</b>
                    </>
                  ) : (
                    "Survolez ou sélectionnez une case pour inspecter les bascules."
                  )}
                </p>
              </>
            )}
            <p className="panel-note">
              Colonnes en points de base. Carnet et flux maintenus constants.
            </p>
          </div>
        </Block>
        <Block title="Consensus fragility" label="TEST D’INVALIDATION">
          <div className="fragility-content">
            <span className="eyebrow">MOUVEMENT CONTRAIRE MINIMAL</span>
            <strong
              className={
                analysis?.fragility && Math.abs(analysis.fragility.bp) <= 5
                  ? "negative"
                  : "positive"
              }
            >
              {!ready
                ? "En attente"
                : analysis?.fragility
                  ? `${signed(analysis.fragility.bp, 0)} bp`
                  : analysis?.fragility_status === "NEUTRAL"
                    ? "Neutre"
                    : "> 50 bp"}
            </strong>
            <p>
              {!ready
                ? "Les données doivent couvrir l’horizon sélectionné."
                : analysis?.fragility
                  ? "À ce niveau, le consensus pondéré change de signe, toutes choses égales par ailleurs."
                  : analysis?.fragility_status === "NEUTRAL"
                    ? "Le consensus est trop proche de zéro pour définir une direction à invalider."
                    : "Aucune inversion trouvée dans la plage testée. Cela ne signifie pas que le consensus est robuste à d’autres changements."}
            </p>
            <div className="fragility-comparison">
              <span>
                Consensus actuel{" "}
                <b>{analysis ? signed(analysis.baseline) : "—"}</b>
              </span>
              <span>
                Après perturbation{" "}
                <b>
                  {analysis?.fragility
                    ? signed(analysis.fragility.consensus)
                    : "—"}
                </b>
              </span>
            </div>
            <small>Recherche par pas de 1 bp · pas un niveau de stop</small>
          </div>
        </Block>
        <Block title="Execution cost preview" label="AUCUN ORDRE ENVOYÉ">
          <div className="cost-controls">
            <label>
              Montant USDT
              <select
                aria-label="Montant simulé en USDT"
                value={notional}
                onChange={(e) => setNotional(Number(e.target.value))}
              >
                {[1000, 10000, 50000, 100000, 250000, 1000000].map((n) => (
                  <option key={n} value={n}>
                    {fmt(n, 0)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Frais par côté (bp)
              <input
                type="number"
                aria-label="Frais par côté en points de base"
                min="0"
                max="100"
                step=".5"
                value={fee}
                onChange={(e) =>
                  setFee(Math.min(100, Math.max(0, Number(e.target.value))))
                }
              />
            </label>
          </div>
          <div className="cost-results">
            {fresh && cost ? (
              cost.rows.map((r) => (
                <div className="cost-side" key={r.side}>
                  <span className={r.side === "BUY" ? "positive" : "negative"}>
                    {r.side === "BUY" ? "ACHAT" : "VENTE"}
                  </span>
                  <strong>
                    {r.total_bps === null ? "—" : fmt(r.total_bps)}{" "}
                    <small>bp</small>
                  </strong>
                  <span>Coût indicatif par côté</span>
                  <dl>
                    <dt>Prix moyen</dt>
                    <dd>{r.vwap === null ? "—" : fmt(r.vwap)}</dd>
                    <dt>Spread + profondeur</dt>
                    <dd>
                      {r.impact_bps === null ? "—" : fmt(r.impact_bps)} bp
                    </dd>
                    <dt>Remplissage visible</dt>
                    <dd className={r.complete ? "positive" : "negative"}>
                      {fmt(r.fill_ratio * 100, 1)} %
                    </dd>
                  </dl>
                  {!r.complete && (
                    <b className="partial-warning">PROFONDEUR INSUFFISANTE</b>
                  )}
                </div>
              ))
            ) : (
              <p className="panel-note">Calcul sur carnet frais en cours…</p>
            )}
          </div>
          <p className="panel-note">
            Frais configurables : 10 bp par défaut, à adapter à votre compte.
            Coût hors latence et sélection adverse. Ce n’est pas une estimation
            de rendement.
          </p>
        </Block>
        <Block title="Visible liquidity" label="40 NIVEAUX / CÔTÉ">
          <div className="liquidity-metrics">
            {[
              [
                "Concentration bid · top 5",
                state.features.bid_concentration * 100,
                "%",
              ],
              [
                "Concentration ask · top 5",
                state.features.ask_concentration * 100,
                "%",
              ],
              ["Plus grand vide au-dessus", state.features.vacuum_up, "bp"],
              ["Plus grand vide en dessous", state.features.vacuum_down, "bp"],
            ].map(([name, value, unit]) => (
              <div key={String(name)}>
                <span>{name}</span>
                <b>
                  {fmt(Number(value), 2)} <small>{unit}</small>
                </b>
              </div>
            ))}
          </div>
          <p className="panel-note">
            Une forte concentration peut signaler une barrière locale. Un écart
            entre deux niveaux peut faciliter un mouvement, sans garantir qu’il
            se produira.
          </p>
        </Block>
      </div>
    </div>
  );
}
