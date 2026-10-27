from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.accounts import router as accounts_router
from app.api.admin import router as admin_router
from app.api.assistant import router as assistant_router
from app.api.auth import router as auth_router
from app.api.catalog import router as catalog_router
from app.api.contacts import router as contacts_router
from app.api.health import router as health_router
from app.api.moderation import router as moderation_router
from app.api.products import router as products_router
from app.api.reports import public_router as reports_public_router
from app.api.reports import router as reports_router
from app.api.storefront import router as storefront_router
from app.api.stores import router as stores_router
from app.api.users import router as users_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.storage import ensure_bucket
from app.db.session import dispose_engine
from app.deps.rate_limit import build_invitation_limiter

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    await ensure_bucket(settings)
    logger.info("backend started in %s mode", settings.app_env)
    yield
    await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="AllStore API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.is_local else None,
        redoc_url=None,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # per application, so every worker keeps its own tally — see app/core/rate_limit.py
    app.state.invitation_limiter = build_invitation_limiter()

    register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(users_router, prefix=settings.api_prefix)
    app.include_router(stores_router, prefix=settings.api_prefix)
    app.include_router(contacts_router, prefix=settings.api_prefix)
    app.include_router(products_router, prefix=settings.api_prefix)
    app.include_router(moderation_router, prefix=settings.api_prefix)
    app.include_router(storefront_router, prefix=settings.api_prefix)
    app.include_router(catalog_router, prefix=settings.api_prefix)
    app.include_router(assistant_router, prefix=settings.api_prefix)
    app.include_router(admin_router, prefix=settings.api_prefix)
    app.include_router(accounts_router, prefix=settings.api_prefix)
    app.include_router(reports_public_router, prefix=settings.api_prefix)
    app.include_router(reports_router, prefix=settings.api_prefix)
    return app


app = create_app()
