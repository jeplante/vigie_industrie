import re
from typing import ClassVar

from bs4 import BeautifulSoup

from vigie_pipeline.sources.base import MetricCandidate
from vigie_pipeline.sources.generic_ir import GenericIrAdapter


class GreatWestAdapter(GenericIrAdapter):
    company_id = "GWO"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA de base", "base earnings per share"),
        "core_earnings": ("bénéfice de base", "base earnings"),
        "licat_ratio": ("ratio LICAT", "LICAT ratio"),
        "total_client_assets": ("actifs clients totaux", "total assets under administration"),
    }

    def extract_metrics(self, content: str) -> list[MetricCandidate]:
        text = re.sub(r"\s+", " ", BeautifulSoup(content, "html.parser").get_text(" ", strip=True))
        patterns: tuple[tuple[str, str, str, float, str], ...] = (
            (
                "core_eps",
                "base EPS",
                r"base eps.{0,80}?\$\s*(\d+(?:[.,]\d+)?)",
                1.0,
                "$",
            ),
            (
                "core_earnings",
                "base earnings",
                r"base earnings.{0,100}?\$\s*([\d,]+)\s*(?:million)?",
                0.001,
                "G$",
            ),
            (
                "licat_ratio",
                "LICAT ratio",
                r"licat ratio.{0,100}?(\d{2,3})\s*%",
                1.0,
                "%",
            ),
            (
                "total_client_assets",
                "total client assets",
                (
                    r"(?:total client assets|total assets under administration)"
                    r".{0,120}?\$\s*(\d+(?:[.,]\d+)?)\s*trillion"
                ),
                1.0,
                "T$",
            ),
        )
        candidates: list[MetricCandidate] = []
        for metric_id, label, pattern, multiplier, suffix in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match is None:
                continue
            parsed = float(match[1].replace(",", "")) * multiplier
            raw_value = f"{parsed:g} {suffix}"
            candidates.append(
                MetricCandidate(
                    metric_id=metric_id,
                    label=label,
                    raw_value=raw_value,
                    value=parsed,
                    context=match.group(0)[:500],
                )
            )
        return candidates
