import React, { useEffect, useRef, useState } from "react";
import { Help } from "./help";
import type { MetamaskConnectEVM } from "@metamask/connect-evm";
import { API } from "./api";
import { TestnetValidation } from "./testnet-validation";
type Provider = {request: (args: {method: string}) => Promise<unknown>; isMetaMask?:boolean; on?:(event:string,handler:(value:unknown)=>void)=>void; removeListener?:(event:string,handler:(value:unknown)=>void)=>void};
type Account = {address:string; network:string; observed_at:number; perps:{marginSummary?:{accountValue?:string}; assetPositions?:{position:{coin:string;szi:string;entryPx?:string;unrealizedPnl?:string}}[]}; spot:{balances?:{coin:string;total:string;hold:string}[]}; open_orders:{coin:string;side:string;sz:string;limitPx:string;oid:number}[]};
const money = (value: unknown) => value == null ? "—" : Number.isFinite(Number(value)) ? Number(value).toLocaleString("fr-FR", {maximumFractionDigits:2}) : "—";
export function HyperliquidWallet() {
 const [address,setAddress]=useState(""); const [network,setNetwork]=useState("mainnet");
 const [account,setAccount]=useState<Account|null>(null); const [busy,setBusy]=useState(false); const [error,setError]=useState("");
 const sequence=useRef(0);
 const [native,setNative]=useState<Provider|null>(null), [walletAddress,setWalletAddress]=useState("");
 const [activeProvider,setActiveProvider]=useState<Provider|null>(null);
 const sdk=useRef<MetamaskConnectEVM|null>(null);
 useEffect(()=>{
  const announce=(event:Event)=>{const detail=(event as CustomEvent).detail;if(detail?.info?.rdns==="io.metamask"&&typeof detail.provider?.request==="function")setNative(detail.provider);};
  window.addEventListener("eip6963:announceProvider",announce);
  window.dispatchEvent(new Event("eip6963:requestProvider"));
  const injected=(window as Window & {ethereum?:Provider}).ethereum;
  if(injected?.isMetaMask)setNative(old=>old??injected);
  return ()=>window.removeEventListener("eip6963:announceProvider",announce);
 },[]);
 useEffect(()=>{
  if(!activeProvider)return;
  const changed=(accounts:unknown)=>{++sequence.current;setBusy(false);setAccount(null);const next=Array.isArray(accounts)&&typeof accounts[0]==="string"?accounts[0]:"";setAddress(next);setWalletAddress(next);setError(next?"Compte MetaMask modifié. Clique sur Afficher le compte pour actualiser Hyperliquid.":"MetaMask déconnecté.");};
  const disconnected=()=>changed([]);
  activeProvider.on?.("accountsChanged",changed);activeProvider.on?.("disconnect",disconnected);
  return ()=>{activeProvider.removeListener?.("accountsChanged",changed);activeProvider.removeListener?.("disconnect",disconnected);};
 },[activeProvider]);
 async function disconnect(){++sequence.current;setActiveProvider(null);setWalletAddress("");setAddress("");setAccount(null);setBusy(false);setError("");try{await sdk.current?.disconnect();}catch{setError("Vue locale effacée. Vérifie aussi les connexions dans MetaMask.");}}

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
  const ticket=++sequence.current;setError("");setBusy(true);setAccount(null);
  try {
   let provider:Provider;let accounts:unknown;
   if(native){provider=native;accounts=await native.request({method:"eth_requestAccounts"});}
   else {
    const {createEVMClient}=await import("@metamask/connect-evm");
    sdk.current??=await createEVMClient({dapp:{name:"Darwin · Hyperliquid en lecture seule",url:window.location.origin},analytics:{enabled:false},skipAutoAnnounce:true,api:{supportedNetworks:{"0x1":"https://cloudflare-eth.com/v1/mainnet"}}});
    if(ticket!==sequence.current)return;
    const result=await sdk.current.connect();accounts=result.accounts;provider=sdk.current.getProvider() as unknown as Provider;
   }
   if(ticket!==sequence.current)return;
   if(!Array.isArray(accounts)||typeof accounts[0]!=="string")throw new Error("Aucune adresse partagée.");
   setActiveProvider(provider);setWalletAddress(accounts[0]);setAddress(accounts[0]);await load(accounts[0]);
  }catch(e){if(ticket===sequence.current){const code=(e as {code?:number})?.code;setError(code===4001?"Demande refusée dans MetaMask. Tu peux réessayer.":code===-32002?"Une demande attend déjà dans MetaMask : ouvre l’extension pour y répondre.":"Connexion MetaMask interrompue. Réessaie, ou utilise ton navigateur avec l’extension MetaMask.");}}
  finally{if(ticket===sequence.current)setBusy(false);}
 }
 return <section className="wallet-setup" aria-label="Connexion Hyperliquid">
  <header><span className="factory-eyebrow">HYPERLIQUID · COMPTE</span><h2>MetaMask → adresse → Hyperliquid</h2><p>Tu connectes MetaMask à Darwin pour partager ton adresse. Darwin lit ensuite le compte Hyperliquid de cette adresse. Ce sont deux étapes distinctes ; aucune signature d’ordre n’est demandée.</p></header>
  <div className="wallet-status"><strong>Lecture seule</strong><span>Mode paper · envoi d’ordres réels non branché dans cette page</span></div>
  <div className="wallet-steps"><span><b>1 · MetaMask</b>{walletAddress?"Adresse partagée":native?"Extension détectée":"Connexion mobile par QR disponible"}</span><span><b>2 · Hyperliquid</b>{account?"Instantané du compte reçu":"En attente de consultation"}</span><span><b>3 · Trading réel</b>Verrouillé</span></div>
  <button disabled={busy} onClick={connect}>{busy?"Ouvre MetaMask ou scanne le QR…":native?"Connecter MetaMask":"Connecter MetaMask · QR mobile"}</button>
  {(walletAddress||busy)&&<button onClick={()=>void disconnect()}>Déconnecter de Darwin / annuler</button>}
  <Help label="MetaMask et Hyperliquid" text="MetaMask détient tes clés et partage une adresse. Hyperliquid conserve le compte de trading associé. Ici, Darwin ne demande aucun ordre, transfert ou signature. Le QR officiel MetaMask fonctionne même si ce navigateur n’a pas l’extension."/>
  <p className="muted">Le navigateur intégré ne peut pas ouvrir l’extension d’un autre navigateur. Scanne le QR avec MetaMask mobile, ou ouvre cette page dans Chrome/Edge avec MetaMask. Les changements de compte effacent les anciens résultats. MetaMask peut mémoriser la session ; Darwin ne stocke aucune clé privée.</p>
  <form onSubmit={e=>{e.preventDefault();void load();}}>
   <label>Réseau du compte<Help label="Réseau du compte" text="Mainnet consulte les fonds réels ; testnet consulte des fonds de test. Ce choix ne change pas le réseau de MetaMask et n’active aucun ordre."/><select disabled={busy} value={network} onChange={e=>{setNetwork(e.target.value);setAccount(null);setError("");}}><option value="mainnet">Mainnet · compte réel en lecture seule</option><option value="testnet">Testnet · compte de test</option></select></label>
   <label>Adresse publique du compte<input disabled={busy} value={address} placeholder="0x…" autoComplete="off" spellCheck={false} onChange={e=>{setWalletAddress("");setAddress(e.target.value.trim());setAccount(null);setError("");}}/></label>
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
  <TestnetValidation/>
 </section>;
}
