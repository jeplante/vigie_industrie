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

Ne versionnez jamais `.env`. Le fichier `.env.example` documente uniquement les noms de
variables; le pipeline ne charge pas automatiquement un fichier `.env`.

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
```

Le mode hors ligne recharge le seed V1, applique les corrections manuelles, valide le candidat
et publie sans accès réseau. En ligne, toute extraction incomplète produit un rapport structuré
dans `data/generated/quality-report.json`, fait échouer la commande et conserve
`data/published/` intact.

## Configuration Anthropic

La clé n’est lue que par le pipeline depuis `ANTHROPIC_API_KEY`. Les modèles sont remplaçables
avec `ANTHROPIC_STANDARD_MODEL` et `ANTHROPIC_COMPLEX_MODEL`. Le modèle standard sert aux
résumés et associations simples; le complexe n’est utilisé qu’après une extraction déterministe
incomplète. Les valeurs de repli documentées sont respectivement
`claude-sonnet-4-20250514` et `claude-opus-4-20250514`. Toute sortie est validée par Pydantic
avant d’entrer dans un candidat.

Dans GitHub : **Settings → Secrets and variables → Actions → New repository secret**, créez
`ANTHROPIC_API_KEY`. Ajoutez facultativement les deux modèles comme **repository variables**,
pas comme secrets. La clé ne doit jamais être placée dans Pages, un commit ou un journal.

## GitHub Pages et rafraîchissement manuel

Activez **Settings → Pages → Source: GitHub Actions**. Le workflow `Refresh and deploy` se lance
chaque jour à `10:17 UTC`, sur les changements pertinents de `main`, ou manuellement depuis
**Actions → Refresh and deploy → Run workflow**. L’heure locale de Montréal varie avec l’heure
avancée; le cron GitHub reste en UTC.

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

Ajouter son identifiant stable dans `config/metrics.yaml`, `METRIC_CATALOG` côté TypeScript,
`METRIC_META` et les unités reconnues côté pipeline, puis couvrir normalisation et validation.

### Ajouter une source

Ajouter l’URL et sa politique à `config/sources.yaml`. Les métriques financières doivent garder
une priorité primaire officielle. Une source secondaire peut enrichir une actualité mais ne peut
jamais remplacer une valeur financière.

## Dépannage rapide

- `data/generated/quality-report.json` explique une extraction refusée sans écraser la version
  publiée.
- Une erreur HTTP mentionne la source, le type, la taille ou le nombre de tentatives.
- Une réponse LLM invalide est refusée; aucun JSON Anthropic n’est publié directement.
- Si Pages retourne des 404, vérifier la base Vite et que le dépôt se nomme `vigie_industrie`.
- Pour restaurer une version valide, suivre la procédure détaillée dans `OPERATIONS.md`.
