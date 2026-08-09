import type { CompanyId } from "../domain/models";

export interface ChatHistoryItem { role: "user" | "assistant"; content: string }
export interface ChatRequest { question: string; periodId: string | null; companyId: CompanyId; history: ChatHistoryItem[] }
export interface ChatCitation { label: string; url: string }
export interface ChatResponse { answer: string; citations: ChatCitation[]; caveat: string | null; model: string }

const DEFAULT_TIMEOUT_MS = 45_000;

export async function askVigie(endpoint: string, request: ChatRequest, fetcher: typeof fetch = fetch,
  timeoutMs = DEFAULT_TIMEOUT_MS): Promise<ChatResponse> {
  if (!endpoint) throw new Error("Le service de questions n’est pas encore configuré.");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetcher(endpoint, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request), signal: controller.signal });
    const payload = await response.json() as Partial<ChatResponse> & { error?: string };
    if (!response.ok) throw new Error(payload.error ?? "Le service de questions est temporairement indisponible.");
    if (typeof payload.answer !== "string" || !Array.isArray(payload.citations)) throw new Error("La réponse du service est invalide.");
    return { answer: payload.answer, citations: payload.citations, caveat: payload.caveat ?? null, model: payload.model ?? "OpenAI" };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("L’analyse prend trop de temps. Réessayez dans quelques instants.");
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

export function appendChatMessage(container: HTMLElement, role: "user" | "assistant" | "error", content: string,
  citations: ChatCitation[] = [], caveat: string | null = null): HTMLDivElement {
  const message = document.createElement("div"); message.className = `chat-message chat-message-${role}`;
  const paragraph = document.createElement("p"); paragraph.textContent = content; message.append(paragraph);
  if (citations.length) {
    const list = document.createElement("ul"); list.className = "chat-citations";
    for (const citation of citations) { const item = document.createElement("li"); const link = document.createElement("a");
      link.href = citation.url; link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = citation.label;
      item.append(link); list.append(item); }
    message.append(list);
  }
  if (caveat) { const warning = document.createElement("p"); warning.className = "chat-caveat"; warning.textContent = caveat; message.append(warning); }
  container.append(message); container.scrollTop = container.scrollHeight;
  return message;
}

export function appendChatPending(container: HTMLElement): HTMLDivElement {
  const message = appendChatMessage(container, "assistant", "Analyse en cours…");
  message.classList.add("chat-message-pending");
  message.setAttribute("role", "status");
  return message;
}

export function bindChatSubmitShortcut(textarea: HTMLTextAreaElement, form: HTMLFormElement): void {
  textarea.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    form.requestSubmit();
  });
}
