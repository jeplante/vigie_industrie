# Architecture V2

## Vue d’ensemble

```mermaid
flowchart TD
    A["Sources officielles et réglementaires"] --> B["GitHub Actions · Python 3.12"]
    B --> C["Découverte · ETag · Last-Modified · SHA-256"]
    C --> D["Téléchargement borné et extraction déterministe"]
    D -->|"ambigu ou incomplet"| E["Fournisseur LLM Anthropic"]
    D --> F["Normalisation et corrections manuelles"]
    E --> F
    F --> G{"Validation métier et schémas"}
    G -->|"valide"| H["Publication atomique · data/published"]
    G -->|"invalide"| I["Rapport d’erreur · dernière version conservée"]
    H --> J["JSON statique · app/public/data"]
    J --> K["Vite + TypeScript · GitHub Pages"]
    K -. "future source" .-> L["MicrosoftGraphDataProvider"]
    H -. "future destination" .-> M["SharePointPublisher"]
```

## Responsabilités

Le frontend valide la forme minimale des trois documents, gère l’état compagnie/`periodId`/filtre,
rend avec `textContent` et création DOM explicite, puis exporte toutes les observations publiées.
`DataProvider` masque l’emplacement physique. `StaticJsonDataProvider` est la seule implémentation
actuelle.

Le pipeline charge les quatre YAML dans des modèles Pydantic, découvre les liens de documents,
télécharge avec timeout, reprises,
redirections et taille maximale, puis confie le contenu à l’adaptateur de la société. Les PDF
passent par `pypdf`; le HTML par BeautifulSoup et des expressions contrôlées. Une extraction
Anthropic ne peut fournir qu’un modèle Pydantic strict et reste soumise aux mêmes validations.

`Publisher` isole la destination. `GitHubPagesPublisher` écrit les trois fichiers candidats dans
un répertoire temporaire, puis les remplace ensemble. La future destination SharePoint n’affecte
donc pas la logique d’acquisition.

## Modèle canonique

Une observation conserve une valeur numérique, son unité, une valeur d’affichage française, un
comparatif numérique, la variation recalculée, la direction, la source primaire, son empreinte et
la qualité. Les identifiants suivent `COMPAGNIE-ANNÉE-PÉRIODE-MÉTRIQUE`.

Une période est identifiée par `periodId = ANNÉE-periodKey`, par exemple `2026-T1`. `periodKey`,
`year`, `quarter`, `endDate` et `label` restent des champs distincts. Les fusions, observations,
actualités et sélections UI utilisent l’identifiant composite. Le comparatif d’une période pointe
uniquement vers le même `periodKey` de l’année précédente; en son absence, aucun comparatif
trimestriel ou annuel différent n’est substitué.

Les actualités conservent leur `periodId`, titre, source, date, résumé original ou généré, catégories,
importance, thèmes et qualité. Le seed garde les 64 observations et 48 actualités de la V1;
`scripts/migrate-v1.mjs` vérifie explicitement ces cardinalités.

## Stratégie LLM et traçabilité

`LlmProvider` permet de remplacer Anthropic plus tard. `NoLlmProvider` rend le mode sans LLM
explicite. Anthropic reçoit un contenu tronqué à la limite configurée et une température nulle.
Le SDK 0.116+ utilise `messages.parse` et un modèle Pydantic, traduit nativement vers
`output_config.format`; refus, limite de jetons, réponse incomplète et modèle incompatible sont
des erreurs distinctes.

Un résultat LLM publié porte fournisseur, modèle, version du prompt, date, tâche, empreinte de la
source, confiance et avertissements dans `quality.llmTrace`. Aucun raisonnement interne n’est
stocké. Les journaux contiennent le modèle, la tâche et l’usage disponible, jamais la clé.
La trace est construite par résultat : une métrique déterministe d’un document mixte ne reçoit
jamais la trace de la métrique extraite par Claude.

## Last known good

Le pipeline ne publie qu’après validation complète. Un nouveau document financier inexploitable
ne remplace aucune observation: il publie un état `stale` et un avertissement structuré. En cas
d’échec bloquant d’une autre source obligatoire, de correction ou de validation, un rapport
`failed` est écrit sous `data/generated/`, le processus retourne un code non nul et
`data/published/` n’est pas modifié. Les contrôles comprennent
identifiants, compagnies, périodes, nombres finis, unités, source primaire, dates futures, HTML,
deltas, directions, volume minimal et baisse anormale.

La fraîcheur ne dépend pas du calendrier. Une vérification compare les périodes inférées des
documents officiels découverts aux observations intégrées. Le manifeste expose les dernières
périodes disponible et publiée ainsi que l’heure de vérification. Une extraction échouée sur un
document plus récent produit `newer_document_not_ingested` et `stale`; une source inaccessible
produit `unknown` tout en conservant les observations validées précédentes.

## Décisions et limites

- Le site demeure entièrement statique; aucun secret ni appel aux assureurs n’existe dans le
  navigateur.
- Aucun framework UI n’est nécessaire pour quatre onglets, quatre cartes et une liste filtrée.
- Les quatre adaptateurs sont volontairement petits; leurs alias doivent être ajustés lorsque les
  gabarits officiels changent.
- Au 11 juillet 2026, la page Manuvie est lisible dans un navigateur mais répond HTTP 403 au
  client automatisé testé. Le pipeline signale ce blocage et protège le last-known-good; il faut
  valider avec Manuvie un point d’accès automatisable ou ajouter une source officielle de repli.
- `deploy-pages.yml` ne fait aucun accès réseau métier et peut toujours republier la dernière
  donnée valide. `refresh-data.yml` demeure rouge si Manuvie, source obligatoire, retourne 403;
  il ne commite ni ne remplace alors les données et n’appelle pas le déploiement réutilisable.
- Les sélecteurs et URL sont couverts par fixtures, mais leur comportement en direct doit être
  surveillé dans le workflow. Une nouvelle mise en page non reconnue échoue de façon visible.
- Le seed V1 possède des valeurs parfois arrondies. Le delta numérique est recalculé sur ces
  valeurs; le delta textuel historique reste conservé pour affichage et audit.

## Extension SharePoint

Deux scénarios sont possibles sans changer le domaine : ajouter un `SharePointPublisher` pour
copier les JSON publiés dans une bibliothèque tout en gardant Pages, ou remplacer Pages par un
frontend utilisant `MicrosoftGraphDataProvider`. Le second nécessitera authentification, règles
CORS et gestion des jetons hors du bundle public. Aucune dépendance Microsoft Graph n’est ajoutée
maintenant.
