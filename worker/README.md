# Vigie chat Worker

Cloudflare Worker TypeScript exposing `POST /api/chat` to the static GitHub Pages frontend.

The browser sends only the question, selected company/period, and six recent messages. The Worker fetches the published Vigie dataset itself, routes short factual questions to `gpt-5.6-terra` with low reasoning, and analytical questions to `gpt-5.6-sol` with medium reasoning. Responses use a strict JSON schema, `store: false`, a privacy-preserving `safety_identifier`, and citations restricted to URLs already present in the dataset.

## Local validation

```bash
npm ci
npm run types
npm run check
```

## Secrets and deployment

Never commit secrets. Configure `OPENAI_API_KEY` and `SAFETY_SALT` as Worker secrets. GitHub deployment also requires repository secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `OPENAI_API_KEY`, and `CHAT_SAFETY_SALT`. Run the manual **Deploy chat worker** workflow, then set repository variable `CHAT_API_URL` to the deployed `/api/chat` URL and redeploy Pages.

The Cloudflare binding limits each pseudonymous client identifier to 12 questions per minute. Production CORS allows only `https://jeplante.github.io`; localhost can be enabled explicitly for development.
