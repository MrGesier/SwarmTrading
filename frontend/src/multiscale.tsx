import type {State,Candle} from './types';
import {Help} from './help';
import {fmt,signed,clock} from './charts';

export type Horizon={timestamp:number;horizon_s:number;ready:boolean;features:Record<string,number|boolean>;
 swarm:State['swarm']&{entropy:number};entropy:State['entropy'];intent:State['intent']&{direction:string;entry:string;invalidation:string;p_long:null;p_short:null;p_no_trade:null};triggers:State['triggers'];timeline:State['timeline']};
export type Term={alignment:number;sign_changes:number;slope:number;curvature:number;front_direction:string;front_horizon:number|null;front_velocity:number};
export const duration=(h:number)=>h>=60?`${h/60} min`:`${h} s`;

export function aggregateCandles(candles:Candle[],interval:number):Candle[]{
 const result:Candle[]=[];
 for(const c of candles){const bucket=Math.floor(c.time/interval)*interval;const last=result.at(-1);if(last?.time===bucket){last.high=Math.max(last.high,c.high);last.low=Math.min(last.low,c.low);last.close=c.close;last.volume+=c.volume}else result.push({...c,time:bucket})}
 return result;
}

export function MultiScale({state,horizon,context}:{state:State;horizon:number;context:string}){
 const local=state.horizons?.[String(horizon)];if(!local)return null;
 const keys=Object.keys(state.horizons!).map(Number).sort((a,b)=>a-b);
 const parent=context==='auto'?keys.find(h=>h>horizon):Number(context);
 const parentState=parent?state.horizons?.[String(parent)]:undefined;
 const term=state.term_structure!;
 const frames=state.history.slice(-90);
 return <section className="panel multiscale-panel"><div className="panel-head"><h2>Propagation multi-horizon <Help label="Propagation" text="Chaque ligne représente un horizon, chaque colonne un instant passé. Vert : consensus acheteur ; rose : vendeur ; gris : échauffement. Le front est le plus long horizon contigu partageant le signe du plus court horizon prêt, avec une zone neutre de ±0,1. Il décrit une structure observée, pas une causalité démontrée."/></h2><span>ÉTATS LOCAUX · NON CALIBRÉS</span></div><div className="multiscale-body"><div className="propagation-chart">{keys.map(h=><div className="propagation-row" key={h}><b>{duration(h)}</b><div>{frames.map((f,i)=>{const value=f.horizon_consensus?.[String(h)]??0;const ready=f.horizon_metrics?.[String(h)]?.ready;return <span key={i} title={`${clock(f.time)} · ${duration(h)} · ${ready?signed(value):'Échauffement'}`} style={{background:!ready?'#293540':value>=0?`rgba(89,221,178,${.12+Math.abs(value)*.8})`:`rgba(237,125,139,${.12+Math.abs(value)*.8})`}}/>})}</div><strong>{state.horizons![String(h)].ready?signed(state.horizons![String(h)].swarm.consensus):'…'}</strong></div>)}<div className="propagation-times"><span>{frames.length?clock(frames[0].time):'—'}</span><span>MAINTENANT</span></div></div><div className="direction-card"><span className="eyebrow">THÈSE {duration(horizon)} / ENTRÉE {duration(Math.min(5,horizon))}</span><strong className={local.intent.direction==='LONG'?'positive':local.intent.direction==='SHORT'?'negative':''}>{local.intent.state.replaceAll('_',' ')}</strong><p>{local.intent.entry==='FAVORABLE'?'Pression courte alignée avec le biais local.':'Attendre : le contexte court ne confirme pas une entrée.'}</p><small>Probabilités : non calibrées · aucun ordre envoyé</small><div className="context-line">Contexte {parent?duration(parent):'aucun parent disponible'} : <b>{parentState?.ready?signed(parentState.swarm.consensus):parentState?'échauffement':'—'}</b></div></div></div><div className="multiscale-stats"><span>Front <b>{term.front_direction} {term.front_horizon?`→ ${duration(term.front_horizon)}`:''}</b></span><span>Changements de signe <b>{term.sign_changes}</b></span><span>Alignement <b>{fmt(term.alignment*100,0)} %</b></span><span>Pression haussière locale <b>{fmt(Number(local.features.bullish_pressure_duty_cycle)*100,0)} % du temps</b></span><span>OFI normalisé <b>{signed(Number(local.features.ofi_normalized))}</b></span></div><p className="panel-note">{local.intent.invalidation} Le contexte est affiché séparément ; il ne modifie pas le score local.</p></section>
}
