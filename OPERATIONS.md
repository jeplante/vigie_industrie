# Exploitation

## Déclencher un rafraîchissement

Dans GitHub, ouvrir **Actions → Refresh and deploy → Run workflow**, choisir éventuellement une
compagnie et confirmer. Le workflow planifié s’exécute à `10:17 UTC`; Montréal est à UTC−5 en
hiver et UTC−4 en été. Localement, utiliser `python -m vigie_pipeline refresh --offline` pour un
test sans réseau ou retirer `--offline` pour les sources configurées.

## Lire le rapport de qualité

`status=success` autorise la publication. `partial` indique une source ou un avertissement non
critique. `failed` bloque la publication. `sourcesFailed`, `warnings[].code`, `errors[].sourceId`
et `errors[].message` orientent le diagnostic. Un échec candidat est sous `data/generated/`; le
rapport publié décrit toujours la dernière version effectivement servie.

## Corriger une extraction

1. Vérifier le document officiel et son URL.
2. Préférer la correction de l’alias ou du sélecteur de l’adaptateur avec une fixture minimale.
3. Pour une urgence, ajouter une correction justifiée à `data/manual/overrides.yaml`.
4. Exécuter refresh hors ligne, validation, Ruff, Mypy et Pytest.
5. Vérifier le delta recalculé et le rapport avant revue.

Une source secondaire ne doit jamais corriger une valeur financière.

## Restaurer une version précédente

Créer une branche depuis `main`, restaurer les trois fichiers du même commit dans
`data/published/` et `app/public/data/`, puis exécuter `python -m vigie_pipeline validate` et le
build frontend. Ne restaurez jamais seulement `vigie.json`: manifeste et rapport doivent rester
cohérents. Faites approuver la pull request avant fusion.

## Changer les modèles Anthropic

Dans **Settings → Secrets and variables → Actions → Variables**, modifier
`ANTHROPIC_STANDARD_MODEL` ou `ANTHROPIC_COMPLEX_MODEL`. Garder la clé dans **Secrets**. Relancer
manuellement le workflow et vérifier la trace `quality.llmTrace`; aucun identifiant de modèle du
workflow n’est figé dans le frontend.

## Diagnostiquer GitHub Actions

- Échec `discover/fetch`: vérifier URL, code HTTP, type MIME, redirections et taille.
  Manuvie a retourné HTTP 403 au client automatisé lors de la vérification du 11 juillet 2026;
  ne pas contourner les protections du site. Privilégier un flux ou document officiel autorisé.
- Échec `extract`: télécharger le document, ajouter une fixture représentative, ajuster
  l’adaptateur; Anthropic n’est qu’un secours.
- Échec `validate`: consulter chaque code du rapport généré; ne pas contourner le contrôle.
- Échec npm/Vite: vérifier Node 22, `npm ci`, puis la base `/vigie_industrie/`.
- Échec Pages: vérifier l’environnement `github-pages`, les permissions `pages`/`id-token` et la
  source « GitHub Actions » dans les paramètres du dépôt.

Le commit automatique porte `chore(data): refresh industry watch data`; le workflow ignore ce
message sur le push suivant pour éviter une boucle.

## Vérifier le site publié

Ouvrir <https://jeplante.github.io/vigie_industrie/> en navigation privée. Vérifier les quatre
compagnies, les quatre périodes historiques, le statut et la date, la provenance d’une métrique,
le filtre d’actualités, un lien externe et l’export CSV. Dans les outils réseau, seuls les actifs
Pages et les trois JSON statiques doivent être chargés; aucun domaine d’assureur ni Anthropic ne
doit être appelé par le navigateur.
