import re
from typing import ClassVar

from bs4 import BeautifulSoup

from vigie_pipeline.sources.base import MetricCandidate
from vigie_pipeline.sources.generic_ir import GenericIrAdapter


class SunLifeAdapter(GenericIrAdapter):
    company_id = "SLF"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA sous-jacent", "underlying EPS"),
        "net_income": ("résultat net sous-jacent", "underlying net income"),
        "core_roe": ("rendement des capitaux propres sous-jacent", "underlying ROE"),
        "licat_ratio": ("ratio LICAT", "LICAT ratio"),
        "assets_under_management": ("actif sous gestion", "assets under management"),
    }

    def extract_metrics(self, content: str) -> list[MetricCandidate]:
        text = re.sub(r"\s+", " ", BeautifulSoup(content, "html.parser").get_text(" ", strip=True))
        annual_core_roe = re.search(
            (
                r"underlying return on equity.{0,80}?\d{1,2}(?:[.,]\d+)?\s*%"
                r".{0,40}?full year\s*[-â€“]\s*(\d{1,2}(?:[.,]\d+)?)\s*%"
            ),
            text,
            re.IGNORECASE,
        )
        patterns: tuple[tuple[str, str, str, float, str], ...] = (
            (
                "core_eps",
                "underlying EPS",
                (
                    r"underlying eps(?:\s*\([^)]*\))*\s+of\s+"
                    r"\$\s*(\d+(?:[.,]\d+)?)"
                ),
                1.0,
                "$",
            ),
            (
                "net_income",
                "underlying net income",
                (
                    r"underlying net income(?:\s*\([^)]*\))*\s+of\s+"
                    r"\$\s*([\d,]+)\s+million"
                ),
                0.001,
                "G$",
            ),
            (
                "core_roe",
                "underlying ROE",
                (
                    r"(?:underlying return on equity(?:\s*\(\s*[\"“]?\s*roe[\"”]?\s*\))?"
                    r"|underlying roe)(?:\s*\([^)]*\))*\s+(?:was\s+|of\s+)?"
                    r"(\d{1,2}(?:[.,]\d+)?)\s*%"
                ),
                1.0,
                "%",
            ),
            (
                "licat_ratio",
                "LICAT ratio",
                r"licat ratio(?:\s*\([^)]*\))*\s+(?:of\s+)?(\d{2,3})\s*%",
                1.0,
                "%",
            ),
            (
                "assets_under_management",
                "assets under management",
                (
                    r"assets under management(?:\s*\([^)]*\))*\s+of\s+"
                    r"\$\s*([\d,]+)\s+billion"
                ),
                1.0,
                "G$",
            ),
        )
        candidates: list[MetricCandidate] = []
        for metric_id, label, pattern, multiplier, suffix in patterns:
            match = (
                annual_core_roe
                if metric_id == "core_roe" and annual_core_roe is not None
                else re.search(pattern, text, re.IGNORECASE)
            )
            if match is None:
                continue
            parsed = float(match[1].replace(",", "")) * multiplier
            candidates.append(
                MetricCandidate(
                    metric_id=metric_id,
                    label=label,
                    raw_value=f"{parsed:g} {suffix}",
                    value=parsed,
                    context=match.group(0)[:500],
                )
            )

        found = {candidate.metric_id for candidate in candidates}
        candidates.extend(
            candidate
            for candidate in super().extract_metrics(content)
            if candidate.metric_id not in found
        )
        return candidates
