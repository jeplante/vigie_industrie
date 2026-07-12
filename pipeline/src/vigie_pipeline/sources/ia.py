from typing import ClassVar

from vigie_pipeline.sources.generic_ir import GenericIrAdapter


class IaAdapter(GenericIrAdapter):
    company_id = "IAG"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA tiré des activités de base", "core EPS"),
        "core_earnings": ("résultat tiré des activités de base", "core earnings"),
        "solvency_ratio": ("ratio de solvabilité", "solvency ratio"),
        "assets_under_administration": (
            "actif sous gestion et sous administration",
            "assets under management",
        ),
    }
