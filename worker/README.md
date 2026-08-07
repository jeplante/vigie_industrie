# Vigie chat Worker

Cloudflare Worker TypeScript exposing `POST /api/chat` for the static GitHub Pages frontend.
It is intentionally isolated from the frontend and does not alter any existing application files.

## Setup

```bash
cd worker
npm install
npx wrangler secret put OPENAI_API_KEY
npx wrangler dev --var OPENAI_MODEL:gpt-5-mini
```

Set `OPENAI_MODEL` as a non-secret Cloudflare Worker variable before deployment, for example:

```bash
npx wrangler deploy --var OPENAI_MODEL:gpt-5-mini
```

Do not add `OPENAI_API_KEY` to `wrangler.toml`, source files, or Git. Deploying is intentionally not part of this change.

## API

`POST /api/chat` accepts:

```json
{
  "question": "Compare the latest published results."
}
```

The Worker always fetches the published `vigie.json` from the repository's GitHub raw URL. It does not accept a browser-supplied dataset, preventing untrusted data from being sent to the model. The response is:

```json
{
  "answer": "...",
  "citations": [{ "title": "...", "url": "https://...", "publishedAt": "2026-08-07" }],
  "dataAsOf": "2026-08-07T11:10:28.268608Z"
}
```

Only `https://jeplante.github.io` and `http://localhost` origins (with an optional port) receive CORS access. `OPTIONS` is supported. Questions are limited to 1,000 characters. The Worker compacts the most recent observation period for each company into at most 12,000 characters, and only sends that supplied published data to OpenAI. It does not browse the web; citations are restricted to the source URLs already validated by the Vigie pipeline.

## Official-web extension

The first release deliberately uses the curated Vigie corpus only. To retrieve new publications from issuer sites, add a server-side discovery provider with an explicit domain allow-list and a search/discovery API; do not let the model browse arbitrary URLs or accept URLs from browsers.

## Rate limiting

The prototype limits each `CF-Connecting-IP` to 12 requests per 60 seconds with an in-memory map. This is best-effort only: Worker isolates do not share memory, entries disappear when isolates restart, and it is not suitable as a distributed production rate limiter. Use Cloudflare rate limiting, Durable Objects, or KV for a production policy.

## Validation

```bash
cd worker
npm install
npm run typecheck
```