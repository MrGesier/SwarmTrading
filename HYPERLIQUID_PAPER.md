# Darwin — Hyperliquid paper

Lancer **Darwin - Hyperliquid Paper** sur le bureau, ou `Demarrer-Darwin-Paper.cmd`. Le lanceur démarre le serveur local et le worker Codex, puis ouvre Factory. Aucun wallet n’est nécessaire pour les cours publics ou les trades paper. Le serveur expose uniquement `mode=live` (données réelles), sans sélection de données synthétiques et sans repli vers celles-ci en cas de déconnexion. Les anciens historiques de simulation restent archivés, sans être affichés dans ce mode. Les générateurs synthétiques ne servent plus qu’aux tests hors ligne.

## Boucle automatique

Cours Hyperliquid → positions paper et frais → seuils d’observation → sélection déterministe → ATLAS/CURIE/EVOLVE → nouveaux descendants → prochaine fenêtre → comparaison et mémoire. La configuration locale lance un cycle toutes les heures, sous réserve d’au moins 300 secondes observées et 5 clôtures par stratégie. Les incidents peuvent aussi déclencher un cycle. Le plafond OpenRouter demeure commun à tous les agents : 20 tentatives par 24 heures. Après épuisement, la recherche continue avec un repli déterministe identifié ; ce n’est pas une réponse LLM.

Les appels de recherche s’exécutent en dehors de la boucle réseau. Le flux et l’interface continuent à s’actualiser. Entre fenêtres, les comptes paper sont mis à plat puis les observations suspendues pendant l’analyse : aucune durée ni aucun rendement n’est inventé pendant cette pause. La Factory affiche RESEARCH_RUNNING. Un second cycle simultané est refusé. Les mutations et critères de sélection restent bornés ; une création n’est pas une preuve d’amélioration du PnL.

## Programmation

Codex utilise la connexion ChatGPT locale. La démonstration de code produit une proposition dans un worktree isolé avec tests et diff. Elle porte encore sur un défaut contrôlé de présentation. Les diagnostics de stagnation préparent des tâches d’ingénierie, mais leur transformation en réécritures libres des stratégies n’est pas implémentée. Aucun patch généré n’est intégré automatiquement. Ne pas confondre cette démo avec les mutations de paramètres, qui tournent réellement sans clic.

## Futur réel

L’exécuteur existe derrière des vérifications séparées et reste désactivé. Ne pas communiquer de seed phrase ou de clé de wallet principal à Darwin. Une étape ultérieure devra configurer une API wallet dédiée, vérifier le compte et le réseau, plafonner les montants et tester la soumission puis l’annulation. Aucune aptitude au réel n’est démontrée. Les frais sont encore un modèle configurable, le funding et l’impact réel ne sont pas modélisés ; les comptes indépendants ne forment pas un portefeuille delta/gamma neutral.

## Hébergement et agents

- Railway : hébergement, pas moteur d’apprentissage. Offre gratuite avec 1 USD de ressources mensuelles après un essai de 5 USD ; fonctionnement continu non garanti dans ce budget. [Tarifs officiels](https://docs.railway.com/pricing).
- Render gratuit : mise en veille après 15 minutes sans trafic entrant, impropre à garantir cette collecte continue. [Documentation](https://render.com/docs/free).
- Local : pas de facture d’hébergement, mais le PC doit rester allumé, connecté et non en veille.
- OpenBot de CopilotKit : orchestre des coworkers, outils et conversations AG-UI. Le pont optionnel du dépôt peut fournir le contexte de recherche. Il ne remplace ni un fournisseur LLM, ni les mesures et tests nécessaires à une amélioration. Installer cette infrastructure n’est pas requis pour la boucle Darwin. [Projet officiel](https://github.com/CopilotKit/openbot).

Aucun hébergement externe ni wallet n’a été configuré par cette mise à jour.
