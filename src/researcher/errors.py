"""Exception types that drive retry and failure handling."""


class ResearchError(Exception):
    """Base class for all errors raised by the research pipeline."""


class TransientError(ResearchError):
    """A failure that may succeed if the same work is attempted again."""


class PermanentError(ResearchError):
    """A failure that retrying cannot fix (bad input, integrity violation)."""


class RoutingError(PermanentError):
    """No agent is registered for a task kind."""


class ModelOutputError(TransientError):
    """A language model returned output that could not be parsed or validated."""
