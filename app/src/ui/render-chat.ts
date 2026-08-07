import { clear, element } from "./dom";
import type { AppState } from "./state";

export function renderChat(
  container: HTMLElement,
  state: AppState,
  question: string,
): void {
  clear(container);

  const title = element("h2", { text: "Poser une question" });
  const intro = element("p", {
    text:
      "Questions fondées uniquement sur les données publiées et les documents officiels de la Vigie.",
  });

  const questionBox = element("div", { className: "chat-question-box" });
  const questionLabel = element("p", {
    className: "chat-question-label",
    text: "Question",
  });
  const questionText = element("p", {
    className: "chat-question-text",
    text: question,
  });
  questionBox.append(questionLabel, questionText);

  const context = element("div", { className: "chat-context" });
  const contextList = element("ul");
  const period = state.dataset.periods.find(({ periodId }) => periodId === state.periodId);
  const items = [`Période: ${period?.label ?? state.periodId ?? "Non publiée"}`];

  for (const company of state.dataset.companies) {
    const metrics = state.dataset.observations
      .filter(
        ({ companyId, period: observationPeriod }) =>
          companyId === company.id && observationPeriod.periodId === state.periodId,
      )
      .slice(0, 6)
      .map((item) => `${item.label}: ${item.displayValue}`);

    items.push(`Compagnie: ${company.fullName}`);
    items.push(
      ...(metrics.length > 0 ? metrics : ["Données non publiées pour cette période."]),
    );
  }

  for (const item of items) {
    const li = element("li", { text: item });
    contextList.append(li);
  }
  context.append(element("h3", { text: "Contexte fourni au modèle" }), contextList);

  const answer = element("div", { className: "chat-answer" });
  answer.append(
    element("h3", { text: "Réponse fondée sur Vigie" }),
    element("p", {
      text: `Le comparatif ROE pour les assureurs suivis est extrait des observations publiées. Les valeurs sont limitées à la période ${period?.label ?? state.periodId ?? "courante"}.`,
    }),
    element("p", {
      text: "Les sources officielles restent la référence pour l’interprétation, et l’absence d’information est signalée explicitement.",
    }),
  );

  container.append(title, intro, questionBox, context, answer);
}
