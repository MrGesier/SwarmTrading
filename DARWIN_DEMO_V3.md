# Démonstration locale d’autocorrection V3

Base : `darwin-v0.11-factory-evolution` au commit `8d1f234`. Implémentation sur `darwin-demo-autocorrection-v3`, sans fusion dans main.

## Parcours

1. Dans ton terminal Windows : `codex login status`. Si nécessaire : `codex login` et connexion ChatGPT. Aucune clé API OpenAI requise pour cet ingénieur local.
2. Facultatif : créer une clé OpenRouter et enregistrer `OPENROUTER_API_KEY` dans `.env` local. Ne jamais la mettre dans Git. Le sélecteur du panneau change le fournisseur de recherche ; les anciennes variables `DARWIN_BRAIN_*` explicites restent prioritaires pour les nouvelles sessions.
3. Double-cliquer **Demarrer-Darwin-Demo.cmd**. Le script réutilise `start.ps1` et lance séparément le worker avec un verrou système. Node et les dépendances du projet doivent être installés ; aucun GPU nécessaire.
4. Ouvrir Factory → **Autocorrection / Code Engineer** → **Démonstration contrôlée**. Choisir Codex CLI pour une vraie proposition ; Mock est explicitement étiqueté et ne contacte aucun modèle.
5. Examiner le diff et les sorties des tests via **Ouvrir la proposition et ses preuves**. Aucun bouton d’intégration, de push ou de déploiement automatique n’est fourni.
6. **Verifier-Darwin-Demo.cmd** vérifie la connexion, le mode paper et l’état du worker.

## Ce qui est testé

La fonction de présentation `backend/darwin/demo_report.py::validation_label` décrit des contrôles terminés. Dans un worktree détaché, le worker injecte volontairement un défaut : zéro contrôle est décrit comme PASSED. La référence doit passer, le défaut doit échouer, puis le candidat doit satisfaire le contrat complet, les tests backend et le build frontend. Les sept assertions indépendantes sont détenues par le worker, hors des chemins proposés au LLM.

Codex reçoit le petit module et le contrat dans un prompt versionné. Le CLI utilise l’authentification ChatGPT existante, un sandbox read-only, les outils shell désactivés, les plugins utilisateur désactivés et une sortie JSON contrainte. Le worker transforme **le code réellement retourné** en un fichier autorisé et un véritable diff Git. Il n’exécute aucune commande provenant du modèle. Ce choix volontaire est plus restrictif qu’un Codex autorisé à modifier librement un worktree. Le parseur AST n’autorise ni imports, ni accès aux attributs, ni boucles, ni appels arbitraires ; seuls les arguments, conditions, retours et ValueError du petit module sont admis.

Le worktree contient les fichiers Git suivis, pas le `.env`, les données ou jetons de l’installation. L’environnement des tests est reconstruit sans secrets. Le CLI utilise ses propres identifiants en place ; ils ne sont ni copiés ni exposés au code testé. Une proposition valide reçoit un commit détaché et l’état READY_FOR_REVIEW ; aucune modification de la branche en cours ni du processus Darwin. Un échec conserve le rapport puis retire le worktree exact enregistré. Un worker interrompu rejette sa tâche au redémarrage et ne la relance pas automatiquement ; des artefacts orphelins peuvent rester pour inspection.

Le worker traite une seule tâche et un seul candidat à la fois. Le bouton consomme un task pack de CodexEngineer existant. Les tâches générales préparées sur stagnation ne sont pas arbitrairement exécutées par cette démonstration : la première expérience autorisée est limitée au défaut contrôlé. Les états et résultats sont stockés dans `data/autocorrection/demo.sqlite`, les rapports dans `data/autocorrection/<id>/`. L’API ne lance aucun subprocess. Elle exige une connexion loopback, un Host local, une session HttpOnly SameSite et un jeton anti-CSRF pour les mutations. Ne pas publier ce service derrière un proxy public ; ce protocole est prévu pour la session locale.

## OpenRouter gratuit

`openrouter-free` utilise **Chat Completions**, jamais l’API Responses ni les identifiants GPT d’un autre fournisseur. Le catalogue `/models` est vérifié (cache une heure), seules les variantes `:free` avec prix prompt/completion/request nuls sont admises. `OPENROUTER_FREE_MODEL` permet de choisir un modèle du catalogue ; sinon le classement privilégie les noms liés au code et les sorties structurées. Cela ne garantit ni la qualité en programmation ni la disponibilité. Les réponses sont validées localement contre le schéma.

