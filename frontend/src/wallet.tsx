import React, { useRef, useState } from "react";
import { API } from "./api";
type Provider = {request: (args: {method: string}) => Promise<unknown>};
type Account = {address:string; network:string; observed_at:number; perps:{marginSummary?:{accountValue?:string}; assetPositions?:{position:{coin:string;szi:string;entryPx?:string;unrealizedPnl?:string}}[]}; spot:{balances?:{coin:string;total:string;hold:string}[]}; open_orders:{coin:string;side:string;sz:string;limitPx:string;oid:number}[]};
const money = (value: unknown) => value == null ? "—" : Number.isFinite(Number(value)) ? Number(value).toLocaleString("fr-FR", {maximumFractionDigits:2}) : "—";
export function HyperliquidWallet() {
 const [address,setAddress]=useState(""); const [network,setNetwork]=useState("mainnet");
 const [account,setAccount]=useState<Account|null>(null); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
 const sequence=useRef(0);
 async function load(candidate=address) {
  const id=++sequence.current; setError("");setAccount(null);
  if(!/^0x[0-9a-fA-F]{40}$/.test(candidate)){setError("Adresse publique attendue : 0x suivi de 40 caractères hexadécimaux.");return;}
  setBusy(true);
  try {const response=await fetch(`${API}/api/hyperliquid/account`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({address:candidate,network})});
   if(!response.ok) throw new Error(response.status===502?"Hyperliquid ne répond pas. Réessaie plus tard.":"Consultation refusée. Vérifie l’adresse et ouvre cette page depuis le serveur local.");
   const data=await response.json(); if(id===sequence.current)setAccount(data);
  } catch(e){if(id===sequence.current)setError(e instanceof Error?e.message:"Connexion impossible");}
  finally {if(id===sequence.current)setBusy(false);}
 }
 async function connect(){
  const provider=(window as Window & {ethereum?:Provider}).ethereum;
  if(!provider){setError("Aucun wallet de navigateur détecté. Ouvre cette même adresse locale dans ton navigateur avec son extension wallet, ou colle uniquement ton adresse publique ci-dessous.");return;}
  setError("");setBusy(true);
  try {const accounts=await provider.request({method:"eth_requestAccounts"});
   if(!Array.isArray(accounts)||typeof accounts[0]!=="string")throw new Error("Aucune adresse partagée par le wallet.");
   setAddress(accounts[0]);await load(accounts[0]);
  }catch{setError("Connexion annulée ou wallet indisponible.");}finally{setBusy(false);}
 }
 return <section className="wallet-setup" aria-label="Connexion Hyperliquid">
  <header><span className="factory-eyebrow">HYPERLIQUID · COMPTE</span><h2>Connecter ton wallet</h2><p>Consulte ton compte réel séparément des résultats paper. Cette connexion partage une adresse publique, sans signature ni autorisation de trading.</p></header>
  <div className="wallet-status"><strong>Lecture seule</strong><span>Mode paper · envoi d’ordres réels non branché dans cette page</span></div>
  <button disabled={busy} onClick={connect}>Connecter le wallet du navigateur</button>
  <p className="muted">L’adresse choisie est consultée au moment du clic. Pour changer de compte dans ton wallet, reconnecte-le ici. Rien n’est sauvegardé après fermeture de cette page.</p>
  <form onSubmit={e=>{e.preventDefault();void load();}}>
   <label>Réseau du compte<select disabled={busy} value={network} onChange={e=>{setNetwork(e.target.value);setAccount(null);setError("");}}><option value="mainnet">Mainnet · compte réel en lecture seule</option><option value="testnet">Testnet · compte de test</option></select></label>
   <label>Adresse publique du compte<input disabled={busy} value={address} placeholder="0x…" autoComplete="off" spellCheck={false} onChange={e=>{setAddress(e.target.value.trim());setAccount(null);setError("");}}/></label>
   <small>Adresse du compte principal ou sous-compte, pas celle d’une API wallet. Ne saisis jamais une seed phrase ou une clé privée.</small>
   <button disabled={busy} type="submit">{busy?"Consultation…":"Afficher le compte"}</button>
  </form>
  {error&&<p role="alert">{error}</p>}
  {account&&<section aria-label="Compte consulté"><h3>Compte consulté · {account.network}</h3><p className="wallet-address">{account.address}</p><small>Instantané du {new Date(account.observed_at*1000).toLocaleString("fr-FR")} · actualiser avec « Afficher le compte »</small>
   <h4>Compte perps principal : {money(account.perps.marginSummary?.accountValue)} USD</h4>
   <p className="muted">Ce montant vient d’Hyperliquid, pas des gains simulés de Darwin. Vue limitée au DEX perps principal et au spot, sans agrégation HIP-3 ni sous-comptes.</p>
   <h4>Positions perps</h4>{account.perps.assetPositions?.length?<ul>{account.perps.assetPositions.map(({position:p})=><li key={p.coin}>{p.coin} · quantité {p.szi} · entrée {p.entryPx??"—"} · PnL latent {money(p.unrealizedPnl)} USD</li>)}</ul>:<p>Aucune position sur ce périmètre.</p>}
   <h4>Soldes spot</h4>{account.spot.balances?.length?<ul>{account.spot.balances.map(b=><li key={b.coin}>{b.coin} · total {b.total} · réservé {b.hold}</li>)}</ul>:<p>Aucun solde spot retourné.</p>}
   <h4>Ordres ouverts : {account.open_orders.length}</h4><ul>{account.open_orders.slice(0,30).map(o=><li key={o.oid}>{o.coin} · {o.side==="B"?"achat":"vente"} · {o.sz} à {o.limitPx}</li>)}</ul>{account.open_orders.length>30&&<p>Affichage limité aux 30 premiers ordres.</p>}
   <p>Un compte vide peut être neuf, sur un autre réseau ou une autre adresse. Une réponse API ne prouve pas la propriété du compte.</p>
  </section>}
  <details><summary>Et pour autoriser Darwin à trader plus tard ?</summary><ol>
   <li>Valider d’abord les ordres, annulations, limites et rapprochements sur testnet. L’adaptateur existe, mais cette chaîne n’est pas validée de bout en bout.</li>
   <li>Créer et approuver une API wallet dédiée sur l’interface officielle Hyperliquid lorsque l’intégration d’exécution sera prête. Sa clé restera locale, hors des agents et de la conversation.</li>
   <li>Vérifier le plafond d’exposition, le funding et les frais, puis approuver séparément toute activation réelle. Connecter ton wallet ici n’active aucune de ces étapes.</li>
  </ol><a href="https://app.hyperliquid.xyz" target="_blank" rel="noreferrer">Ouvrir Hyperliquid officiel ↗</a> · <a href="https://app.hyperliquid-testnet.xyz" target="_blank" rel="noreferrer">Ouvrir le testnet officiel ↗</a></details>
 </section>;
}
