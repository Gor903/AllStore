"""categories, products, product_images

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-20
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# snapshots of the patterns in app.models: a migration must not follow the model
CATEGORY_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"

# fixed namespace: the seeded categories get the same ids in every environment, so a fixture
# or a frontend link written against one database still resolves in another
CATEGORY_NAMESPACE = uuid.UUID("3f2a6c9e-5d41-4b8e-9a77-1c0f5b2d8e10")

# the starting catalogue; managing it from the admin panel comes with the moderation stage
CATALOGUE: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Одежда и обувь",
        "clothing",
        (
            ("Женская одежда", "womens-clothing"),
            ("Мужская одежда", "mens-clothing"),
            ("Детская одежда", "kids-clothing"),
            ("Обувь", "footwear"),
        ),
    ),
    (
        "Электроника",
        "electronics",
        (
            ("Смартфоны и гаджеты", "smartphones"),
            ("Компьютеры и ноутбуки", "computers"),
            ("Аудио и видео", "audio-video"),
        ),
    ),
    (
        "Дом и сад",
        "home-and-garden",
        (
            ("Мебель", "furniture"),
            ("Посуда", "tableware"),
            ("Текстиль", "home-textiles"),
            ("Сад и огород", "garden"),
        ),
    ),
    (
        "Красота и здоровье",
        "beauty-and-health",
        (
            ("Косметика", "cosmetics"),
            ("Парфюмерия", "perfume"),
            ("Уход за собой", "personal-care"),
        ),
    ),
    (
        "Продукты питания",
        "food",
        (
            ("Бакалея", "groceries"),
            ("Напитки", "beverages"),
            ("Сладости", "sweets"),
        ),
    ),
    (
        "Детские товары",
        "kids",
        (
            ("Игрушки", "toys"),
            ("Товары для новорождённых", "baby-care"),
        ),
    ),
    (
        "Украшения и аксессуары",
        "jewelry-and-accessories",
        (
            ("Ювелирные изделия", "jewelry"),
            ("Сумки и аксессуары", "bags-and-accessories"),
            ("Часы", "watches"),
        ),
    ),
    (
        "Хобби и творчество",
        "hobby",
        (
            ("Рукоделие", "handmade"),
            ("Книги", "books"),
            ("Спорт и отдых", "sport"),
        ),
    ),
)


def category_id(slug: str) -> uuid.UUID:
    return uuid.uuid5(CATEGORY_NAMESPACE, slug)


def _seed_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for name, slug, children in CATALOGUE:
        rows.append({"id": category_id(slug), "name": name, "slug": slug, "parent_id": None})
        rows.extend(
            {
                "id": category_id(child_slug),
                "name": child_name,
                "slug": child_slug,
                "parent_id": category_id(slug),
            }
            for child_name, child_slug in children
        )
    # status is a python-side default on the model, so the seed sets it explicitly
    for row in rows:
        row["status"] = "active"
    return rows


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Enum("active", "hidden", name="category_status"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(f"slug ~ '{CATEGORY_SLUG_PATTERN}'", name="ck_categories_slug_format"),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_categories_slug"), "categories", ["slug"], unique=True)
    op.create_index(op.f("ix_categories_parent_id"), "categories", ["parent_id"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("stock_quantity", sa.Integer(), nullable=False),
        sa.Column(
            "availability_status",
            sa.Enum("in_stock", "out_of_stock", name="product_availability"),
            nullable=False,
        ),
        sa.Column(
            "moderation_status",
            sa.Enum("pending", "approved", "rejected", name="moderation_status"),
            nullable=False,
        ),
        sa.Column(
            "publication_status",
            sa.Enum("draft", "published", "hidden", name="publication_status"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_products_stock_non_negative"),
        sa.CheckConstraint(f"currency ~ '{CURRENCY_PATTERN}'", name="ck_products_currency_format"),
        sa.ForeignKeyConstraint(["business_id"], ["businesses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_products_business_id"), "products", ["business_id"], unique=False)
    op.create_index(op.f("ix_products_category_id"), "products", ["category_id"], unique=False)
    op.create_index(
        op.f("ix_products_moderation_status"), "products", ["moderation_status"], unique=False
    )
    op.create_index(
        op.f("ix_products_publication_status"), "products", ["publication_status"], unique=False
    )

    op.create_table(
        "product_images",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("alt_text", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("sort_order >= 0", name="ck_product_images_sort_order_non_negative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_product_images_product_id"), "product_images", ["product_id"], unique=False
    )

    op.bulk_insert(
        sa.table(
            "categories",
            sa.column("id", sa.Uuid()),
            sa.column("name", sa.String()),
            sa.column("slug", sa.String()),
            sa.column("parent_id", sa.Uuid()),
            sa.column("status", sa.Enum(name="category_status")),
        ),
        _seed_rows(),
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_product_images_product_id"), table_name="product_images")
    op.drop_table("product_images")
    op.drop_index(op.f("ix_products_publication_status"), table_name="products")
    op.drop_index(op.f("ix_products_moderation_status"), table_name="products")
    op.drop_index(op.f("ix_products_category_id"), table_name="products")
    op.drop_index(op.f("ix_products_business_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_categories_parent_id"), table_name="categories")
    op.drop_index(op.f("ix_categories_slug"), table_name="categories")
    op.drop_table("categories")
    # drop_table leaves the enum types behind — without this a repeated upgrade hits existing types
    bind = op.get_bind()
    for name in (
        "publication_status",
        "moderation_status",
        "product_availability",
        "category_status",
    ):
        sa.Enum(name=name).drop(bind, checkfirst=False)
