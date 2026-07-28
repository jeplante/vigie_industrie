import re
from typing import ClassVar

from bs4 import BeautifulSoup

from vigie_pipeline.sources.base import MetricCandidate
from vigie_pipeline.sources.generic_ir import GenericIrAdapter


class IaAdapter(GenericIrAdapter):
    company_id = "IAG"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA tiré des activités de base", "core EPS"),
        "core_earnings": (
            "résultat tiré des activités de base",
            "résultat des activités de base",
            "core earnings",
        ),
        "core_roe": ("rendement des capitaux propres de base", "core ROE"),
        "licat_ratio": ("ratio de solvabilité", "solvency ratio", "LICAT ratio"),
        "assets_under_administration": (
            "actif sous gestion et sous administration",
            "assets under management",
        ),
    }

    def extract_metrics(self, content: str) -> list[MetricCandidate]:
        text = re.sub(r"\s+", " ", BeautifulSoup(content, "html.parser").get_text(" ", strip=True))
        patterns: tuple[tuple[str, str, str, float], ...] = (
            ("core_eps", "core EPS", r"core eps.{0,60}?\$\s*(\d+(?:[.,]\d+)?)", 1.0),
            (
                "core_earnings",
                "core earnings",
                (
                    r"core earnings(?:\s*\([^)]*\))*"
                    r"(?:.{0,50}?\(in millions\)\s*|.{0,40}?\bof\s+\$\s*)"
                    r"([\d,]{2,5})\s*(?:million)?\b"
                ),
                0.001,
            ),
            (
                "core_roe",
                "core ROE",
                (
                    r"(?:trailing[- ]12[- ]month\s+core\s+roe"
                    r"|core return on common shareholders[’'] equity(?:\s*\(\s*roe\s*\))?)"
                    r".{0,40}?(\d{1,2}(?:[.,]\d+)?)\s*%"
                ),
                1.0,
            ),
            (
                "licat_ratio",
                "LICAT / solvency ratio",
                r"(?:solvency|licat) ratio.{0,40}?(\d{2,3})\s*%",
                1.0,
            ),
            (
                "assets_under_administration",
                "assets under administration",
                (
                    r"assets under management.{0,80}?assets under administration"
                    r".{0,180}?\$\s*(\d+(?:[.,]\d+)?)\s*billion"
                ),
                1.0,
            ),
        )
        candidates: list[MetricCandidate] = []
        for metric_id, label, pattern, multiplier in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match is None:
                continue
            parsed = float(match[1].replace(",", ".")) * multiplier
            if metric_id == "core_earnings":
                raw_value = f"{parsed:.3f} G$"
            elif metric_id in {"core_roe", "licat_ratio"}:
                raw_value = f"{parsed:g} %"
            elif metric_id == "assets_under_administration":
                raw_value = f"{parsed:g} G$"
            else:
                raw_value = f"{parsed:g} $"
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
