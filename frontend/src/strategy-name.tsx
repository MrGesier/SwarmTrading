import React from "react";
export function shortStrategy(id?:string|null){
 if(!id)return "Aucune";
 const base=id.split("__")[0], family=base.replace(/_\d.*$/,"").replaceAll("_"," ");
 const generations=[...id.matchAll(/__g(\d+)_/g)], generation=generations.length?generations[generations.length-1][1]:"0";
 let hash=2166136261;for(const c of id)hash=Math.imul(hash^c.charCodeAt(0),16777619);
 return `${family.charAt(0).toUpperCase()+family.slice(1)} · G${generation} · ${(hash>>>0).toString(16).padStart(8,"0").toUpperCase()}`;
}
export function StrategyName({id}:{id?:string|null}){return <span className="strategy-alias" title={id??undefined}>{shortStrategy(id)}</span>;}
