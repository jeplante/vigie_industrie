from typing import ClassVar

from vigie_pipeline.sources.generic_ir import GenericIrAdapter


class SunLifeAdapter(GenericIrAdapter):
    company_id = "SLF"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA sous-jacent", "underlying EPS"),
        "net_income": ("résultat net sous-jacent", "underlying net income"),
        "licat_ratio": ("ratio LICAT", "LICAT ratio"),
        "assets_under_management": ("actif sous gestion", "assets under management"),
    }
