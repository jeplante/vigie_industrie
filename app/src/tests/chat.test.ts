import { describe, expect, it, vi } from "vitest";
import { appendChatMessage, askVigie } from "../ui/chat";

describe("assistant Vigie", () => {
  it("sends selected context and reads a cited answer", async () => {
    const fetcher = vi.fn(async (_url: string, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toMatchObject({ question: "Compare le ROE", periodId: "2026-T2", companyId: "MFC" });
      return new Response(JSON.stringify({ answer: "Manuvie affiche un ROE de 16,3 %.", citations: [{ label: "Rapport", url: "https://example.com/report" }], caveat: null, model: "gpt-5.6-terra" }), { status: 200, headers: { "Content-Type": "application/json" } });
    });
    const response = await askVigie("https://chat.example.com", { question: "Compare le ROE", periodId: "2026-T2", companyId: "MFC", history: [] }, fetcher as typeof fetch);
    expect(response.model).toBe("gpt-5.6-terra"); expect(response.citations).toHaveLength(1);
  });
  it("renders text and secures source links", () => {
    const container = document.createElement("div"); appendChatMessage(container, "assistant", "Réponse", [{ label: "Source officielle", url: "https://example.com/report" }]);
    const link = container.querySelector("a")!; expect(container.textContent).toContain("Réponse"); expect(link.rel).toBe("noopener noreferrer"); expect(link.target).toBe("_blank");
  });
  it("rejects an unconfigured service", async () => {
    await expect(askVigie("", { question: "Question", periodId: null, companyId: "MFC", history: [] })).rejects.toThrow("pas encore configuré");
  });
});
