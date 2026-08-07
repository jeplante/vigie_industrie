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

interface PublishedValue {
  companyName: string;
  observation: Observation;
}

function publishedValuesForMetric(
  state: AppState,
  metricId: string,
): PublishedValue[] {
  return state.dataset.companies.flatMap((company) => {
    const observation = observationsForCompany(state, company.id).find(
      (item) => canonicalMetricId(item) === metricId,
    );
    return observation ? [{ companyName: company.name, observation }] : [];
  });
}

function answerForQuestion(
  state: AppState,
  question: string,
  periodLabel: string,
): { paragraphs: string[]; sources: Observation[] } {
  const selectedMetricId = metricForQuestion(question);

  if (selectedMetricId) {
    const published = publishedValuesForMetric(state, selectedMetricId);
    const unavailable = state.dataset.companies
      .filter((company) => !published.some((value) => value.companyName === company.name))
      .map((company) => company.name);
    const example = published[0]?.observation;
    const label = example ? canonicalMetricLabel(example) : "le KPI demandé";
    const values = published.map(
      ({ companyName, observation }) => `${companyName} : ${observation.displayValue}`,
    );
    const paragraphs = [
      `Indicateur analysé : ${label} — ${periodLabel}.`,
      published.length > 0
        ? `Valeurs publiées : ${values.join("; ")}.`
        : `Aucune valeur publiée pour ${label} à cette période.`,
    ];

    if (
      published.length >= 2 &&
      new Set(published.map(({ observation }) => observation.unit)).size === 1
    ) {
      const ranked = [...published].sort(
        (left, right) => right.observation.value - left.observation.value,
      );
      const leader = ranked[0]!;
      const trailing = ranked.at(-1)!;
      paragraphs.push(
        `${leader.companyName} affiche la valeur la plus élevée (${leader.observation.displayValue}), devant ${trailing.companyName} (${trailing.observation.displayValue}).`,
      );
    }

    if (published.length > 0) {
      paragraphs.push(
        `Évolution indiquée : ${published
          .map(
            ({ companyName, observation }) =>
              `${companyName} ${observation.comparison.displayChange} vs ${observation.comparison.periodLabel}`,
          )
          .join("; ")}.`,
      );
    }
    if (unavailable.length > 0) {
      paragraphs.push(`Donnée non publiée : ${unavailable.join(", ")}.`);
    }

    return { paragraphs, sources: published.map(({ observation }) => observation) };
  }

  const observations = state.dataset.companies.flatMap((company) =>
    observationsForCompany(state, company.id),
  );
  const availableMetrics = [
    ...new Set(observations.map(canonicalMetricLabel)),
  ];
  return {
    paragraphs: [
      `Je n’ai pas identifié de KPI précis dans « ${question} ». Pour ${periodLabel}, les indicateurs publiés comprennent : ${availableMetrics.join(", ") || "aucun"}.`,
      "Précisez le ROE, le BPA, le résultat net, la solvabilité ou les actifs pour une analyse comparative.",
    ],
    sources: [],
  };
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

  const period = state.dataset.periods.find(({ periodId }) => periodId === state.periodId);
  const periodLabel = period?.label ?? state.periodId ?? "Non publiée";
  const answer = element("div", { className: "chat-answer" });
  const response = answerForQuestion(state, question, periodLabel);
  answer.append(element("h3", { text: "Analyse fondée sur Vigie" }));
  for (const paragraph of response.paragraphs) {
    answer.append(element("p", { text: paragraph }));
  }
  if (response.sources.length > 0) {
    const sources = element("ul", { className: "chat-sources" });
    const uniqueSources = new Map(
      response.sources.map((item) => [item.source.url, item.source]),
    );
    for (const source of uniqueSources.values()) {
      const link = element("a", { text: source.title });
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const item = element("li");
      item.append(link);
      sources.append(item);
    }
    answer.append(element("h3", { text: "Sources officielles" }), sources);
  }

  container.append(title, intro, questionBox, answer);
}
