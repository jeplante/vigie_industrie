import { clear, element } from "./dom";
import {
  canonicalMetricId,
  canonicalMetricLabel,
  canonicalObservations,
} from "../domain/metric-aliases";
import type { Observation } from "../domain/models";
import type { AppState } from "./state";

const QUESTION_METRICS: Array<{ metricId: string; terms: RegExp }> = [
  { metricId: "core_roe", terms: /\broe\b|rendement des capitaux propres/u },
  { metricId: "core_eps", terms: /\bbpa\b|benefice par action/u },
  {
    metricId: "core_earnings",
    terms: /core earnings|activites de base|resultat des activites de base/u,
  },
  { metricId: "net_income", terms: /resultat net|benefice net/u },
  { metricId: "licat_ratio", terms: /licat|solvabilite/u },
  {
    metricId: "assets_managed_or_administered",
    terms: /actifs?|gestion|administration/u,
  },
];

function normalize(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

function metricForQuestion(question: string): string | undefined {
  const normalizedQuestion = normalize(question);
  return QUESTION_METRICS.find(({ terms }) => terms.test(normalizedQuestion))?.metricId;
}

function observationsForCompany(state: AppState, companyId: string): Observation[] {
  return canonicalObservations(
    state.dataset.observations.filter(
      ({ companyId: observationCompanyId, period }) =>
        observationCompanyId === companyId && period.periodId === state.periodId,
    ),
  );
}

function answerForQuestion(state: AppState, question: string, periodLabel: string): string[] {
  const selectedMetricId = metricForQuestion(question);
  const observationsByCompany = state.dataset.companies.map((company) => ({
    company,
    observations: observationsForCompany(state, company.id),
  }));

  if (selectedMetricId) {
    const values = observationsByCompany.map(({ company, observations }) => {
      const observation = observations.find(
        (item) => canonicalMetricId(item) === selectedMetricId,
      );
      return observation
        ? `${company.name} : ${observation.displayValue}`
        : `${company.name} : donnée non publiée`;
    });
    const example = observationsByCompany
      .flatMap(({ observations }) => observations)
      .find((item) => canonicalMetricId(item) === selectedMetricId);
    const label = example ? canonicalMetricLabel(example) : "le KPI demandé";

    return [
      `Pour ${label} à ${periodLabel}, ${values.join("; ")}.`,
      "Cette synthèse reprend exclusivement les valeurs publiées; une absence ne doit pas être interprétée comme une valeur nulle.",
    ];
  }

  const availableMetrics = [
    ...new Set(
      observationsByCompany.flatMap(({ observations }) =>
        observations.map(canonicalMetricLabel),
      ),
    ),
  ];
  return [
    `Je n’ai pas identifié de KPI précis dans « ${question} ». Pour ${periodLabel}, les KPI publiés comprennent : ${availableMetrics.join(", ") || "aucun"}.`,
    "Précisez par exemple le ROE, le BPA, le résultat net, la solvabilité ou les actifs pour obtenir un comparatif chiffré.",
  ];
}

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
  const periodLabel = period?.label ?? state.periodId ?? "Non publiée";
  const items = [`Période: ${periodLabel}`];

  for (const company of state.dataset.companies) {
    const metrics = observationsForCompany(state, company.id).map(
      (item) =>
        `${canonicalMetricLabel(item)}: ${item.displayValue} (${item.comparison.displayChange} vs ${item.comparison.periodLabel}). Source : ${item.source.title}.`,
    );

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
  answer.append(element("h3", { text: "Réponse fondée sur Vigie" }));
  for (const paragraph of answerForQuestion(state, question, periodLabel)) {
    answer.append(element("p", { text: paragraph }));
  }

  container.append(title, intro, questionBox, context, answer);
}
