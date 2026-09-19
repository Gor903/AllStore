from typing import Annotated

from fastapi import Depends, Request

from app.core.errors import NotFoundError
from app.core.hosts import subdomain_from_host
from app.deps.auth import SessionDep, SettingsDep
from app.models import Store
from app.services import stores as stores_service


async def get_current_store(request: Request, settings: SettingsDep, session: SessionDep) -> Store:
    """Resolves the storefront a public request is addressed to, from the Host header.

    Only public storefront data hangs off this. Nothing a seller owns is ever resolved by
    Host — the dashboard reads the session — so a forged header cannot reach private data.
    """
    subdomain = subdomain_from_host(request.headers.get("host"), settings.base_domain)
    if subdomain is None or subdomain in settings.reserved_subdomains:
        raise NotFoundError("Магазин не найден")
    return await stores_service.get_public_store(session, subdomain)


CurrentStore = Annotated[Store, Depends(get_current_store)]
