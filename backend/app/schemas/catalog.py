import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.models import Category, Product, ProductAvailability, Store

# Nothing internal is listed in this module — no identifiers of a business, no moderation or
# publication status, no stock figures, no legal name. A visitor sees a shop window.


class CatalogImageRead(BaseModel):
    image_url: str
    alt_text: str | None


class CatalogCategoryRead(BaseModel):
    slug: str
    name: str


class CatalogStoreRef(BaseModel):
    subdomain: str
    display_name: str


class CatalogProductRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    price: Decimal
    currency: str
    availability_status: ProductAvailability
    category: CatalogCategoryRead
    store: CatalogStoreRef
    images: list[CatalogImageRead]
    created_at: datetime

    @classmethod
    def from_product(cls, product: Product) -> "CatalogProductRead":
        store = product.business.store
        if store is None:  # pragma: no cover — the public query joins the store in
            raise ValueError("a public product always belongs to a storefront")
        return cls(
            id=product.id,
            name=product.name,
            description=product.description,
            price=product.price,
            currency=product.currency,
            availability_status=product.availability_status,
            category=CatalogCategoryRead(slug=product.category.slug, name=product.category.name),
            store=CatalogStoreRef(
                subdomain=store.subdomain, display_name=product.business.display_name
            ),
            images=[
                CatalogImageRead(image_url=image.image_url, alt_text=image.alt_text)
                for image in product.images
            ],
            created_at=product.created_at,
        )


class CatalogProductListResponse(BaseModel):
    items: list[CatalogProductRead]
    total: int
    limit: int
    offset: int


class CatalogStoreRead(BaseModel):
    subdomain: str
    display_name: str
    description: str | None
    logo_url: str | None
    banner_url: str | None

    @classmethod
    def from_store(cls, store: Store) -> "CatalogStoreRead":
        return cls(
            subdomain=store.subdomain,
            display_name=store.business.display_name,
            description=store.business.description,
            logo_url=store.logo_url,
            banner_url=store.banner_url,
        )


class CatalogStoreListResponse(BaseModel):
    items: list[CatalogStoreRead]
    total: int
    limit: int
    offset: int


class CategoryTreeRead(BaseModel):
    """The reference book both sides read: a visitor filters by slug, a seller files a
    product under an id. Neither is anybody's private data — the catalogue is the same
    for everyone."""

    id: uuid.UUID
    slug: str
    name: str
    children: list["CategoryTreeRead"]

    @classmethod
    def leaf(cls, category: Category) -> "CategoryTreeRead":
        return cls(id=category.id, slug=category.slug, name=category.name, children=[])

    @classmethod
    def from_root(cls, category: Category) -> "CategoryTreeRead":
        """Two levels, because two is what the repository loads — a third would lazy load."""
        return cls(
            id=category.id,
            slug=category.slug,
            name=category.name,
            children=[cls.leaf(child) for child in category.children],
        )
