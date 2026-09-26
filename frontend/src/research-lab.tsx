import React from 'react';
import {Help} from './help';
import {StrategyName} from './strategy-name';
const number=(v:any)=>v!=null&&Number.isFinite(Number(v))?Number(v).toFixed(2):'—';
export function ResearchLabPanel({lab}:{lab:any}){
 if(!lab)return null;
 const reports=(lab.records??[]).filter((r:any)=>r.kind==='epoch_report');
 const batches=(lab.records??[]).filter((r:any)=>r.kind==='batch');
 const comparisons=(lab.records??[]).filter((r:any)=>r.kind==='ablation');
 return <section className="research-activity" aria-label="Bilan automatique de recherche">
  <header><div><span className="factory-eyebrow">BILAN DES DERNIÈRES 24 HEURES</span><h3>Ce que Darwin a appris <Help label="Bilan de recherche" text="Bilan calculé à partir des expériences conservées. Une nouvelle variante, une réponse LLM ou un test réussi ne prouvent pas une amélioration. Les comparaisons attendent assez de données."/></h3></div><strong>{lab.summary?.batches??0} lots · {lab.summary?.comparisons??0} comparaisons · {lab.summary?.reports??0} cycles</strong></header>
  <p>Un dossier de questions au maximum toutes les deux heures par marché, seulement si les données ont changé. La collecte et les tests paper continuent entre les appels.</p>
  <h4>Questions regroupées et réponses</h4>{!batches.length&&<p>En attente du premier lot avec assez de données nouvelles.</p>}
  {batches.slice(0,6).map((r:any)=><details key={r.id}><summary>{new Date(r.ts*1000).toLocaleString()} · {r.ok?'Réponse exploitable':'Repli déterministe'} · {r.audit?.provider_status}</summary><p>{r.summary}</p><p>{r.error}</p><pre>{JSON.stringify(r.plans,null,2)}</pre></details>)}
  <h4>Avec / sans indicateur · fenêtres communes <Help label="Comparaisons d’indicateurs" text="Comptes indépendants, mêmes carnets Hyperliquid et frais. Signal neutralisé : imbalance, flux ou microprice. Le filtre de spread compare la politique habituelle à un blocage au-delà de 2 bp. Ce sont des interventions de recherche isolées, sans promotion automatique."/></h4>
  {(lab.active_ablations??[]).map((p:any)=><div key={p.feature}><b>{p.feature}</b> · collecte en cours · <StrategyName id={p.parent_id}/><p>Témoin : {number(p.control?.pnl)} USD · variante : {number(p.variant?.pnl)} USD · clôtures {p.control?.closed_trades??0} / {p.variant?.closed_trades??0}</p></div>)}
  {comparisons.slice(0,8).map((r:any)=><details key={r.id}><summary>{r.feature} · Δ net {number(r.delta_net_usd)} USD · {r.status}</summary><p>Du {new Date(r.start*1000).toLocaleString()} au {new Date(r.end*1000).toLocaleString()}</p><p>Frais : {number(r.control?.fees)} / {number(r.variant?.fees)} USD. Trades : {r.control?.closed_trades} / {r.variant?.closed_trades}.</p><p>{r.interpretation}</p></details>)}
  <h4>Décisions et prochaines expériences</h4>{reports.slice(0,4).map((r:any)=><details key={r.id}><summary>Cycle {r.epoch_id} · {r.created} variantes créées · {r.retired} retirées · {r.resolved} comparaisons traitées</summary><p>Diagnostic : {r.incident?.code??'Aucun incident'}</p><p>Comparaison G0 / descendants : {r.comparison?.status??'En attente'} · {number(r.comparison?.g0_mean_return_bps)} / {number(r.comparison?.descendant_mean_return_bps)} bp nets. Incertitude non estimée.</p><pre>{JSON.stringify(r.next_experiments,null,2)}</pre></details>)}
  <p>Prochaine étape : collecter les observations suivantes, comparer les variantes, puis regrouper les nouvelles questions. Un incident persistant peut déclencher une proposition Codex isolée ; son état et ses tests apparaissent dans Autocorrection.</p>
 </section>;
}
