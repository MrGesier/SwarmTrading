import React, {useEffect, useState} from 'react';
import {API} from './api';

export function Autocorrection(){
  const [csrf,setCsrf]=useState(''),[state,setState]=useState<any>(null),[error,setError]=useState('');
  const [busy,setBusy]=useState(false),[ping,setPing]=useState<any>(null),[models,setModels]=useState<any[]>([]);
  const [provider,setProvider]=useState('codex-cli');
  const [selected,setSelected]=useState('');
  useEffect(()=>{
    let gone=false;
    const load=async()=>{try{
      const session=await fetch(`${API}/api/autocorrection/session`,{credentials:'same-origin'});
      if(!session.ok)throw Error('Démonstration accessible uniquement depuis la Factory locale.');
      const token=await session.json();
      const response=await fetch(`${API}/api/autocorrection/state`);
      if(!response.ok)throw Error('Session locale indisponible');
      const next=await response.json();if(!gone){setCsrf(token.csrf);setState(next);setError('');}
    }catch(e){if(!gone)setError(String(e));}};
    void load();const timer=setInterval(load,2500);return()=>{gone=true;clearInterval(timer)};
  },[]);
  const send=async(path:string,body?:any)=>{
    setBusy(true);setError('');try{
      const r=await fetch(`${API}/api/autocorrection/${path}`,{method:'POST',headers:{'Content-Type':'application/json','X-Darwin-Demo':csrf},body:body?JSON.stringify(body):undefined});
      if(!r.ok)throw Error(`Demande refusée (${r.status})`);
      const data=await r.json();if(path==='ping')setPing(data);
      else if(path==='provider')setState((old:any)=>({...old,...data}));
      else setState((old:any)=>({...old,jobs:[data,...(old?.jobs??[]).filter((x:any)=>x.id!==data.id)]}));
    }catch(e){setError(String(e))}finally{setBusy(false)}
  };
  const job=state?.jobs?.find((x:any)=>x.id===selected)??state?.jobs?.[0];
  const active=job&&['DETECTED','QUEUED','LLM_CONNECTED','PROPOSED','PATCHING','TESTING'].includes(job.state);
  return <section className="autocorrection-panel" aria-label="Autocorrection du code">
    <header><div><small>EXPÉRIENCE LOCALE · CODE UNIQUEMENT</small><h3>Autocorrection / Code Engineer</h3><p>Défaut contrôlé → proposition de code → tests indépendants → revue humaine.</p></div><span className={state?.worker_online?'positive':'negative'}>{state?.worker_online?'Worker local connecté':'Worker arrêté'}</span></header>
    <div className="autocorrection-controls">
      <label>Ingénieur <select aria-label="Fournisseur de la démonstration" value={provider} onChange={e=>setProvider(e.target.value)}><option value="codex-cli">Codex CLI · abonnement ChatGPT</option><option value="mock">Mock · aucun LLM</option></select></label>
      <button disabled={busy||active||!csrf||!state?.worker_online} onClick={()=>void send('demo',{provider})}>Démonstration contrôlée</button>
    </div>
    {!state?.worker_online&&<p>Démarre <b>Demarrer-Darwin-Demo.cmd</b> pour connecter le worker. Une seule tâche et un seul candidat à la fois.</p>}
    <details><summary>Agents de recherche · OpenRouter gratuit</summary>
      <p>{state?.openrouter?.configured?'Clé configurée · connexion à tester':'Fournisseur non connecté · OPENROUTER_API_KEY absent'}. Budget partagé : {state?.openrouter?.budget?.remaining??'—'} / 20 tentatives restantes sur 24 h.</p>
      <button disabled={busy||!csrf} onClick={()=>void send('ping')}>Tester un véritable appel</button>{' '}
      <button onClick={()=>void fetch(`${API}/api/autocorrection/models`).then(r=>r.json()).then(x=>setModels(x.models??[])).catch(()=>setError('Catalogue indisponible'))}>Vérifier les modèles gratuits</button>
      {models.length>0&&<p>Catalogue vérifié : {models.slice(0,5).map(m=>m.id).join(' · ')}. OPENROUTER_FREE_MODEL permet d’en sélectionner un ; sinon sélection automatique dans le catalogue.</p>}
      <label>Fournisseur des agents <select aria-label="Fournisseur des agents de recherche" value={state?.selected_provider??'deterministic'} disabled={busy||!csrf} onChange={e=>void send('provider',{provider:e.target.value})}><option value="openai" disabled>OpenAI historique</option><option value="deterministic">Déterministe · sans LLM</option><option value="openrouter-free">OpenRouter gratuit</option><option value="ollama">Ollama · non installé</option></select></label><p>Le choix est conservé localement. Ollama est réservé à une étape ultérieure et n’est pas installé. FORGE, JUDGE numérique, CERBERUS et HERMES restent déterministes.</p>
      {ping&&<pre>{JSON.stringify(ping,null,2)}</pre>}
    </details>
    {error&&<p role="alert">{error}</p>}
    {state?.jobs?.length>1&&<label>Expérience <select aria-label="Expérience à examiner" value={job?.id??''} onChange={e=>setSelected(e.target.value)}>{state.jobs.map((j:any)=><option key={j.id} value={j.id}>{new Date(j.created_at*1000).toLocaleTimeString()} · {j.provider} · {j.state}</option>)}</select></label>}
    {job&&<article>
      <div className="autocorrection-status"><b>{job.state}</b><span>{job.provider} · {job.model??'modèle en attente'} · {job.real_call?'réponse LLM réelle vérifiée':'aucune réponse LLM réelle vérifiée'}</span></div>
      <p>{job.evidence}</p><p>{job.hypothesis??job.reason}</p>
      <ol className="autocorrection-history">{job.history.map((h:any,i:number)=><li key={i}>{h.state}<small>{new Date(h.ts*1000).toLocaleTimeString()}</small></li>)}</ol>
      {job.base_sha&&<p>Base du défaut : <code>{job.base_sha.slice(0,12)}</code> · Candidat : <code>{job.candidate_sha?.slice(0,12)??'en attente'}</code></p>}
      {job.checks?.length>0&&<table><thead><tr><th>Vérification</th><th>Code de sortie</th><th>Durée</th></tr></thead><tbody>{job.checks.map((c:any,i:number)=><tr key={i}><td><details><summary>{c.name}</summary><pre>{c.output}</pre><code>{c.command.join(' ')}</code></details></td><td>{c.exit_code}{c.name==='defect reproduction'?' (échec attendu)':''}</td><td>{c.seconds}s</td></tr>)}</tbody></table>}
      {job.diff&&<details open><summary>Diff réel · {job.files.join(', ')}</summary><pre>{job.diff}</pre></details>}
      {job.reason&&<p>{job.reason}</p>}
      <a href={`${API}/api/autocorrection/proposal/${job.id}`} target="_blank" rel="noreferrer">Ouvrir la proposition et ses preuves</a>
      <p>Aucun code généré n’est intégré au moteur courant. Aucun ordre réel. La réussite des tests ne démontre pas une amélioration du rendement.</p>
    </article>}
    {!job&&<p>Aucune expérience lancée. La démonstration modifie uniquement un outil de présentation dans un worktree jetable.</p>}
  </section>
}
