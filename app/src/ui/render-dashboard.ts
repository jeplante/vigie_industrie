import type { AppState } from "./state";
import { renderMetrics } from "./render-metrics";
import { renderNews } from "./render-news";
import { clear, element, requiredElement } from "./dom";
import { formatDate } from "../formatters/date";

export function renderDashboard(state: AppState): void {
  const company = state.dataset.companies.find(
    ({ id }) => id === state.companyId,
  );
  if (!company) throw new Error(`Compagnie inconnue: ${state.companyId}`);
  const period = state.dataset.periods.find(
    ({ periodId }) => periodId === state.periodId,
  );

  const header = requiredElement<HTMLDivElement>("company-header");
  clear(header);
  const titleWrap = element("div");
  titleWrap.append(
    element("p", { className: "eyebrow", text: company.fullName }),
    element("h2", {
      text: period
        ? `${company.name} · ${period.label}`
        : `${company.name} · Données non encore publiées`,
    }),
  );
  const irLink = element("a", {
    className: "button",
    text: "Relations investisseurs",
  });
  irLink.href = company.investorRelationsUrl;
  irLink.target = "_blank";
  irLink.rel = "noopener noreferrer";
  header.append(titleWrap, irLink);

  renderMetrics(
    requiredElement("metrics"),
    state.dataset.observations.filter(
      ({ companyId, period: observationPeriod }) =>
        companyId === state.companyId &&
        observationPeriod.periodId === state.periodId,
    ),
  );
  const companyNews = state.dataset.news
    .filter((item) => item.companyIds.includes(state.companyId))
    .sort((left, right) => right.publishedAt.localeCompare(left.publishedAt));
  const latestNews = companyNews[0];
  requiredElement("news-freshness").textContent = latestNews
    ? `Dernière actualité recensée : ${formatDate(latestNews.publishedAt)}`
    : "Aucune actualité recensée.";
  renderNews(
    requiredElement("news"),
    companyNews.filter(
      (item) =>
        state.category === "all" || item.categories.includes(state.category),
    ),
  );
  requiredElement("company-panel").setAttribute(
    "aria-labelledby",
    `company-tab-${company.id}`,
  );
}
