import re
from typing import ClassVar

from bs4 import BeautifulSoup

from vigie_pipeline.sources.base import MetricCandidate
from vigie_pipeline.sources.generic_ir import GenericIrAdapter


class ManulifeAdapter(GenericIrAdapter):
    company_id = "MFC"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA tiré des activités de base", "core EPS"),
        "core_earnings": ("résultat tiré des activités de base", "core earnings"),
        "net_income": ("résultat net attribué aux actionnaires", "net income attributed"),
        "core_roe": ("rendement des capitaux propres de base", "core ROE"),
        "licat_ratio": ("ratio LICAT", "LICAT ratio"),
    }

    def extract_metrics(self, content: str) -> list[MetricCandidate]:
        text = re.sub(r"\s+", " ", BeautifulSoup(content, "html.parser").get_text(" ", strip=True))
        patterns: tuple[tuple[str, str, str, float, str], ...] = (
            (
                "core_eps",
                "core EPS",
                r"core eps\s*\(\s*\$\s*\)\s*\$\s*(\d+(?:[.,]\d+)?)",
                1.0,
                "$",
            ),
            (
                "core_earnings",
                "core earnings",
                r"core earnings\s*\$\s*([\d,]+)",
                0.001,
                "G$",
            ),
            (
                "net_income",
                "net income attributed to shareholders",
                r"net income attributed to shareholders\s*\$\s*([\d,]+)",
                0.001,
                "G$",
            ),
            (
                "core_roe",
                "core ROE",
                (
                    r"(?:core roe|roe (?:tirÃ© des activitÃ©s )?de base)"
                    r"(?:\s*\d+|\s*\([^)]*\))*\s+(?:of\s+|Ã©tait de\s+)?"
                    r"(\d{1,2}(?:[.,]\d+)?)\s*%"
                ),
                1.0,
                "%",
            ),
            (
                "licat_ratio",
                "LICAT ratio",
                r"licat ratio(?:\s*\d+|\s*\([^)]*\))*\s+of\s+(\d{2,3})\s*%",
                1.0,
                "%",
            ),
        )
        candidates: list[MetricCandidate] = []
        for metric_id, label, pattern, multiplier, suffix in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
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
