from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base — every model inherits from it so Alembic autogenerate sees the metadata."""
