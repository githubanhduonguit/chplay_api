"""
FastAPI application entry point.

Configures the app with:
- API routers
- Global exception handlers
- CORS middleware
- Lifespan events for startup/shutdown
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


# ── Logging setup ────────────────────────────────────────────────────
# Uvicorn only configures its own loggers (uvicorn.* with propagate=False)
# and leaves the root logger at WARNING, so application logs (app.*)
# would be silently dropped. Ensure the root logger is visible no matter
# how the app is launched (uvicorn or plain scripts).
def _ensure_root_logging() -> None:
    log_level = getattr(logging, str(settings.LOG_LEVEL).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(log_level)
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"),
        )
        root.addHandler(handler)


_ensure_root_logging()

# ── API routers ──────────────────────────────────────────────────────

try:
    from app.api.routes.apps import router as apps_router
except Exception as e:
    print(f"Warning: Failed to import apps router: {e}")
    apps_router = None

from app.api.v1.documents import router as documents_router
from app.api.routes.tickets import router as tickets_router

from app.services.queue.queue import review_job_queue
from app.services.queue.ticket_queue import ticket_proposal_queue
from app.services.queue.ticket_worker import TicketProposalQueueWorker
from app.services.queue.worker import ReviewQueueWorker

# Module-level worker references so the lifespan shutdown can stop them.
review_worker: ReviewQueueWorker | None = None
ticket_worker: TicketProposalQueueWorker | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks."""
    # Startup: ensure required directories exist
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    settings.data_path.mkdir(parents=True, exist_ok=True)

    # Startup: start the review queue worker
    global review_worker, ticket_worker
    review_worker = ReviewQueueWorker(review_job_queue)
    review_task = asyncio.create_task(review_worker.start())
    logger.info(
        "Review queue worker started (queue size=%d)",
        review_job_queue.size(),
    )

    # Startup: start the ticket proposal queue worker (async ticket creation
    # right after an admin approves a proposal — no polling scheduler).
    ticket_worker = TicketProposalQueueWorker(ticket_proposal_queue)
    ticket_task = asyncio.create_task(ticket_worker.start())
    logger.info(
        "Ticket proposal queue worker started (queue size=%d)",
        ticket_proposal_queue.size(),
    )

    yield

    # Shutdown: stop the review queue worker
    if review_worker is not None:
        await review_worker.stop()
        review_task.cancel()
        await asyncio.gather(review_task, return_exceptions=True)
        logger.info("Review queue worker stopped.")

    # Shutdown: stop the ticket proposal queue worker
    if ticket_worker is not None:
        await ticket_worker.stop()
        ticket_task.cancel()
        await asyncio.gather(ticket_task, return_exceptions=True)
        logger.info("Ticket proposal queue worker stopped.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Backend API for document management, AI-powered search, and retrieval-augmented generation.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────

if apps_router:
    app.include_router(apps_router)
app.include_router(documents_router, prefix="/api/v1")
app.include_router(tickets_router, prefix="/api/v1")


# ── Global Exception Handlers ────────────────────────────────────────


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Handle all application-level errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """Handle SQLAlchemy/database errors."""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "DATABASE_ERROR",
                "message": "A database error occurred",
                "details": {"type": type(exc).__name__},
            }
        },
    )


@app.exception_handler(Exception)
async def global_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for all unhandled exceptions."""
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An internal server error occurred",
                "details": {"type": type(exc).__name__} if settings.DEBUG else {},
            }
        },
    )


# ── Health Check ─────────────────────────────────────────────────────


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """Simple health check endpoint."""
    return {
        "status": "ok",
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }
