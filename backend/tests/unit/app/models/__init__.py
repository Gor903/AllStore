"""Reading the schema out of the models, with the types SQLAlchemy hides.

`__table__` is declared as a generic FROM clause and a constraint as a generic constraint, so
every one of these facts needs a narrowing to be read at all. Doing it once here keeps the
tests about the decisions — RESTRICT rather than CASCADE, one administrator, a reason that is
not whitespace — instead of about getting at them.
"""

from typing import Any, cast

from sqlalchemy import CheckConstraint, Column, DefaultClause, Index, String, Table
from sqlalchemy.sql.schema import ColumnDefault

from app.db.base import Base


def table_of(model: type[Base]) -> Table:
    return cast(Table, model.__table__)


def column_of(model: type[Base], name: str) -> Column[Any]:
    return table_of(model).columns[name]


def default_of(model: type[Base], name: str) -> Any:
    """What a new row gets when nobody said. Absent is an answer too, so this asks for one."""
    default = column_of(model, name).default
    assert isinstance(default, ColumnDefault), f"{name} has no default"
    return default.arg


def server_default_of(model: type[Base], name: str) -> str:
    """What the database puts there when the application says nothing at all."""
    default = column_of(model, name).server_default
    assert isinstance(default, DefaultClause), f"{name} has no server default"
    return str(default.arg)


def length_of(model: type[Base], name: str) -> int | None:
    return cast(String, column_of(model, name).type).length


def check_of(model: type[Base], name: str) -> str:
    """The SQL of one named check constraint, as the database will read it."""
    constraint = next(c for c in table_of(model).constraints if c.name == name)
    assert isinstance(constraint, CheckConstraint)
    return str(constraint.sqltext)


def index_of(model: type[Base], name: str) -> Index:
    return next(index for index in table_of(model).indexes if index.name == name)


def where_of(index: Index) -> str:
    """The condition a partial index is kept under — the half that makes it a rule."""
    return str(index.dialect_options["postgresql"]["where"])


def on_delete(model: type[Base], column: str) -> str | None:
    """What happens to this row when what it points at goes away."""
    key = next(k for k in table_of(model).foreign_keys if k.parent.name == column)
    return key.ondelete
