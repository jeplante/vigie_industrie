import { describe, expect, it } from "vitest";
import { buildGroundingContext, chooseRoute, parseStructuredAnswer, validateChatRequest } from "../src/router";

const env = { TERRA_MODEL: "gpt-5.6-terra", SOL_MODEL: "gpt-5.6-sol" } as Env;

describe("chat routing and grounding", () => {
  it("routes simple questions to Terra and analysis to Sol", () => {
    expect(chooseRoute("Quel est le ROE de Manuvie?", 0, env).model).toBe("gpt-5.6-terra");
    expect(chooseRoute("Compare la tendance historique du ROE", 0, env).model).toBe("gpt-5.6-sol");
  });

  it("validates and caps history", () => {
    const request = validateChatRequest({ question: " Compare les assureurs ", periodId: "2026-T2", companyId: "MFC",
      history: Array.from({ length: 8 }, (_, index) => ({ role: index % 2 ? "assistant" : "user", content: `message ${index}` })) });
    expect(request.question).toBe("Compare les assureurs");
    expect(request.history).toHaveLength(6);
  });

  it("builds context and rejects invented citations", () => {
    const context = buildGroundingContext({ generatedAt: "2026-08-07T00:00:00Z",
      companies: [{ id: "MFC", name: "Manuvie" }], news: [], observations: [{ companyId: "MFC",
        period: { periodId: "2026-T2", endDate: "2026-06-30" }, metricId: "core_roe", label: "ROE",
        value: 16.3, unit: "PERCENT", displayValue: "16,3 %", comparison: { periodId: "2025-T2", displayChange: "+1,3 pp" },
        source: { title: "Rapport T2", url: "https://example.com/t2" } }] },
      { question: "Question", periodId: "2026-T2", companyId: "MFC", history: [] });
    expect(context.observations[0]?.sourceUrl).toBe("https://example.com/t2");
    const payload = { output: [{ content: [{ type: "output_text", text: JSON.stringify({ answer: "Réponse",
      citations: [{ label: "Valide", url: "https://example.com/t2" }, { label: "Inventée", url: "https://evil.test" }], caveat: null }) }] }] };
    expect(parseStructuredAnswer(payload, new Set(["https://example.com/t2"])).citations).toEqual([{ label: "Valide", url: "https://example.com/t2" }]);
  });
});
