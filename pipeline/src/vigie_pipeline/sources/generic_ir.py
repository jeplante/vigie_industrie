"""Extraction déterministe générique, spécialisée par alias dans les adaptateurs."""

import re
from typing import ClassVar

from bs4 import BeautifulSoup

from vigie_pipeline.normalize import parse_french_number
from vigie_pipeline.sources.base import MetricCandidate


class GenericIrAdapter:
    company_id = "GENERIC"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {}

    def extract_metrics(self, content: str) -> list[MetricCandidate]:
        text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
        candidates: list[MetricCandidate] = []
        for metric_id, aliases in self.aliases.items():
            for alias in aliases:
                pattern = re.compile(
                    rf"(?P<context>.{{0,100}}{re.escape(alias)}.{{0,80}}?(?P<value>[−+-]?\d[\d\s]*(?:[,.]\d+)?\s*(?:G\$|M\$|\$|%)).{{0,100}})",
                    re.IGNORECASE,
                )
                match = pattern.search(text)
                if match is None:
                    continue
                value = parse_french_number(match.group("value"))
                if value is not None:
                    candidates.append(
                        MetricCandidate(
                            metric_id, alias, match.group("value"), value, match.group("context")
                        )
                    )
                    break
        return candidates
