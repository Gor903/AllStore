"""Модели реэкспортируются здесь, чтобы Alembic autogenerate видел полную метадату."""

from app.models.account_block import AccountBlock
from app.models.audit import AuditLog
from app.models.auth import PasswordResetToken, RefreshToken
from app.models.business import Business, BusinessStatus
from app.models.category import Category, CategoryStatus
from app.models.contact import PHONE_PLATFORMS, ContactPlatform, SocialLink
from app.models.customer_block import BusinessCustomerBlock
from app.models.embedding import EMBEDDING_DIMENSIONS, ProductEmbedding
from app.models.moderation import (
    BusinessDecision,
    BusinessModerationReview,
    ModerationDecision,
    ModerationReview,
)
from app.models.product import (
    ModerationStatus,
    Product,
    ProductAvailability,
    ProductImage,
    PublicationStatus,
)
from app.models.product_revision import ProductRevision, RevisionStatus
from app.models.report import Report, ReportStatus
from app.models.store import Store, StoreStatus
from app.models.user import User, UserRole, UserStatus

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "PHONE_PLATFORMS",
    "AccountBlock",
    "AuditLog",
    "Business",
    "BusinessCustomerBlock",
    "BusinessDecision",
    "BusinessModerationReview",
    "BusinessStatus",
    "Category",
    "CategoryStatus",
    "ContactPlatform",
    "ModerationDecision",
    "ModerationReview",
    "ModerationStatus",
    "PasswordResetToken",
    "Product",
    "ProductAvailability",
    "ProductEmbedding",
    "ProductImage",
    "ProductRevision",
    "PublicationStatus",
    "RefreshToken",
    "Report",
    "ReportStatus",
    "RevisionStatus",
    "SocialLink",
    "Store",
    "StoreStatus",
    "User",
    "UserRole",
    "UserStatus",
]
