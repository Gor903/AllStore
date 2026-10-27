from fastapi import APIRouter

from app.deps.auth import OptionalUser, SessionDep, viewer_id_of
from app.deps.tenant import CurrentStore
from app.schemas.store import StorefrontRead, Subdomain
from app.services import customer_blocks
from app.services import stores as stores_service

router = APIRouter(prefix="/storefront", tags=["storefront"])


@router.get("", response_model=StorefrontRead)
async def read_storefront_by_host(
    store: CurrentStore, session: SessionDep, viewer: OptionalUser = None
) -> StorefrontRead:
    """How a browser reaches a storefront: the subdomain it typed is the Host header."""
    await customer_blocks.ensure_may_see(session, store.business_id, viewer_id_of(viewer))
    return StorefrontRead.from_store(store)


@router.get("/{subdomain}", response_model=StorefrontRead)
async def read_storefront(
    subdomain: Subdomain, session: SessionDep, viewer: OptionalUser = None
) -> StorefrontRead:
    """The same data addressed explicitly, for callers that cannot set a Host header.

    Server-side rendering is one: Node's fetch replaces a Host header with the authority
    of the URL it dials, and the frontend dials the backend over the internal network.
    """
    store = await stores_service.get_public_store(session, subdomain, viewer_id_of(viewer))
    return StorefrontRead.from_store(store)
