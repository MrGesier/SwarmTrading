# Connexion Hyperliquid locale

Ouvrir `http://127.0.0.1:8000/hyperliquid` ou **Wallet Hyperliquid** dans la navigation.

1. Dans un navigateur disposant d’un wallet injecté (interface `window.ethereum`), cliquer **Connecter le wallet du navigateur** et choisir l’adresse à partager. Le navigateur intégré peut ne pas avoir d’extension : ouvrir alors la même URL dans le navigateur habituel, ou saisir uniquement l’adresse publique.
2. Choisir le réseau du compte : mainnet pour consulter le compte réel, testnet pour le compte de test. Le réseau de consultation ne change pas le réseau du wallet ni la source Hyperliquid mainnet du paper.
3. Cliquer **Afficher le compte** : aperçu perps principal, balances spot et ordres ouverts. Les données sont un instantané horodaté. Reconnecter pour sélectionner un autre compte ; pas de suivi automatique des changements du wallet.

Le backend appelle uniquement les endpoints publics `/info` (clearinghouseState, spotClearinghouseState, openOrders). Aucun SDK de signature, clé privée, seed, changement de chaîne, approbation d’API wallet ou ordre. L’adresse reste dans l’état de cette page, sans stockage persistant. La consultation d’une adresse ne démontre pas sa propriété. Le résultat n’agrège pas tous les DEX HIP-3 ou les sous-comptes.

## Ce qui n’est pas encore prêt

L’adaptateur Python d’exécution existe, mais les autorisations, signatures, ordres/annulations, rapprochements, erreurs réseau et contrôles de risque ne sont pas validés ensemble en testnet. Aucun bouton ne permet ici d’activer le live. `HYPERLIQUID_ENABLED=false` reste inchangé.

Quand cette chaîne sera prête, une API wallet dédiée devra être approuvée depuis le wallet principal sur l’interface officielle. Ne pas utiliser la clé privée du wallet principal. Aucune clé n’est nécessaire pour cette étape de consultation ou pour le paper actuel. Le SDK optionnel est décrit dans `backend/requirements-execution.txt` ; il n’est pas nécessaire à la connexion en lecture seule.

Documentation officielle :
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets
