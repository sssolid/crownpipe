"""
Custom exception hierarchy for CrownPipe.

All exceptions inherit from CrownPipeError for consistent error handling.
"""


class CrownPipeError(Exception):
    """Base exception for all CrownPipe errors."""
    
    def __init__(self, message: str, context: dict | None = None):
        self.message = message
        self.context = context or {}
        super().__init__(self.message)


class ConfigurationError(CrownPipeError):
    """Configuration-related errors (missing settings, invalid values)."""
    pass


class DatabaseError(CrownPipeError):
    """Database operation errors (connection, query, transaction)."""
    pass


class PipelineError(CrownPipeError):
    """Base for pipeline-specific errors."""
    pass


class MediaPipelineError(PipelineError):
    """Media pipeline errors."""
    pass


class DataPipelineError(PipelineError):
    """Data pipeline errors."""
    pass


class SyncPipelineError(PipelineError):
    """Sync pipeline errors."""
    pass


class FileProcessingError(PipelineError):
    """File processing errors (invalid format, corruption)."""
    pass


class ValidationError(CrownPipeError):
    """Input validation errors."""
    pass


class ExternalServiceError(CrownPipeError):
    """External service errors (FileMaker, AS400, S3)."""
    pass
