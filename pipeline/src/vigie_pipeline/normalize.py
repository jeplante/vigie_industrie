"""Normalisation déterministe des nombres et comparatifs."""

import re

NUMBER_PATTERN = re.compile(r"-?\d[\d\s\u00a0]*(?:[,.]\d+)?")


def parse_french_number(value: str) -> float | None:
    """Lit le premier nombre français sans inférer une valeur absente."""

    normalized = value.replace("−", "-")
    match = NUMBER_PATTERN.search(normalized)
    if match is None:
        return None
    return float(match.group(0).replace("\u00a0", "").replace(" ", "").replace(",", "."))


def calculate_change(current: float, previous: float) -> float | None:
    """Retourne la variation relative; zéro au dénominateur reste ambigu."""

    if previous == 0:
        return None
    return (current - previous) / abs(previous)


def direction_for(current: float, previous: float, tolerance: float = 1e-9) -> str:
    difference = current - previous
    if abs(difference) <= tolerance:
        return "neutral"
    return "up" if difference > 0 else "down"
