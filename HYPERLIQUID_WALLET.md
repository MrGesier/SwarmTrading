# Connexion Hyperliquid locale

Ouvrir `http://127.0.0.1:8000/hyperliquid` ou **Wallet Hyperliquid** dans la navigation.

1. Cliquer **Connecter MetaMask** dans le navigateur où l’extension est installée. Darwin détecte MetaMask via EIP-6963 (avec compatibilité `window.ethereum.isMetaMask`). Dans le navigateur intégré sans extension, **Connecter MetaMask · QR mobile** ouvre le dialogue officiel MetaMask : scanner avec MetaMask mobile et accepter le partage de l’adresse.
2. Choisir le réseau du compte : mainnet pour consulter le compte réel, testnet pour le compte de test. Ce choix ne change pas la chaîne du wallet ni la source Hyperliquid mainnet du paper.
3. L’adresse partagée est consultée automatiquement. **Afficher le compte** actualise cet instantané ; la saisie manuelle d’une adresse publique reste possible. Tout changement de compte MetaMask efface les anciennes données et demande une actualisation explicite.

MetaMask partage une adresse ; Hyperliquid fournit les positions, soldes et ordres de cette adresse. Le backend utilise uniquement les endpoints publics `/info`. Aucune signature d’ordre, clé privée, seed, approbation d’API wallet ou changement de chaîne n’est demandé. La consultation ne démontre pas la propriété du compte et n’agrège pas les DEX HIP-3 ou sous-comptes.

Le SDK officiel `@metamask/connect-evm` est chargé seulement au clic, avec analytics désactivées. Il peut conserver une session de connexion ; **Déconnecter de Darwin / annuler** termine la session SDK. Pour l’extension native, retirer l’autorisation du site dans MetaMask si souhaité. Aucune clé privée n’est stockée par Darwin. Le RPC Ethereum public déclaré pour satisfaire la configuration du SDK ne sert pas à interroger le compte Hyperliquid.

## Ce qui n’est pas encore prêt

L’adaptateur Python d’exécution existe, mais les autorisations, signatures, ordres/annulations, rapprochements, erreurs réseau et contrôles de risque ne sont pas validés ensemble en testnet. Aucun bouton ne permet ici d’activer le live. `HYPERLIQUID_ENABLED=false` reste inchangé.

Quand cette chaîne sera prête, une API wallet dédiée devra être approuvée depuis le wallet principal sur l’interface officielle. Ne pas utiliser la clé privée du wallet principal. Aucune clé n’est nécessaire pour cette étape de consultation ou pour le paper actuel. Le SDK optionnel est décrit dans `backend/requirements-execution.txt` ; il n’est pas nécessaire à la connexion en lecture seule.

Documentation officielle :
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets
