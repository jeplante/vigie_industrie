interface Env {
  OPENAI_API_KEY: string;
  OPENAI_MODEL: string;
}

interface ChatRequest {
  question: string;
}

interface Citation {
  title: string;
  url: string;
  publishedAt: string;
}

interface SourceRecord {
  title?: unknown;
  url?: unknown;
  publishedAt?: unknown;
}

interface ObservationRecord {
  companyId?: unknown;
  period?: { periodId?: unknown; endDate?: unknown; label?: unknown };
  metricId?: unknown;
  label?: unknown;
  displayValue?: unknown;
  comparison?: { displayValue?: unknown; displayChange?: unknown; periodLabel?: unknown };
  note?: unknown;
  source?: SourceRecord;
}

interface DatasetRecord {
  generatedAt?: unknown;
  companies?: Array<{ id?: unknown; name?: unknown; investorRelationsUrl?: unknown }>;
  observations?: ObservationRecord[];
}

const ALLOWED_ORIGIN = "https://jeplante.github.io";
const DATASET_URL = "https://raw.githubusercontent.com/jeplante/vigie_industrie/main/data/published/vigie.json";
const MAX_QUESTION_LENGTH = 1000;
const MAX_CONTEXT_LENGTH = 12_000;
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX_REQUESTS = 12;
const rateLimits = new Map<string, { count: number; resetAt: number }>();

const SYSTEM_INSTRUCTION = `Vous etes un analyste d'affaires pour Vigie de l'industrie canadienne de l'assurance de personnes. Repondez en francais avec une analyse substantielle, precise et utile, exclusivement a partir des donnees publiees fournies dans le contexte. N'inventez aucun fait, ne completez pas avec des connaissances externes et ne naviguez jamais sur le Web. Expliquez les incertitudes, les limites de comparabilite ou les donnees manquantes. Ne donnez pas de conseil en investissement, de recommandation d'achat, de vente ou de detention. Lorsque vous appuyez une affirmation sur une source, citez son titre et son URL officielle fournis dans le contexte.`;

function corsHeaders(request: Request): HeadersInit {
  const origin = request.headers.get("Origin");
  if (origin && isAllowedOrigin(origin)) {
    return {
      "Access-Control-Allow-Origin": origin,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      "Vary": "Origin",
    };
  }
  return { "Vary": "Origin" };
}

function isAllowedOrigin(origin: string): boolean {
  return origin === ALLOWED_ORIGIN || /^http:\/\/localhost(?::\d+)?$/.test(origin);
}

function jsonResponse(request: Request, body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", ...corsHeaders(request) },
  });
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getClientIp(request: Request): string {
  return request.headers.get("CF-Connecting-IP") ?? "unknown";
}

function isRateLimited(clientIp: string): boolean {
  const now = Date.now();
  const current = rateLimits.get(clientIp);
  if (!current || current.resetAt <= now) {
    rateLimits.set(clientIp, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return false;
  }
  current.count += 1;
  return current.count > RATE_LIMIT_MAX_REQUESTS;
}

async function readRequest(request: Request): Promise<ChatRequest | null> {
  try {
    const payload: unknown = await request.json();
    if (!isRecord(payload) || typeof payload.question !== "string") return null;
    return { question: payload.question, dataset: payload.dataset };
  } catch {
    return null;
  }
}

async function loadDataset(): Promise<DatasetRecord | null> {
  try {
    const response = await fetch(DATASET_URL, { signal: AbortSignal.timeout(8_000) });
    if (!response.ok) return null;
    const payload: unknown = await response.json();
    return isRecord(payload) ? payload : null;
  } catch {
    return null;
  }
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function isPublishedSourceUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "https:";
  } catch {
    return false;
  }
}

