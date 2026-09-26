import { useState } from "react";
import { LineChart, fmt, signed } from "./charts";
import { StrategyName } from "./strategy-name";
export type SharedPortfolioState = {
 initial_eur:number;equity_eur:number;pnl_eur:number;cash_eur:number;available_eur:number;margin_eur:number;gross_exposure_eur:number;net_exposure_eur:number;leverage:number;max_leverage:number;fees_eur:number;funding_eur:number;funding_unobserved_seconds:number;closed_count:number;status:string;error:string;pair_status:string;gamma_status:string;
 fx:{usd_per_eur:number;date:string}|null;
 positions:Array<{id:number;strategy_id:string;kind:string;opened_at:number;net_eur:number;fresh:boolean;delta_units:number|null;legs:Array<{instrument:string;kind:string;qty:number;entry:number;mark:number;marked_at:number}>}>;
 closed:Array<{id:number;strategy_id:string;kind:string;net_eur:number;fees_eur:number;closed_at:number;reason:string}>;
 history:Array<{ts:number;equity_eur:number}>;
};
export function SharedPortfolioPanel({p}:{p:SharedPortfolioState}) {
 const [showHistory,setShowHistory]=useState(false);
 return <section className="darwin-card shared-portfolio" aria-label="Portefeuille commun Darwin">
  <div className="darwin-card-head"><h3>Mon portefeuille Darwin</h3><span>Hyperliquid · PAPER · EUR</span></div>
  <p>Un seul capital partagé entre toutes les stratégies et tous les marchés. Conservé entre les cycles et les redémarrages.</p>
  {p.error&&<p role="alert">{p.error}</p>}
  <div className="darwin-kpis">
   <div><small>CAPITAL INITIAL</small><b>{fmt(p.initial_eur)} €</b><span>Démarrage de ce portefeuille</span></div>
   <div><small>VALEUR ACTUELLE</small><b>{fmt(p.equity_eur)} €</b><span className={p.pnl_eur>=0?"positive":"negative"}>{signed(p.pnl_eur)} € · {signed(p.pnl_eur/p.initial_eur*100)} %</span></div>
   <div><small>POSITIONS EN COURS</small><b>{p.positions.length}</b><span>{p.positions.reduce((n,x)=>n+x.legs.length,0)} jambes · {p.closed_count} positions clôturées</span></div>
   <div><small>LEVIER BRUT / LIMITE</small><b>{fmt(p.leverage)}× / 3×</b><span>{fmt(p.gross_exposure_eur)} € exposés · {fmt(Math.max(0,p.available_eur))} € disponibles</span></div>
  </div>
  <p className="panel-note">Frais déduits : {fmt(p.fees_eur)} € · funding estimé : {signed(p.funding_eur)} €. {p.positions.some(x=>!x.fresh)&&<strong>Valorisations périmées : attente des carnets ; aucune exécution sur ces données.</strong>}</p>
  <button className="toggle" onClick={()=>setShowHistory(!showHistory)}>{showHistory?"Masquer":"Voir"} l’évolution du capital</button>
  {showHistory&&<LineChart label="Capital commun · EUR" values={p.history.map(x=>x.equity_eur)} times={p.history.map(x=>x.ts)} color="#edb18b"/>}
  <div className="darwin-table-wrap"><table className="darwin-table"><thead><tr><th>Stratégie</th><th>Instrument / sens</th><th>Depuis</th><th>PnL net €</th></tr></thead><tbody>{p.positions.map(x=><tr key={x.id}><td>{x.kind==="delta_neutral"?"Delta neutral HYPE":<StrategyName id={x.strategy_id}/>}</td><td>{x.legs.map(l=><div key={l.instrument}>{l.kind==="spot"?"Spot HYPE/USDC":l.instrument.replace("perp:","Perp ")} · {l.qty>0?"LONG":"SHORT"} · {fmt(Math.abs(l.qty),6)}</div>)}{x.delta_units!==null&&<small>Delta quantité : {fmt(x.delta_units,6)} HYPE</small>}</td><td>{new Date(x.opened_at*1000).toLocaleTimeString()}</td><td>{signed(x.net_eur)}{!x.fresh&&" · ancien prix"}</td></tr>)}</tbody></table></div>
  {!p.positions.length&&<p className="panel-note">Aucune position ouverte. Les stratégies attendent un signal admissible et du capital disponible.</p>}
  <p className="panel-note">{p.pair_status}</p>
  <details><summary>Comprendre le capital, les frais et les couvertures</summary><p>Le spot est payé comptant ; les perps réservent une marge à 3×. La somme brute des jambes est plafonnée à trois fois la valeur du portefeuille à l’entrée. Un dépassement par mouvement de marché déclenche une tentative de réduction sur carnet frais. Les stratégies sur un même perp sont des allocations virtuelles ; leur exposition exchange serait nette, sans mode hedge par stratégie.</p><p>Au plus 18 allocations directionnelles (100 € chacune au départ) et une paire couverte (250 € par jambe au départ). Les entrées peuvent attendre ; aucune performance positive n’est garantie. Frais taker modélisés : 4,5 bp par fill perp, 7 bp spot, sans réduction de compte. Les deux carnets doivent permettre la quantité entière ; la paire est atomique dans le paper uniquement. Risque de jambe, latence, liquidation et impact réel ne sont pas reproduits.</p><p>Change BCE figé à l’initialisation : {p.fx?`1 EUR = ${p.fx.usd_per_eur} USD (${p.fx.date})`:"en attente"}. USDC/USD supposés à parité ; ce suivi n’est pas un relevé de wallet. Funding proratisé à partir du taux horaire observé, pas un règlement exact de l’exchange. Temps non couvert par ce modèle : {fmt(p.funding_unobserved_seconds,0)} secondes-position.</p><p>La paire spot long / perp short neutralise la quantité de HYPE, pas le risque de basis ni tous les autres risques. Gamma : {p.gamma_status}.</p></details>
  <details><summary>Journal du portefeuille · {p.closed_count} clôtures</summary><div className="darwin-table-wrap"><table className="darwin-table"><thead><tr><th>Clôture</th><th>Stratégie</th><th>Net €</th><th>Frais €</th><th>Motif</th></tr></thead><tbody>{[...p.closed].reverse().map(x=><tr key={x.id}><td>{new Date(x.closed_at*1000).toLocaleString()}</td><td><StrategyName id={x.strategy_id}/></td><td>{signed(x.net_eur)}</td><td>{fmt(x.fees_eur)}</td><td>{x.reason}</td></tr>)}</tbody></table></div></details>
 </section>;
}
