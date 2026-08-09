import { describe, expect, it, vi } from "vitest";
import { appendChatMessage, appendChatPending, askVigie, bindChatSubmitShortcut } from "../ui/chat";

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
  it("aborts a request that exceeds the response deadline", async () => {
    const fetcher = vi.fn((_url: string, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    }));
    await expect(askVigie("https://chat.example.com", { question: "Question", periodId: null, companyId: "MFC", history: [] }, fetcher as typeof fetch, 5)).rejects.toThrow("trop de temps");
  });
  it("submits with Enter and keeps Shift+Enter for a new line", () => {
    const textarea = document.createElement("textarea");
    const form = document.createElement("form");
    const submit = vi.spyOn(form, "requestSubmit").mockImplementation(() => undefined);
    bindChatSubmitShortcut(textarea, form);
    const enter = new KeyboardEvent("keydown", { key: "Enter", cancelable: true });
    textarea.dispatchEvent(enter);
    expect(enter.defaultPrevented).toBe(true);
    expect(submit).toHaveBeenCalledOnce();
    const shiftEnter = new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, cancelable: true });
    textarea.dispatchEvent(shiftEnter);
    expect(shiftEnter.defaultPrevented).toBe(false);
    expect(submit).toHaveBeenCalledOnce();
  });
  it("renders a visible pending status", () => {
    const container = document.createElement("div");
    const pending = appendChatPending(container);
    expect(pending.textContent).toContain("Analyse en cours");
    expect(pending.getAttribute("role")).toBe("status");
  });
});
