import re
from typing import ClassVar

from bs4 import BeautifulSoup

from vigie_pipeline.sources.base import MetricCandidate
from vigie_pipeline.sources.generic_ir import GenericIrAdapter


def _parse_number(value: str) -> float | None:
    compact = value.replace(" ", "")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", compact):
        return float(compact.replace(",", ""))
    if not re.fullmatch(r"\d+(?:[.,]\d+)?", compact):
        return None
    return float(compact.replace(",", "."))


class IaAdapter(GenericIrAdapter):
    company_id = "IAG"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA tiré des activités de base", "core EPS"),
        "core_earnings": (
            "résultat tiré des activités de base",
            "résultat des activités de base",
            "core earnings",
        ),
        "net_income": (
            "résultat net attribué aux actionnaires ordinaires",
            "net income attributed to common shareholders",
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
            (
                "core_eps",
                "core EPS",
                (
                    r"core eps(?:\s*\([^)]*\)|\s*[†‡*])*\s+"
                    r"(?:of\s+)?\$?\s*(\d+(?:[.,]\d+)?)"
                ),
                1.0,
            ),
            (
                "core_earnings",
                "core earnings",
                (
                    r"core earnings(?:\s*[†‡*]|\s*\([^)]*\))*\s*"
                    r"(?:\(\s*in millions\s*\)\s*)?(?:of\s+)?\$?\s*"
                    r"([\d,]{2,5})\s*(?:million)?\b"
                ),
                0.001,
            ),
            (
                "net_income",
                "net income attributed to common shareholders",
                (
                    r"net income attributed to common shareholders"
                    r"(?:\s*\([^)]*\))*\s*(?:was\s+|of\s+)?\$?\s*"
                    r"([\d,]+)\s*(?:million)?\b"
                ),
                0.001,
            ),
            (
                "core_roe",
                "core ROE",
                (
                    r"(?:trailing[- ]12[- ]month\s+core\s+roe"
                    r"|core\s+roe(?:\s*[†‡*])*(?:\s*\([^)]*\))?"
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
                    r"(?:total\s+)?assets under management(?:\s*\d+)?"
                    r"(?:\s+and\s+(?:assets under administration|administration)"
                    r"(?:\s*\d+)?)?.{0,120}?\$\s*(\d+(?:[.,]\d+)?)"
                    r"(?:\s*billion)?"
                ),
                1.0,
            ),
        )
        candidates: list[MetricCandidate] = []
        for metric_id, label, pattern, multiplier in patterns:
            match = None
            parsed_number = None
            for candidate_match in re.finditer(pattern, text, re.IGNORECASE):
                candidate_number = _parse_number(candidate_match[1])
                if candidate_number is None:
                    continue
                if metric_id == "core_earnings" and candidate_number < 100:
                    continue
                match = candidate_match
                parsed_number = candidate_number
                break
            if match is None or parsed_number is None:
                continue
            parsed = parsed_number * multiplier
            if metric_id in {"core_earnings", "net_income"}:
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