function buildContext(dataset: DatasetRecord): { context: string; citations: Citation[]; dataAsOf: string | null } | null {
  if (!Array.isArray(dataset.companies) || !Array.isArray(dataset.observations)) return null;

  const companies = dataset.companies
    .map((company) => ({
      id: asString(company.id),
      name: asString(company.name),
    }))
    .filter((company): company is { id: string; name: string } =>
      Boolean(company.id && company.name),
    );
  if (companies.length === 0) return null;

  const latestPeriodByCompany = new Map<string, string>();
  for (const observation of dataset.observations) {
    const companyId = asString(observation.companyId);
    const endDate = asString(observation.period?.endDate);
    if (companyId && endDate && (!latestPeriodByCompany.has(companyId) || endDate > latestPeriodByCompany.get(companyId)!)) {
      latestPeriodByCompany.set(companyId, endDate);
    }
  }

  const citations: Citation[] = [];
  const citationUrls = new Set<string>();
  const lines = ["DONNEES VIGIE PUBLIEES (ne pas utiliser d'autre source) :"];
  for (const company of companies) {
    const latestEndDate = latestPeriodByCompany.get(company.id);
    if (!latestEndDate) continue;
    const observations = dataset.observations.filter((observation) =>
      observation.companyId === company.id && observation.period?.endDate === latestEndDate,
    );
    if (observations.length === 0) continue;

    const periodLabel = asString(observations[0].period?.label) ?? latestEndDate;
    lines.push(`\n${company.name} - ${periodLabel} (fin ${latestEndDate})`);
    for (const observation of observations) {
      const label = asString(observation.label);
      const value = asString(observation.displayValue);
      if (!label || !value) continue;
      const comparison = observation.comparison;
      const comparisonText = [asString(comparison?.displayValue), asString(comparison?.displayChange)]
        .filter((item): item is string => item !== null)
        .join("; ");
      const note = asString(observation.note);
      lines.push(`- ${label}: ${value}${comparisonText ? ` (comparaison: ${comparisonText})` : ""}${note ? `; note: ${note}` : ""}`);

      const source = observation.source;
      if (source && isPublishedSourceUrl(source.url) && !citationUrls.has(source.url)) {
        citationUrls.add(source.url);
        citations.push({
          title: asString(source.title) ?? `${company.name} - source officielle`,
          url: source.url,
          publishedAt: asString(source.publishedAt) ?? latestEndDate,
        });
      }
    }
  }

  if (lines.length === 1) return null;
  let context = lines.join("\n");
  if (context.length > MAX_CONTEXT_LENGTH) context = context.slice(0, MAX_CONTEXT_LENGTH);
  return { context, citations, dataAsOf: asString(dataset.generatedAt) };
}

async function getAnswer(env: Env, question: string, context: string): Promise<string | null> {
  try {
    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: env.OPENAI_MODEL,
        store: false,
        instructions: SYSTEM_INSTRUCTION,
        input: `Question de l'utilisateur:\n${question}\n\n${context}`,
      }),
      signal: AbortSignal.timeout(30_000),
    });
    if (!response.ok) return null;
    const payload: unknown = await response.json();
    if (!isRecord(payload)) return null;
    if (typeof payload.output_text === "string" && payload.output_text.trim()) return payload.output_text.trim();
    return null;
  } catch {
    return null;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("Origin");
    if (origin && !isAllowedOrigin(origin)) return jsonResponse(request, { error: "Origin not allowed." }, 403);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: corsHeaders(request) });
    if (request.method !== "POST" || new URL(request.url).pathname !== "/api/chat") {
      return jsonResponse(request, { error: "Not found." }, 404);
    }
    if (isRateLimited(getClientIp(request))) return jsonResponse(request, { error: "Too many requests." }, 429);
    if (!env.OPENAI_API_KEY || !env.OPENAI_MODEL) return jsonResponse(request, { error: "Service temporarily unavailable." }, 503);

    const chat = await readRequest(request);
    const question = chat?.question.trim();
    if (!question || question.length > MAX_QUESTION_LENGTH) {
      return jsonResponse(request, { error: "Question must contain 1 to 1000 characters." }, 400);
    }

    const dataset = await loadDataset();
    if (!dataset) return jsonResponse(request, { error: "Published data is unavailable." }, 502);
    const prepared = buildContext(dataset);
    if (!prepared) return jsonResponse(request, { error: "Published data is invalid or incomplete." }, 422);

    const answer = await getAnswer(env, question, prepared.context);
    if (!answer) return jsonResponse(request, { error: "Analysis service is temporarily unavailable." }, 502);
    return jsonResponse(request, { answer, citations: prepared.citations, dataAsOf: prepared.dataAsOf });
  },
} satisfies ExportedHandler<Env>;