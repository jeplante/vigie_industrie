export interface ChatHistoryItem {
  role: "user" | "assistant";
  content: string;
}

export interface ChatRequest {
  question: string;
  periodId: string | null;
  companyId: string | null;
  history: ChatHistoryItem[];
}

export interface RouteConfig {
  model: string;
  effort: "low" | "medium";
}

const COMPLEX_TERMS = [
  "analyse", "compare", "comparaison", "explique", "pourquoi", "historique",
  "tendance", "évolution", "evolution", "risque", "synthèse", "synthese", "perspective",
];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function validateChatRequest(value: unknown): ChatRequest {
  if (!isRecord(value)) throw new Error("Requête invalide.");
  const question = typeof value.question === "string" ? value.question.trim() : "";
  if (question.length < 3 || question.length > 600) {
    throw new Error("La question doit contenir entre 3 et 600 caractères.");
  }
  const history = Array.isArray(value.history) ? value.history.slice(-6) : [];
  const validatedHistory: ChatHistoryItem[] = history.map((item) => {
    if (!isRecord(item) || (item.role !== "user" && item.role !== "assistant") ||
        typeof item.content !== "string" || item.content.length > 1_200) {
      throw new Error("L’historique de conversation est invalide.");
    }
    return { role: item.role, content: item.content };
  });
  return {
    question,
    periodId: typeof value.periodId === "string" ? value.periodId : null,
    companyId: typeof value.companyId === "string" ? value.companyId : null,
    history: validatedHistory,
  };
}

export function chooseRoute(question: string, historyLength: number, env: Env): RouteConfig {
  const normalized = question.toLocaleLowerCase("fr");
  const complex = historyLength >= 4 || question.length > 220 ||
    COMPLEX_TERMS.some((term) => normalized.includes(term));
  return complex
    ? { model: env.SOL_MODEL || "gpt-5.6-sol", effort: "medium" }
    : { model: env.TERRA_MODEL || "gpt-5.6-terra", effort: "low" };
}

type Dataset = Record<string, unknown> & {
  generatedAt?: unknown;
  companies?: unknown[];
  observations?: unknown[];
  news?: unknown[];
};

function compactObservation(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value) || !isRecord(value.period) || !isRecord(value.source)) return null;
  const comparison = isRecord(value.comparison) ? value.comparison : {};
  return {
    company: value.companyId, period: value.period.periodId, endDate: value.period.endDate,
    metric: value.metricId, label: value.label, value: value.value, unit: value.unit,
    display: value.displayValue, comparisonPeriod: comparison.periodId,
    change: comparison.displayChange, note: value.note,
    sourceTitle: value.source.title, sourceUrl: value.source.url,
  };
}

function compactNews(value: unknown): Record<string, unknown> | null {
  if (!isRecord(value) || !isRecord(value.source)) return null;
  return {
    companies: value.companyIds, date: value.publishedAt, title: value.title,
    summary: value.generatedSummary || value.originalSummary, sourceUrl: value.source.url,
  };
}

export function buildGroundingContext(dataset: Dataset, request: ChatRequest) {
  if (!Array.isArray(dataset.companies) || !Array.isArray(dataset.observations) || !Array.isArray(dataset.news)) {
    throw new Error("Les données publiées sont invalides.");
  }
  const observations = dataset.observations.map(compactObservation).filter(Boolean)
    .sort((a, b) => String(b!.endDate).localeCompare(String(a!.endDate)));
  const news = dataset.news.map(compactNews).filter(Boolean)
    .sort((a, b) => String(b!.date).localeCompare(String(a!.date))).slice(0, 40);
  return {
    generatedAt: dataset.generatedAt,
    selectedPeriod: request.periodId,
    selectedCompany: request.companyId,
    companies: dataset.companies,
    observations,
    recentNews: news,
  };
}

export function sourceAllowlist(context: ReturnType<typeof buildGroundingContext>): Set<string> {
  return new Set([...context.observations, ...context.recentNews]
    .map((item) => item?.sourceUrl).filter((url): url is string => typeof url === "string"));
}

export function parseStructuredAnswer(responsePayload: unknown, allowedSources: Set<string>) {
  if (!isRecord(responsePayload) || !Array.isArray(responsePayload.output)) throw new Error("Réponse OpenAI incomplète.");
  let outputText: string | null = null;
  for (const output of responsePayload.output) {
    if (!isRecord(output) || !Array.isArray(output.content)) continue;
    for (const content of output.content) {
      if (isRecord(content) && content.type === "output_text" && typeof content.text === "string") outputText = content.text;
    }
  }
  if (!outputText) throw new Error("Réponse OpenAI incomplète.");
  const parsed: unknown = JSON.parse(outputText);
  if (!isRecord(parsed) || typeof parsed.answer !== "string" || !Array.isArray(parsed.citations)) {
    throw new Error("Réponse OpenAI non conforme.");
  }
  const citations = parsed.citations.filter((citation) => isRecord(citation) &&
    typeof citation.label === "string" && typeof citation.url === "string" && allowedSources.has(citation.url))
    .slice(0, 6).map((citation) => ({ label: String(citation.label), url: String(citation.url) }));
  return { answer: parsed.answer, citations, caveat: typeof parsed.caveat === "string" ? parsed.caveat : null };
}

export const ANSWER_SCHEMA = {
  type: "object", additionalProperties: false,
  properties: {
    answer: { type: "string" },
    citations: { type: "array", maxItems: 6, items: { type: "object", additionalProperties: false,
      properties: { label: { type: "string" }, url: { type: "string" } }, required: ["label", "url"] } },
    caveat: { type: ["string", "null"] },
  },
  required: ["answer", "citations", "caveat"],
} as const;
