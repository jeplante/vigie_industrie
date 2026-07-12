# Vigie de l’industrie canadienne de l’assurance de personnes

Application statique de vigie des résultats financiers et des actualités de Manuvie (MFC),
Sun Life (SLF), Great-West Lifeco (GWO) et iA Groupe financier (IAG). La V2 sépare le site,
les données publiées, la configuration et le pipeline d’acquisition. Le navigateur ne contacte
jamais les sites des assureurs.

## Architecture

- `app/` : interface Vite + TypeScript sans framework, tests Vitest, export CSV.
- `pipeline/` : découverte, téléchargement borné, extraction, Anthropic en secours, validation
  et publication atomique en Python 3.12.
- `config/` : sociétés, sources, métriques et seuils en YAML.
- `data/seed/` : migration complète des 64 observations et 48 actualités de la V1.
- `data/published/` : dernière version validée; seule cette version alimente le site.
- `schemas/` : contrats JSON de publication.
- `.github/workflows/` : CI et rafraîchissement/déploiement GitHub Pages.

Le détail des décisions est dans [ARCHITECTURE.md](ARCHITECTURE.md). Les procédures courantes
sont dans [OPERATIONS.md](OPERATIONS.md).

## Prérequis et installation locale

- Python 3.12 ou plus récent;
- Node.js 22 et npm;
- aucune clé n’est requise pour le mode hors ligne.

```bash
cd pipeline
python -m pip install -e ".[dev]"
cd ../app
npm ci
```

Ne versionnez jamais `.env`. Le fichier `.env.example` documente les noms de variables et les
modèles non secrets par défaut; le pipeline ne charge pas automatiquement un fichier `.env`.

## Commandes frontend

```bash
cd app
npm run dev
npm run lint
npm run typecheck
npm run test
npm run build
```

Vite utilise la base `/vigie_industrie/`. La sortie de production est `app/dist/`.

## Commandes pipeline

```bash
cd pipeline
python -m vigie_pipeline discover
python -m vigie_pipeline validate
python -m vigie_pipeline publish
python -m vigie_pipeline refresh
python -m vigie_pipeline refresh --company MFC
python -m vigie_pipeline refresh --offline
python -m vigie_pipeline discover --offline
python -m vigie_pipeline sync-frontend
```

Le mode hors ligne recharge le seed V1, applique les corrections manuelles, valide le candidat
et publie sans accès réseau. En ligne, une extraction financière incomplète sur un nouveau
document conserve les observations précédentes et publie un avertissement `stale`; un échec
bloquant d’une autre source obligatoire ou de la validation produit un rapport structuré dans
`data/generated/quality-report.json` et conserve `data/published/` intact.

## Périodes et fraîcheur

Chaque période possède un identifiant composite stable (`2026-T1`, `2026-T2`, `2026-AN`) en
plus de sa clé (`T1`, `T2`, `T3`, `AN`), de l’année, du trimestre, de la date de fin et du libellé.
Le pipeline ajoute automatiquement les nouvelles périodes découvertes et fusionne par
`periodId`; une année ne peut donc jamais en remplacer une autre. Les actualités utilisent le
même identifiant. Le frontend conserve `periodId` dans son état, trie les périodes par date
décroissante et ne propose que celles réellement publiées pour la compagnie sélectionnée.

Le manifeste publie, pour chaque compagnie, `latestAvailablePeriodId`,
`latestPublishedPeriodId`, `latestSourceCheckAt` et `freshnessStatus`. Le statut est `current`
quand le dernier document officiel découvert est intégré, `stale` quand un document plus récent
n’a pas pu être intégré, et `unknown` quand la source n’a pas pu être vérifiée. Le rapport de
qualité utilise alors l’avertissement structuré `newer_document_not_ingested` sans inventer de
données ni supprimer la dernière version valide.

## Configuration Anthropic

La clé n’est lue que par le pipeline depuis `ANTHROPIC_API_KEY`. Les modèles sont remplaçables
avec `ANTHROPIC_STANDARD_MODEL` et `ANTHROPIC_COMPLEX_MODEL`. Le modèle standard sert aux
résumés et associations simples; le complexe n’est utilisé qu’après une extraction déterministe
incomplète. Les valeurs par défaut sont respectivement `claude-haiku-4-5` et
`claude-sonnet-5`. Le SDK utilise `client.messages.parse(..., output_format=ModelePydantic)`,
qui applique les Structured Outputs Anthropic natifs; une validation Pydantic supplémentaire
reste obligatoire avant publication.

Les quatre assureurs disposent également d’une source `official_news`. Les nouveaux articles
sont dédupliqués par URL canonique, téléchargés avec des limites strictes, puis résumés et classés
en français avec le modèle standard. La source originale, l’empreinte et la trace LLM restent
attachées à chaque actualité.

Dans GitHub : **Settings → Secrets and variables → Actions → New repository secret**, créez
`ANTHROPIC_API_KEY`. Ajoutez facultativement les deux modèles comme **repository variables**,
pas comme secrets. La clé ne doit jamais être placée dans Pages, un commit ou un journal.

## GitHub Pages et rafraîchissement manuel

Activez **Settings → Pages → Source: GitHub Actions**. `Deploy GitHub Pages` valide et déploie
le last-known-good sans contacter les assureurs ni lire `ANTHROPIC_API_KEY`. `Refresh industry
data` s’exécute chaque jour à `10:17 UTC` ou manuellement, acquiert et valide les nouveautés,
puis appelle le déploiement seulement après succès. Une panne d’acquisition ne bloque donc jamais
un déploiement indépendant de la dernière donnée valide. Le cron GitHub reste en UTC.

Le site attendu est : <https://jeplante.github.io/vigie_industrie/>.

## Corrections et extensions

### Correction manuelle

Ajoutez une entrée auditable dans `data/manual/overrides.yaml`. Une correction doit viser un
identifiant existant, limiter ses champs à `value`, `displayValue`, `note` ou `direction`, citer
une source officielle et indiquer l’approbation. Exécutez ensuite le refresh hors ligne et tous
les tests. Le rapport indique le nombre de corrections appliquées.

### Ajouter une compagnie

1. Ajouter la société dans `config/companies.yaml` et ses sources primaires dans
   `config/sources.yaml`.
2. Créer un adaptateur sous `pipeline/src/vigie_pipeline/sources/` et l’inscrire dans
   `acquire.py`.
3. Ajouter des fixtures et tests, puis adapter l’union TypeScript si un identifiant fermé est
   souhaité.

### Ajouter une métrique

Ajouter son identifiant stable dans `config/metrics.yaml` et `METRIC_CATALOG` côté TypeScript,
puis couvrir normalisation et validation. Le pipeline déduit son catalogue d’unités du YAML.

### Ajouter une source

Ajouter l’URL et sa politique à `config/sources.yaml`. Les métriques financières doivent garder
une priorité primaire officielle. Une source secondaire peut enrichir une actualité mais ne peut
jamais remplacer une valeur financière.

## Dépannage rapide

- `data/generated/quality-report.json` explique une extraction refusée sans écraser la version
  publiée.
- Une erreur HTTP mentionne la source, le type, la taille ou le nombre de tentatives.
- Un refus, une réponse tronquée, un modèle sans Structured Outputs ou une sortie Pydantic
  invalide fait échouer l’acquisition sans toucher au last-known-good.
- Si Pages retourne des 404, vérifier la base Vite et que le dépôt se nomme `vigie_industrie`.
- Pour restaurer une version valide, suivre la procédure détaillée dans `OPERATIONS.md`.
