"""A narrow mirror of the tables this service touches.

Deliberately not an import from backend: the service is deployed separately (ADR 10), and a
shared package would make them one deployable again. The mirror is narrow on purpose — only
the columns the search actually reads. The schema itself is owned by backend migrations
(AllStore_build_plan.md, раздел 6); nothing here creates or alters a table.

`products.archived_at` is the only visibility rule applied here, and only to avoid embedding
what a seller threw away. Everything else — approved, published, shop on the air — is decided
by backend when it turns identifiers back into products. One place decides what a visitor may
see, and it is not this one.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    func,
)

from app.config import get_settings

metadata = MetaData()

products = Table(
    "products",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("business_id", Uuid, nullable=False),
    Column("category_id", Uuid, nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", Text),
    Column("archived_at", DateTime(timezone=True)),
)

categories = Table(
    "categories",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("name", String(255), nullable=False),
)

businesses = Table(
    "businesses",
    metadata,
    Column("id", Uuid, primary_key=True),
    Column("display_name", String(255), nullable=False),
)

product_embeddings = Table(
    "product_embeddings",
    metadata,
    Column("product_id", Uuid, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("model", String(128), nullable=False),
    Column("source_hash", String(64), nullable=False),
    Column("embedding", Vector(get_settings().embedding_dimensions), nullable=False),
    Column("updated_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)
