from typing import ClassVar

from vigie_pipeline.sources.generic_ir import GenericIrAdapter


class GreatWestAdapter(GenericIrAdapter):
    company_id = "GWO"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA de base", "base earnings per share"),
        "core_earnings": ("bénéfice de base", "base earnings"),
        "licat_ratio": ("ratio LICAT", "LICAT ratio"),
        "total_client_assets": ("actifs clients totaux", "total assets under administration"),
    }
