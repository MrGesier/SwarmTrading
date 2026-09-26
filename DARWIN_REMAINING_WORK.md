# Darwin — audit des travaux restants

État vérifié dans le code le 26 septembre 2026. Ce document est un plan de travail, pas une liste de fonctionnalités déjà livrées.

## P1 — Mesurer clairement les résultats

Le panneau PnL affiche une moyenne de comptes indépendants et repart à zéro à chaque cycle (`supervisor.py:pnl_state`). Les totaux historiques additionnent les rendements de fenêtres (`store.py:strategy_summaries`) ; ce n’est pas une courbe de capital composé.

À faire : journal de capital paper continu avec PnL réalisé/non réalisé, frais et drawdown ; filtres stratégie/période ; distinguer population changeante, témoin fixe et portefeuille alloué. Critère : réconcilier chaque variation de capital avec les fills et coûts, y compris après redémarrage, sans transformer les moyennes de cohortes en rendement de portefeuille.

## P1 — Prouver la boucle de recherche sur la durée

Les paramètres mutent, les descendants sont comparés sur une fenêtre commune et les tâches de stagnation sont préparées. La création d’un descendant n’établit pas sa supériorité.

À faire : campagne locale prolongée sur données Hyperliquid, rapport quotidien sourcé (cycles, appels réels/fallbacks, hypothèses, enfants conservés/rejetés, coûts, ruptures de flux), validation hors échantillon sur plusieurs fenêtres et régimes. Vérifier particulièrement reprise après veille/déconnexion et attribution des durées observées. Critère : chaque promotion est traçable et ne dépend pas d’une seule fenêtre favorable.

## P1 — Relier les incidents aux propositions de code

`supervisor.py` prépare une tâche sur stagnation ; `demo_worker.py` ne traite encore qu’un défaut contrôlé de présentation.

À faire : consommateur des tâches préparées, contexte minimal sans secrets, reproduction du problème, patch isolé sur périmètre autorisé, tests indépendants, mesure avant/après, proposition en Factory. Bornes de temps, déduplication, arrêt sur échecs répétés. Critère : un problème observé déclenche sans clic une proposition testée ; intégration et déploiement restent soumis à validation humaine.

## P2 — Enrichir les stratégies, pas seulement les seuils

`signals.py` utilise déjà momentum, flow, microprice/spread et weighted_imbalance selon les familles. `genome.py` expose huit gènes ; les coefficients et compositions des indicateurs ne sont pas librement réécrits par les agents.

À faire : catalogue versionné de compositions autorisées, poids/bornes explicites, filtres de régime, expériences d’ablation et couverture des mutations. Comparer chaque nouvelle combinaison à son parent avec les mêmes observations et coûts. Ne pas brancher tous les indicateurs simplement parce qu’ils sont visibles dans Marché.

## P2 — Fidélité paper et portefeuille

`pnl_state` déclare explicitement le funding et l’impact réel non modélisés. Une position est gérée par stratégie ; plusieurs stratégies peuvent avoir des positions simultanées, sans gestion globale de couverture.

À faire : funding horodaté, frais par hypothèse de tier/maker-taker, scénarios de latence et liquidité, exposition et capital partagés, limites globales. Distinguer horizon du signal, durée de détention et raison de sortie ; analyser les clôtures répétées risk_off avant de modifier leurs garde-fous. Un portefeuille delta neutral exige une comptabilité multi-actifs ; le gamma neutral est un chantier distinct, absent du POC.

## P2 — Ergonomie sur petit écran

La vérification dans le panneau navigateur étroit montre encore un débordement horizontal et des éléments de navigation superposés. Reprendre la navigation mobile et les cartes Factory aux petites largeurs ; les nouveaux logos sont intégrés, mais cette refonte responsive reste distincte.

## P3 — Passage éventuel au réel et hébergement

Aucun ordre réel autorisé. Avant tout réel : fidélité comptable, contrôles de risque, rapprochement compte/ordres, annulation, arrêt d’urgence, essais testnet et validation humaine explicite. Le wallet n’est pas requis pour le paper public actuel.

Le local convient au POC tant que le PC reste actif et connecté. L’hébergement et OpenBot ne remplacent pas les chantiers ci-dessus. Voir `HYPERLIQUID_PAPER.md` pour les offres étudiées et leurs limites.

## Identité visuelle livrée

Nouveaux logos Darwin et Swarm Trading dans `frontend/public`, favicon Swarm Trading et icône du raccourci Darwin. Les fichiers PNG sont les masters générés ; les ICO sont des exports Windows. Anciens assets conservés pour historique, sans référence active dans le branding.
