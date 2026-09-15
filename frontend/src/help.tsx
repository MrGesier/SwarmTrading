import { useId, useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { CircleHelp } from "lucide-react";

export const explanations: Record<string, string> = {
  "MARKET INTENT":
    "État de l’horizon sélectionné : consensus pondéré (70 %), flux agressif (15 %) et déséquilibre du carnet (15 %). Trois observations consécutives stabilisent les transitions. RISK_OFF signifie que les données ou l’échauffement ne permettent pas de produire un signal. Ce score n’est pas une probabilité.",
  CONSENSUS:
    "Moyenne des signaux, pondérée pour réduire les doublons corrélés. −1 : orientation vendeuse ; +1 : acheteuse ; 0 : neutralité ou opposition. Le chiffre, la courbe et les votes utilisent l’horizon sélectionné.",
  "SWARM ENTROPY":
    "Désaccord entre les poids vendeurs, neutres et acheteurs. Proche de 0 : concentration sur un état ; proche de 1 : fragmentation. Une faible entropie peut aussi correspondre à une majorité neutre : elle ne suffit pas à justifier un trade.",
  "EFFECTIVE STRATEGIES":
    "Nombre effectif d’opinions indépendantes, calculé avec la matrice de corrélation des 120 derniers vecteurs de signaux de cet horizon. 320 variantes ne sont pas 320 avis indépendants. Les signaux constants sont exclus ; les poids sont recalculés toutes les cinq observations.",
  "Price & trigger zones":
    "Bougies à intervalle réglable construites à partir des trades reçus. Les bandes indiquent des niveaux hypothétiques où le poids des stratégies change de direction. Ce sont des sensibilités du modèle, pas des ordres réels du marché.",
  "Liquidity landscape":
    "Chaque colonne représente un instant ; chaque ligne, une zone de prix. Une couleur plus intense indique davantage de liquidité au repos dans les 40 premiers niveaux de chaque côté. La ligne claire est le midpoint. Une disparition de liquidité ne prouve pas une annulation ou du spoofing.",
  "Order-book physics":
    "Mesures complémentaires de la structure du carnet. Elles décrivent le marché et ne constituent pas des signaux d’achat ou de vente indépendants. Les calculs portent sur les 40 premiers niveaux.",
  "Strategy swarm":
    "Répartition du soutien effectif par famille à l’horizon choisi. Rose : vendeur ; gris : neutre ; vert : acheteur. Les barres utilisent les poids corrigés de la corrélation, pas le nombre brut de variantes. Cliquez sur une famille pour inspecter ses génomes.",
  "Trigger density":
    "Poids total des stratégies dont le signe change sous une variation hypothétique de prix. 1 point de base (bp) = 0,01 %. Un passage neutre → acheteur compte comme un changement. La densité ne mesure pas la probabilité d’atteindre le niveau.",
  "Entropy stack":
    "Composite de trois entropies normalisées : signes des variations de prix, volumes agressifs acheteurs/vendeurs et répartition des quantités du carnet. Moyenne à poids égaux, sans calibration prédictive.",
  "Signal timeline":
    "Historique des transitions du moteur. Chaque entrée conserve le score et les facteurs disponibles à cet instant. Cliquez pour ouvrir l’explication causale. Le score instantané peut déjà évoluer pendant que l’état attend sa confirmation.",
  "Time machine":
    "Capture les 300 derniers états de la session. Lecture et curseur figent toutes les vues au même instant. Les bougies historiques sont copiées afin qu’un trade futur ne puisse pas modifier le passé.",
  "Counterfactual engine":
    "Recalcule les génomes de l’horizon choisi en modifiant prix, volatilité et flux. Le carnet reste fixe. L’analyse mesure la sensibilité locale du modèle ; elle ne prédit pas le chemin futur.",
  "Entropy phase plane":
    "Axe horizontal : entropie composite. Axe vertical : variation par seconde. La traînée montre les derniers états. Ces quadrants décrivent une transition de structure, sans promettre une prévisibilité financière.",
  "Consensus by horizon":
    "Chaque horizon dispose de ses propres variantes et de son propre retour de prix. Les horizons 1 et 3 minutes restent en échauffement jusqu’à disposer de 60 ou 180 secondes de données réellement observées.",
  "Liquidity × trigger interaction":
    "Compare le poids des stratégies qui changent de signe à la quantité opposée entre le midpoint et le prix cible. Hors des 40 niveaux observés, la profondeur cumulée est seulement une borne inférieure.",
  "Strategy population":
    "320 génomes : 8 familles × 5 horizons × 8 variantes. Le poids effectif réduit les variantes corrélées. Un signal constant est exclu du poids ; une fenêtre temporelle incomplète est neutralisée.",
  "Book imbalance":
    "(Quantité bid − quantité ask) / (bid + ask), sur les 40 premiers niveaux. +1 signifie que la profondeur est presque exclusivement côté acheteur. Un mur peut disparaître avant toute exécution.",
  "Weighted imbalance":
    "Même comparaison, avec un poids 1/rang : les niveaux proches du meilleur prix comptent davantage que les niveaux éloignés.",
  "Microprice delta":
    "Écart entre microprice et midpoint, en points de base. Le microprice pondère le meilleur ask par la quantité bid et le meilleur bid par la quantité ask. Une valeur positive reflète davantage de pression au meilleur bid.",
  "Trade-flow imbalance":
    "(Volume d’achats agressifs − volume de ventes agressives) / volume total, sur 30 secondes. « Agressif » signifie que le trade prend la liquidité au carnet.",
  Horizon:
    "Fenêtre de mémoire utilisée par les stratégies : 1 s, 5 s, 30 s, 1 min ou 3 min. Les flux, le carnet et la population effective ont leur propre mémoire par horizon. La durée des bougies se choisit séparément de 1 seconde à 3 minutes.",
  VWAP: "Prix moyen pondéré par le volume sur les bougies affichées, calculé avec leur prix typique (haut + bas + clôture) / 3. Ce n’est pas un VWAP de journée entière.",
  SPREAD:
    "Écart entre meilleur ask et meilleur bid, rapporté au midpoint, en points de base. 1 bp = 0,01 %. Franchir le spread constitue une partie du coût d’exécution.",
  REGIME:
    "Régime déterministe basé sur la dispersion récente des rendements échantillonnés : compression, normal ou expansion. Ce libellé n’est pas une probabilité de transition.",
  "Trigger surface":
    "Chaque case recalcule le consensus de l’horizon choisi pour une variation du prix (colonnes) et un multiplicateur de volatilité (lignes). La couleur indique le signe et l’intensité du consensus ; le survol donne le poids des stratégies qui changent de signe.",
  "Consensus fragility":
    "Cherche le plus petit mouvement contraire, par pas de 1 bp jusqu’à 50 bp, qui fait changer de signe le consensus. Le carnet et le flux restent fixes. Une valeur faible signifie une sensibilité élevée ; ce n’est pas un stop recommandé.",
  "Execution cost preview":
    "Parcourt les 40 niveaux visibles pour estimer un prix moyen sur une quantité cible = montant / midpoint. Coût = écart au midpoint + frais configurés, par côté. Un remplissage partiel reste explicitement partiel. Aucune prise en compte de la latence, du renouvellement de liquidité ou de la sélection adverse ; aucun ordre envoyé.",
  "Visible liquidity":
    "Concentration : part des quantités dans les cinq meilleurs niveaux parmi les 40 observés. Vide : plus grand écart entre deux niveaux consécutifs. Ce sont des observations géométriques, pas une détection de manipulation.",
};

export function Help({ label, text }: { label: string; text?: string }) {
  const id = useId(),
    ref = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false),
    [pos, setPos] = useState({ left: 0, top: 0 });
  const description =
    text ??
    explanations[label] ??
    (label.includes("CONSENSUS") ? explanations.CONSENSUS : undefined);
  function show() {
    const r = ref.current?.getBoundingClientRect();
    if (r) {
      const width = Math.min(340, window.innerWidth - 24);
      setPos({
        left: Math.max(
          12,
          Math.min(r.left - 30, window.innerWidth - width - 12),
        ),
        top: Math.min(r.bottom + 9, window.innerHeight - 240),
      });
    }
    setOpen(true);
  }
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", key);
    return () => {
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", key);
    };
  }, [open]);
  if (!description) return null;
  return (
    <>
      <button
        ref={ref}
        type="button"
        className="help-button"
        aria-label={`Aide : ${label}`}
        aria-describedby={open ? id : undefined}
        onMouseEnter={show}
        onMouseLeave={() => setOpen(false)}
        onFocus={show}
        onBlur={() => setOpen(false)}
        onClick={(e) => {
          e.stopPropagation();
          show();
        }}
      >
        <CircleHelp size={13} />
      </button>
      {open &&
        createPortal(
          <div id={id} role="tooltip" className="help-tooltip" style={pos}>
            <strong>{label}</strong>
            <p>{description}</p>
          </div>,
          document.body,
        )}
    </>
  );
}
