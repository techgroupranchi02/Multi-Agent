"""
Aikyam Multi-Agent Pipeline — FastAPI Application
Main entry point for the backend server.
"""

from __future__ import annotations

import logging
import sys
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.api.review_routes import review_router, client_router
from src.config import get_settings
from src.integrations.jira_client import get_jira_client
from src.integrations.llm_provider import get_llm_manager
from src.integrations.slack_handler import get_slack_handler

# ── Logging Setup ──
try:
    sys.stdout.reconfigure(encoding='utf-8')  # type: ignore
    sys.stderr.reconfigure(encoding='utf-8')  # type: ignore
except AttributeError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-28s | %(levelname)-5s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Aikyam Multi-Agent Pipeline",
        description="API for the Multi-Agent SDLC Pipeline — From raw requirements to production",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ── CORS (allow frontend) ──
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
            "*",  # Allow all in dev
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ──
    app.include_router(router, prefix="/api")
    app.include_router(review_router)    # /api/review/* routes
    app.include_router(client_router)    # /api/client/* routes

    # ── Startup Event ──
    @app.on_event("startup")
    async def startup():
        logger.info("=" * 60)
        logger.info("  Aikyam Multi-Agent Pipeline — Starting")
        logger.info("=" * 60)

        # Initialize LLM providers
        try:
            llm = get_llm_manager()
            providers = llm.list_providers()
            logger.info("LLM Providers: %d configured", len(providers))
            for p in providers:
                logger.info("  • %s → %s", p["name"], p["model"])
        except Exception as e:
            logger.error("Failed to initialize LLM providers: %s", e)

        # Initialize Slack (non-blocking)
        try:
            slack = get_slack_handler()
            if slack.initialize():
                # Start Socket Mode in background thread
                thread = threading.Thread(target=slack.start_socket_mode, daemon=True)
                thread.start()
                logger.info("Slack Socket Mode started in background")
            else:
                logger.warning("Slack not configured — human approvals via dashboard only")
        except Exception as e:
            logger.warning("Slack initialization skipped: %s", e)

        # Initialize Jira (non-blocking)
        try:
            jira = get_jira_client()
            if jira.initialize():
                logger.info("Jira board: %s", jira.get_board_url())
            else:
                logger.warning("Jira not configured — tasks saved locally only")
        except Exception as e:
            logger.warning("Jira initialization skipped: %s", e)

        # Initialize RAG Knowledge Base (non-blocking)
        try:
            from src.integrations.rag_knowledge_base import get_rag_knowledge_base
            rag = get_rag_knowledge_base()
            if rag.initialize():
                logger.info("RAG Knowledge Base ready")
            else:
                logger.warning("RAG KB not initialized — PRD indexing disabled")
        except Exception as e:
            logger.warning("RAG initialization skipped: %s", e)

        logger.info("=" * 60)
        logger.info("  Server ready at http://%s:%d", settings.app_host, settings.app_port)
        logger.info("  API docs: http://localhost:%d/docs", settings.app_port)
        logger.info("=" * 60)

    @app.on_event("shutdown")
    async def shutdown():
        logger.info("Aikyam Pipeline — Shutting down")

    return app


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "src.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
