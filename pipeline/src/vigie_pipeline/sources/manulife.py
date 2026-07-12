from typing import ClassVar

from vigie_pipeline.sources.generic_ir import GenericIrAdapter


class ManulifeAdapter(GenericIrAdapter):
    company_id = "MFC"
    aliases: ClassVar[dict[str, tuple[str, ...]]] = {
        "core_eps": ("BPA tiré des activités de base", "core EPS"),
        "core_earnings": ("résultat tiré des activités de base", "core earnings"),
        "net_income": ("résultat net attribué aux actionnaires", "net income attributed"),
        "licat_ratio": ("ratio LICAT", "LICAT ratio"),
    }
