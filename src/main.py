"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import get_settings
from src.exceptions import (
    AgentError,
    BedrockRateLimitError,
    CalendarConflictError,
    CampusCopilotError,
    CogneeError,
    TUMSystemUnavailableError,
)
from src.lib.logging import get_logger, setup_logging

setup_logging(json_output=get_settings().environment == "production")
logger = get_logger(__name__)


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    application = FastAPI(
        title="Campus Co-Pilot",
        version="0.1.0",
        description="Multi-agent AI backend for TUM students",
    )

    settings = get_settings()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(application)
    _register_routes(application)

    return application


def _register_exception_handlers(application: FastAPI) -> None:
    """Map domain exceptions to HTTP status codes."""

    @application.exception_handler(BedrockRateLimitError)
    async def _bedrock_rate_limit(request: Request, exc: BedrockRateLimitError) -> JSONResponse:
        logger.warning("bedrock_rate_limited", path=request.url.path)
        return JSONResponse(status_code=429, content={"detail": "LLM rate limited, retry shortly"})

    @application.exception_handler(TUMSystemUnavailableError)
    async def _tum_unavailable(request: Request, exc: TUMSystemUnavailableError) -> JSONResponse:
        logger.error("tum_system_unavailable", path=request.url.path, exc_info=True)
        return JSONResponse(status_code=502, content={"detail": "TUM system unavailable"})

    @application.exception_handler(CalendarConflictError)
    async def _calendar_conflict(request: Request, exc: CalendarConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @application.exception_handler(CogneeError)
    async def _cognee_error(request: Request, exc: CogneeError) -> JSONResponse:
        logger.error("cognee_error", path=request.url.path, exc_info=True)
        return JSONResponse(status_code=502, content={"detail": "Memory system error"})

    @application.exception_handler(AgentError)
    async def _agent_error(request: Request, exc: AgentError) -> JSONResponse:
        logger.error("agent_error", path=request.url.path, exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Agent execution failed"})

    @application.exception_handler(CampusCopilotError)
    async def _domain_error(request: Request, exc: CampusCopilotError) -> JSONResponse:
        logger.error("domain_error", path=request.url.path, error=str(exc), exc_info=True)
        return JSONResponse(status_code=500, content={"detail": "Internal error"})


def _register_routes(application: FastAPI) -> None:
    """Register all API routers."""
    from src.api.chat import router as chat_router
    from src.api.cognify import router as cognify_router
    from src.api.health import router as health_router

    application.include_router(health_router)
    application.include_router(chat_router, prefix="/api")
    application.include_router(cognify_router)


app = create_app()
