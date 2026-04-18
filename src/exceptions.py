"""Domain-specific exceptions for Campus Co-Pilot."""

from __future__ import annotations


class CampusCopilotError(Exception):
    """Base exception for all domain errors."""


# --- Bedrock / LLM ---


class BedrockError(CampusCopilotError):
    """Base for Bedrock-related failures."""


class BedrockRateLimitError(BedrockError):
    """Bedrock throttling — caller should back off."""


class BedrockModelError(BedrockError):
    """Model returned an unusable response."""


# --- TUM Systems ---


class TUMSystemError(CampusCopilotError):
    """Base for TUM external system failures."""


class TUMSystemUnavailableError(TUMSystemError):
    """External TUM system is unreachable or returned 5xx."""


class TUMAuthenticationError(TUMSystemError):
    """TUM credentials are invalid or expired."""


# --- Cognee ---


class CogneeError(CampusCopilotError):
    """Base for Cognee memory layer failures."""


class CogneeRetrievalError(CogneeError):
    """Failed to retrieve from the knowledge graph."""


class CogneeIngestionError(CogneeError):
    """Failed to ingest data into the knowledge graph."""


class ContentGenerationError(CogneeError):
    """Failed to generate learning content from the knowledge graph."""


class QuizNotFoundError(CampusCopilotError):
    """Requested quiz content not found on S3."""


# --- S3 / Storage ---


class S3Error(CampusCopilotError):
    """Base for S3 storage failures."""


class S3UploadError(S3Error):
    """Failed to upload a file to S3."""


# --- Calendar ---


class CalendarError(CampusCopilotError):
    """Base for calendar-related failures."""


class CalendarNotConnectedError(CalendarError):
    """Student hasn't connected Google Calendar yet."""


class CalendarConflictError(CalendarError):
    """Proposed booking conflicts with an existing event."""


# --- Jobs ---


class JobSearchError(CampusCopilotError):
    """Job search API call failed."""


# --- Agent ---


class AgentError(CampusCopilotError):
    """Base for agent execution failures."""


class AgentToolError(AgentError):
    """A tool invoked by an agent failed."""

    def __init__(self, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.recoverable = recoverable

    def to_dict(self) -> dict[str, object]:
        """Structured error for LLM consumption."""
        return {"error": str(self), "recoverable": self.recoverable}
