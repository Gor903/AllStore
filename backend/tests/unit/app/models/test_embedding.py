"""The search index of one product — an addition to the product, never a copy of it.

Written and read by the search service alone. The model lives here because the schema of this
database is owned by backend migrations and by nothing else: without this declaration Alembic
autogenerate would see a table nobody declared and propose dropping it.

`model` and `source_hash` together are what makes a row stale — a product whose search text
changed, or one embedded by a model we no longer use, is re-embedded in the background rather
than at the moment the seller saves.
"""

from pgvector.sqlalchemy import Vector

from app.models.embedding import EMBEDDING_DIMENSIONS, ProductEmbedding
from tests.unit.app.models import column_of, on_delete, table_of


def test_one_product_has_one_current_embedding() -> None:
    assert column_of(ProductEmbedding, "product_id").primary_key is True


def test_an_embedding_is_not_a_thing_that_outlives_its_product() -> None:
    assert on_delete(ProductEmbedding, "product_id") == "CASCADE"


def test_a_row_says_what_made_it_and_from_what() -> None:
    """Without both, nothing can tell a stale row from a current one, and the sweep would
    either re-embed everything every time or nothing ever."""
    columns = table_of(ProductEmbedding).columns

    assert columns["model"].nullable is False
    assert columns["source_hash"].nullable is False


def test_the_vector_is_as_wide_as_the_model_it_comes_from() -> None:
    vector = column_of(ProductEmbedding, "embedding").type
    assert isinstance(vector, Vector)

    assert vector.dim == EMBEDDING_DIMENSIONS


def test_it_carries_none_of_the_product_s_own_fields() -> None:
    """An addition, not a copy: a name kept here would be a second place for it to be wrong."""
    columns = set(table_of(ProductEmbedding).columns.keys())

    assert columns.isdisjoint({"name", "description", "price", "currency"})
