"""Unit tests for deterministic, secret-safe configuration loading."""

from pathlib import Path

import pytest
from omegaconf.errors import InterpolationResolutionError

from app.conf.app_config import app_config, load_app_config


def test_current_config_uses_rebuild_service_boundaries() -> None:
    assert app_config.db_dw.port == 3307
    assert app_config.qdrant.port == 6335
    assert app_config.embedding.port == 8082
    assert app_config.es.port == 9201
    assert app_config.qdrant.column_collection_name.endswith("_rebuild")
    assert app_config.qdrant.metric_collection_name.endswith("_rebuild")
    assert app_config.es.index_name == "value_index_rebuild"


def test_config_loading_does_not_depend_on_current_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    loaded = load_app_config()
    assert loaded.db_meta.database == "meta"


def test_secret_fields_are_not_in_repr() -> None:
    rendered = repr(app_config)
    assert app_config.db_meta.password not in rendered
    assert app_config.llm.api_key not in rendered


def test_missing_environment_variable_fails_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    variable = "SHOPKEEPER_REBUILD_TEST_MISSING"
    monkeypatch.delenv(variable, raising=False)
    source = Path(__file__).resolve().parents[2] / "conf" / "app_config.yaml"
    config_text = source.read_text(encoding="utf-8").replace(
        "${oc.env:MYSQL_PASSWORD}", f"${{oc.env:{variable}}}"
    )
    config_file = tmp_path / "app_config.yaml"
    config_file.write_text(config_text, encoding="utf-8")

    with pytest.raises(InterpolationResolutionError):
        load_app_config(config_file=config_file, env_file=None)
