import { ANSWER_SCHEMA, buildGroundingContext, chooseRoute, parseStructuredAnswer, sourceAllowlist, validateChatRequest } from "./router";

declare global {
  interface Env { OPENAI_API_KEY: string; SAFETY_SALT: string }
}

const DEFAULT_ORIGIN = "https://jeplante.github.io";
const DEFAULT_DATASET = "https://jeplante.github.io/vigie_industrie/data/vigie.json";

function allowedOrigin(origin: string | null, env: Env): boolean {
  if (!origin) return false;
  if (origin === (env.ALLOWED_ORIGIN || DEFAULT_ORIGIN)) return true;
  return false;
}

function corsHeaders(origin: string | null, env: Env): HeadersInit {
  return allowedOrigin(origin, env) ? {
    "Access-Control-Allow-Origin": origin!, "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST, OPTIONS", "Access-Control-Max-Age": "86400", Vary: "Origin",
  } : { Vary: "Origin" };
}

function json(request: Request, env: Env, body: unknown, status = 200): Response {
  return Response.json(body, { status, headers: corsHeaders(request.headers.get("Origin"), env) });
}

async function identifier(ip: string, salt: string): Promise<string> {
  const bytes = new TextEncoder().encode(`${salt}:${ip}`);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((part) => part.toString(16).padStart(2, "0")).join("").slice(0, 32);
}

async function loadDataset(env: Env): Promise<Record<string, unknown>> {
  const datasetUrl = env.DATASET_URL || DEFAULT_DATASET;
  const response = await fetch(datasetUrl, {
    signal: AbortSignal.timeout(8_000),
    cf: { cacheEverything: true, cacheTtl: 300 },
  });
  if (!response.ok) throw new Error("Les données de la Vigie sont indisponibles.");
  return await response.json() as Record<string, unknown>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("Origin");
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(origin, env) });
    if (request.method !== "POST" || new URL(request.url).pathname !== "/api/chat") return json(request, env, { error: "Introuvable." }, 404);
    if (!allowedOrigin(origin, env)) return json(request, env, { error: "Origine refusée." }, 403);
    if (!env.OPENAI_API_KEY || !env.SAFETY_SALT) return json(request, env, { error: "Service non configuré." }, 503);

    try {
      const ip = request.headers.get("CF-Connecting-IP") || "unknown";
      const safetyId = await identifier(ip, env.SAFETY_SALT);
      const rate = await env.CHAT_RATE_LIMITER.limit({ key: safetyId });
      if (!rate.success) return json(request, env, { error: "Trop de questions. Réessayez dans une minute." }, 429);
      const chat = validateChatRequest(await request.json());
      const context = buildGroundingContext(await loadDataset(env), chat);
      const route = chooseRoute(chat.question, chat.history.length, env);
      const response = await fetch("https://api.openai.com/v1/responses", {
        method: "POST", signal: AbortSignal.timeout(45_000),
        headers: { Authorization: `Bearer ${env.OPENAI_API_KEY}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model: route.model, reasoning: { effort: route.effort }, store: false, max_output_tokens: 1_200,
          safety_identifier: safetyId,
          instructions: "Vous êtes l’assistant de la Vigie de l’industrie canadienne de l’assurance de personnes. Répondez en français uniquement à partir du contexte JSON fourni. N’inventez aucune donnée. Distinguez les faits, comparaisons et interprétations. Signalez toute donnée absente ou non comparable. Ne donnez aucun conseil d’investissement. Citez uniquement les URL présentes dans le contexte.",
          input: [...chat.history, { role: "user", content: `Question: ${chat.question}\n\nContexte Vigie validé:\n${JSON.stringify(context)}` }],
          text: { format: { type: "json_schema", name: "vigie_chat_answer", strict: true, schema: ANSWER_SCHEMA } },
        }),
      });
      if (!response.ok) throw new Error(`OpenAI indisponible (${response.status}).`);
      const answer = parseStructuredAnswer(await response.json(), sourceAllowlist(context));
      return json(request, env, { ...answer, model: route.model, dataAsOf: context.generatedAt });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Erreur inattendue.";
      const status = message.includes("invalide") || message.includes("doit contenir") ? 400 : 502;
      return json(request, env, { error: message }, status);
    }
  },
} satisfies ExportedHandler<Env>;
