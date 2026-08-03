"""Tests for metadata ORM model mappings."""

from app.models import (
    ColumnInfoMySQL,
    ColumnMetricMySQL,
    MetricInfoMySQL,
    TableInfoMySQL,
)
from app.models.base import Base


def test_metadata_models_are_registered() -> None:
    """All four Meta MySQL tables are registered."""

    assert set(Base.metadata.tables) == {
        "table_info",
        "column_info",
        "metric_info",
        "column_metric",
    }


def test_model_table_names() -> None:
    """Each ORM model maps to the expected table."""

    assert TableInfoMySQL.__tablename__ == "table_info"
    assert ColumnInfoMySQL.__tablename__ == "column_info"
    assert MetricInfoMySQL.__tablename__ == "metric_info"
    assert ColumnMetricMySQL.__tablename__ == "column_metric"


def test_column_metric_uses_composite_primary_key() -> None:
    """ColumnMetric uses column_id and metric_id together."""

    primary_keys = {
        column.name for column in ColumnMetricMySQL.__table__.primary_key.columns
    }

    assert primary_keys == {
        "column_id",
        "metric_id",
    }


def test_column_info_has_expected_columns() -> None:
    """ColumnInfo matches the existing Meta MySQL table."""

    column_names = {column.name for column in ColumnInfoMySQL.__table__.columns}

    assert column_names == {
        "id",
        "name",
        "type",
        "role",
        "examples",
        "description",
        "alias",
        "table_id",
    }
