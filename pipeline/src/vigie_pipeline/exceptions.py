"""Erreurs spécialisées du pipeline."""


class PipelineError(RuntimeError):
    """Erreur contrôlée qui doit être présentée sans trace sensible."""


class ConfigurationError(PipelineError):
    """Configuration absente ou invalide."""


class FetchError(PipelineError):
    """Échec borné de récupération d’une source."""


class ExtractionError(PipelineError):
    """Document récupéré, mais extraction non fiable."""


class ValidationFailure(PipelineError):
    """Le candidat ne satisfait pas les règles de publication."""


class LlmError(PipelineError):
    """Erreur permanente ou réponse non conforme du fournisseur LLM."""


class TemporaryLlmError(LlmError):
    """Erreur LLM qui peut faire l’objet d’une reprise limitée."""