La limite locale est **20 tentatives d’inférence maximum par fenêtre glissante de 24 h** (configurable à la baisse), enregistrées avant l’appel dans une base commune à tous les agents, symboles et processus de cette installation. Les tentatives échouées comptent. Prompts identiques dédupliqués, succès en cache 24 h, délai persistant après 429, coupe-circuit après trois échecs. Les lectures du catalogue ne sont pas des inférences et ne sont pas incluses dans ce compteur. Une copie distincte du projet aurait son propre plafond : les limites du compte fournisseur restent globales.

Le ping affiche fournisseur, modèle, statut, latence, consommation de tokens fournie et budget local restant. Ce budget n’est pas le quota restant du compte OpenRouter. `connected` signifie réponse réelle valide ; `cached` ne signifie pas nouvel appel ; `fallback`, `rate-limited`, `quota` et `unavailable` ne sont jamais affichés comme succès LLM. Aucun mock de test ne consomme le quota réel. Ollama est un choix préparé mais indisponible, sans installation ni faux succès.

## Indicateurs et évolution des stratégies

| Signal de Darwin | Données effectivement utilisées |
|---|---|
| Momentum, Mean reversion, Trend, Volatility | Rendements à l’horizon et volatilité |
| Breakout | Rendement normalisé et amplitude du flux exécuté |
| Order flow | Déséquilibre du flux de transactions |
| Microprice | Écart du microprice au mid, normalisé par le spread |
| Book pressure | `weighted_imbalance`, déséquilibre pondéré du carnet |

Source : `backend/darwin/signals.py`, cohérente avec `backend/engine.py::votes`. L’imbalance brute et pondérée sont calculées ; c’est la pondérée qui est utilisée par Book pressure. Les visualisations VWAP, bougies et diagnostics avancés ne constituent pas toutes des entrées de ces huit familles. Huit paramètres de politique évoluent aujourd’hui, mais la combinaison de signaux, les familles et leurs formules restent prédéfinies. La V3 de code ne prétend pas avoir changé cela. Une extension des features/formules devra faire l’objet d’une proposition séparée, avec validation sur données ultérieures, comparaison à une référence et frais.

## Sources consultées

- [Codex non interactif et authentification existante](https://developers.openai.com/codex/non-interactive-mode)
- [Codex SDK](https://developers.openai.com/codex/sdk)
- [OpenRouter : tarification](https://openrouter.ai/pricing) — 50 requêtes/jour affichées pour Free à la consultation, disponibilité non garantie.
- [Limites et erreurs 429](https://openrouter.ai/docs/api/reference/limits)
- [Catalogue dynamique des modèles](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)

La demande initiale `/docs/auth` n’a pas pu être chargée ; le comportement d’authentification est fondé sur la documentation non interactive et le résultat local de `codex login status`. Le trading réel demeure désactivé ; aucun déploiement Railway ni installation Ollama.


## État vérifié le 22 septembre 2026

- Pipeline mock complet `094c60c22fef45f380a41ab8f65eca5e` : READY_FOR_REVIEW. Défaut reproduit, contrat indépendant corrigé, 79 tests backend de cette révision, TypeScript et Vite réussis. Le rapport et le diff sont dans `data/autocorrection/<id>/`. Ce résultat ne provient pas d’un LLM.
- Révision suivante : 80 tests backend réussis, `npm ci` et `npm run build` réussis. Analyse syntaxique PowerShell du lanceur réussie. Endpoints health/brains/research/factory/engineer répondent 200, `paper_only=true`.
- OpenRouter sélectionné dans l’application, clé absente, zéro inférence réelle consommée. Le quota local de 20 tentatives est distinct de l’offre du fournisseur.
- Codex connecté à ChatGPT, mais `codex exec` échoue avec « Access is denied » depuis la session isolée de l’assistant. Un ancien worker ne retrouvait pas non plus le CLI. Le lanceur recherche maintenant le CLI officiel installé par l’application et renouvelle seulement un worker inactif. L’appel sous la session Windows habituelle reste à vérifier.
- Le journal affiche la durée réelle entre ouverture et clôture. La fenêtre de signal 1 s n’est pas une durée de détention. Plusieurs comptes paper peuvent ouvrir simultanément, chacun avec une position nette ; aucun portefeuille delta/gamma neutral n’est implémenté.
- La récursivité actuelle ajuste des paramètres bornés, conserve les lignées et compare les descendants. Le défaut de code de la démo reste volontairement un helper de présentation. La réécriture des formules de stratégie à partir de diagnostics et leur évaluation hors échantillon ne sont pas encore implémentées.

Pour reprendre l’appel réel : configurer uniquement `OPENROUTER_API_KEY` dans `.env` pour les agents de recherche ; relancer `Demarrer-Darwin-Demo.cmd` sous Windows pour le worker Codex, puis lancer la démonstration Codex dans Factory. Aucune clé OpenAI n’est demandée pour Codex. Les propositions restent soumises à validation humaine avant intégration.
