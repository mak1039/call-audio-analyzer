class DomainError(Exception):
    """Base class for every error the domain raises."""


class InvalidAnalysisResultError(DomainError):
    """An analysis result violates the output contract."""


class BatchNotFoundError(DomainError):
    """No batch exists for the requested identifier."""


class ManifestError(DomainError):
    """The CSV manifest is structurally unusable."""


class CorruptArchiveError(DomainError):
    """The uploaded archive could not be read."""
