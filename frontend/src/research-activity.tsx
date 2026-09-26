import React, {useEffect,useMemo,useState} from "react";
import {API} from "./api";
import {Help} from "./help";
import {StrategyName} from "./strategy-name";
type Run={id:number;ts:number;agent_id:string;model:string;ok:boolean;latency_ms:number;error?:string;payload?:Record<string,unknown>;audit?:{task?:string;context_preview?:string;provider_status?:string;real_call?:boolean|null}};
const kind=(r:Run)=>r.audit?.provider_status==="cached"?"Cache":r.audit?.real_call===true?(r.ok?"LLM réel":"Appel LLM échoué"):r.audit?.provider_status==="deterministic"?"Déterministe":r.audit?.provider_status?"Repli / indisponible":"Historique non instrumenté";
export function ResearchActivity({runs,experiments,cycle,symbol,mode,events}:{runs:Run[];experiments:any[];cycle:any;symbol:string;mode:string;events:any[]}){
 const [older,setOlder]=useState<Run[]>([]),[filter,setFilter]=useState("Tous"),[busy,setBusy]=useState(false),[error,setError]=useState(""),[end,setEnd]=useState(false);
 useEffect(()=>{setOlder([]);setEnd(false);setError("");},[symbol,mode]);
 const rows=useMemo(()=>Array.from(new Map([...older,...runs].map(r=>[r.id,r])).values()).sort((a,b)=>b.id-a.id),[runs,older]);
 async function loadOlder(){setBusy(true);setError("");try{const id=rows.at(-1)?.id;const r=await fetch(`${API}/api/darwin/agent-runs?symbol=${symbol}&mode=${mode}${id?`&before_id=${id}`:""}`);if(!r.ok)throw Error();const d=await r.json();setOlder(old=>[...old,...d.runs]);setEnd(d.next_before_id===null);}catch{setError("Historique indisponible. Réessaie.");}finally{setBusy(false);}}
 const active=new Map<string,string>();for(const e of events){if(e.type==="agent_started"||e.type==="agent_finished")active.set(e.agent_id,e.type);}
 const thinking=cycle?.status==="RESEARCH_RUNNING"?[...active].filter(([,v])=>v==="agent_started").map(([k])=>k.toUpperCase()):[];
 const mutations=new Map<string,any>();for(const e of events){if(e.type==="mutation_created")for(const child of e.payload?.children??[])mutations.set(child.id,child.mutation);}
 const visible=rows.filter(r=>filter==="Tous"||(filter==="LLM"?r.audit?.real_call===true:filter==="Cache"?kind(r)==="Cache":kind(r)==="Repli / indisponible"));
 return <section className="research-activity" aria-label="Journal de la boucle récursive">
  <header><div><span className="factory-eyebrow">OBSERVER → QUESTIONNER → MUTER → ÉVALUER</span><h3>Ce que Darwin est en train de faire <Help label="Boucle récursive" text="Chaque cycle utilise les résultats de la fenêtre précédente pour proposer une mutation bornée. Les résultats des descendants alimentent le cycle suivant. Cela ne garantit pas une amélioration et ne réécrit pas automatiquement le code."/></h3></div><strong>{thinking.length?`${thinking.join(", ")} · analyse en cours`:cycle?.status==="RESEARCH_RUNNING"?"Cycle en cours":"Collecte paper en cours"}</strong></header>
  <p>{runs.filter(r=>r.audit?.real_call===true).length} appels réseau LLM vérifiés parmi les {runs.length} derniers résultats. Un résultat en cache ou déterministe n’est pas un nouvel appel LLM.</p>
  <div className="activity-filters">{["Tous","LLM","Cache","Repli"].map(f=><button key={f} aria-pressed={f===filter} onClick={()=>setFilter(f)}>{f}</button>)}</div>
  <div className="research-runs">{visible.map(r=><details key={r.id}><summary><b>{r.agent_id.toUpperCase()}</b><span className="run-kind">{kind(r)}</span><time>{new Date(r.ts*1000).toLocaleString("fr-FR")}</time><span>{r.model} · {r.latency_ms} ms</span></summary>
   <p><b>Question préparée :</b> {r.audit?.task??"Non conservée pour cet ancien appel."}</p>
   {r.audit?.real_call===false&&<p>Aucun nouvel envoi réseau pour ce résultat.</p>}
   {r.error&&<p className="negative">{r.error}</p>}
   <h4>Réponse / proposition</h4><pre>{JSON.stringify(r.payload??{},null,2)}</pre>
   <details><summary>Contexte préparé pour le fournisseur (aperçu limité)</summary><pre>{r.audit?.context_preview??"Non conservé pour cet ancien appel."}</pre></details>
   <p>Cette réponse est un avis. Les mutations appliquées et leur verdict figurent ci-dessous ; les calculs et contrôles restent déterministes.</p>
  </details>)}</div>{!visible.length&&<p>Aucun résultat dans ce filtre. Les nouveaux appels apparaîtront automatiquement.</p>}
  {!end&&<button disabled={busy} onClick={()=>void loadOlder()}>{busy?"Chargement…":"Voir les appels plus anciens"}</button>}{error&&<p role="alert">{error}</p>}
  <h4>Mutations en cours et décisions <Help label="Mutation" text="Une modification d’un seul paramètre est proposée puis comparée au parent. RUNNING attend des observations ; RESOLVED signifie que la comparaison a été traitée, pas que le descendant gagne de l’argent."/></h4>
  <div className="mutation-ledger">{experiments.map(e=><details key={e.id}><summary>Expérience #{e.id} · {e.parameter} × {(e.factors??[]).join(" / ")} · {e.status}</summary><p><StrategyName id={e.parent_id}/></p><p>{e.hypothesis}</p><p>{e.rationale}</p><p>Descendants : {(e.child_ids??[]).map((id:string)=><span key={id}><StrategyName id={id}/>{mutations.has(id)?` : ${mutations.get(id).from} → ${mutations.get(id).to}`:""}{" "}</span>)}</p><p>Gagnant : <StrategyName id={e.winner_id}/></p><pre>{JSON.stringify(e.result??{},null,2)}</pre></details>)}</div>
  <p>Programmation : les propositions de code et leurs tests restent dans le panneau Autocorrection. Aucune intégration automatique.</p>
 </section>;
}
