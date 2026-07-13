"""Erreurs spécialisées du pipeline."""


class PipelineError(RuntimeError):
    """Erreur contrôlée qui doit être présentée sans trace sensible."""


class ConfigurationError(PipelineError):
    """Configuration absente ou invalide."""


class FetchError(PipelineError):
    """Échec borné de récupération d’une source."""


class ExtractionError(PipelineError):
    """Document récupéré, mais extraction non fiable."""


class DocumentNotIngestedError(ExtractionError):
    """Un document officiel daté a été découvert, mais n'a pas pu être intégré."""

    def __init__(self, message: str, *, period: object) -> None:
        super().__init__(message)
        self.period = period


class ValidationFailure(PipelineError):
    """Le candidat ne satisfait pas les règles de publication."""


class LlmError(PipelineError):
    """Erreur permanente ou réponse non conforme du fournisseur LLM."""


class TemporaryLlmError(LlmError):
    """Erreur LLM qui peut faire l’objet d’une reprise limitée."""


class LlmRefusalError(LlmError):
    """Claude a explicitement refusé la demande."""


class LlmIncompleteError(LlmError):
    """La réponse structurée est absente ou tronquée."""


class StructuredOutputUnsupportedError(LlmError):
    """Le modèle sélectionné ne prend pas en charge les Structured Outputs."""
