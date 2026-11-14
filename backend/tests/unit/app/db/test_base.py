"""What every table gets for free, and why each of the two mixins exists.

A UUID instead of a counter: tenant identifiers must not be enumerable in order. With a
counter, anybody holding one identifier holds the neighbouring ones — and on this platform the
neighbours belong to other shops.

Timestamps written by the database rather than by the application, so a row cannot be dated by
a clock we do not control, and `updated_at` moves on its own rather than when somebody
remembers to move it.
"""

import uuid

from sqlalchemy import DateTime, Uuid
from sqlalchemy.orm import DeclarativeBase

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class _Row(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "_rows_for_the_mixin_test"


def test_the_base_is_what_alembic_reads_the_schema_from() -> None:
    """Every model inherits from it so autogenerate sees the metadata; a model that did not
    would be a table nobody migrates."""
    assert issubclass(Base, DeclarativeBase)
    assert Base.metadata.tables


def test_an_identifier_is_not_a_number_anybody_can_count_on() -> None:
    column = _Row.__table__.columns["id"]

    assert isinstance(column.type, Uuid)
    assert column.primary_key is True


def test_and_it_is_made_here_rather_than_by_the_database() -> None:
    """The column carries the generator, so the identifier exists as the row is inserted and
    a service can use it in the same transaction rather than reading it back."""
    default = _Row.__table__.columns["id"].default
    assert default is not None

    assert isinstance(default.arg(None), uuid.UUID)


def test_both_times_are_written_by_the_database() -> None:
    """A row dated by a clock we do not control is a row whose order we cannot trust."""
    for name in ("created_at", "updated_at"):
        column = _Row.__table__.columns[name]
        assert column.server_default is not None, name
        assert isinstance(column.type, DateTime), name
        assert column.type.timezone is True, name


def test_and_the_second_one_moves_by_itself() -> None:
    assert _Row.__table__.columns["updated_at"].onupdate is not None


def test_a_row_that_only_happens_once_may_take_the_first_mixin_alone() -> None:
    """The two are separate on purpose: `updated_at` on a journal entry or on a verdict would
    be a field inviting a correction to something that is a record precisely because it cannot
    be corrected."""
    assert "updated_at" not in UUIDPrimaryKeyMixin.__dict__
    assert "created_at" not in UUIDPrimaryKeyMixin.__dict__
    assert "id" not in TimestampMixin.__dict__
