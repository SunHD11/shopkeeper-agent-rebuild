"""Unit tests for deterministic, secret-safe configuration loading."""

from pathlib import Path

import pytest
from omegaconf.errors import InterpolationResolutionError

from app.conf.app_config import PROJECT_ROOT, app_config, load_app_config


def test_current_config_uses_rebuild_service_boundaries() -> None:
    assert app_config.db_dw.port == 3307
    assert app_config.qdrant.port == 6335
    assert app_config.embedding.port == 8082
    assert app_config.es.port == 9201
    assert app_config.qdrant.column_collection_name.endswith("_rebuild")
    assert app_config.qdrant.metric_collection_name.endswith("_rebuild")
    assert app_config.es.index_name == "value_index_rebuild"
    assert app_config.runtime.query_timeout_seconds == 120
    assert app_config.runtime.max_concurrent_queries == 4
    assert app_config.llm.timeout_seconds == 60
    assert app_config.llm.max_retries == 1
    assert app_config.api.cors_allowed_origins == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


def test_config_loading_does_not_depend_on_current_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    loaded = load_app_config()
    assert loaded.db_meta.database == "meta"


def test_service_addresses_can_be_overridden_for_compose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一份 YAML 在容器内可以改用 Compose 服务名和内部端口。"""

    overrides = {
        "META_MYSQL_HOST": "mysql",
        "META_MYSQL_PORT": "3306",
        "DW_MYSQL_HOST": "mysql",
        "DW_MYSQL_PORT": "3306",
        "QDRANT_HOST": "qdrant",
        "QDRANT_PORT": "6333",
        "ELASTICSEARCH_HOST": "elasticsearch",
        "ELASTICSEARCH_PORT": "9200",
        "EMBEDDING_HOST": "embedding",
        "EMBEDDING_PORT": "80",
    }
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)

    loaded = load_app_config(env_file=None)

    assert (loaded.db_meta.host, loaded.db_meta.port) == ("mysql", 3306)
    assert (loaded.db_dw.host, loaded.db_dw.port) == ("mysql", 3306)
    assert (loaded.qdrant.host, loaded.qdrant.port) == ("qdrant", 6333)
    assert (loaded.es.host, loaded.es.port) == ("elasticsearch", 9200)
    assert (loaded.embedding.host, loaded.embedding.port) == ("embedding", 80)


def test_secret_fields_are_not_in_repr() -> None:
    rendered = repr(app_config)
    assert app_config.db_meta.password not in rendered
    assert app_config.llm.api_key not in rendered


def test_missing_environment_variable_fails_fast(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    variable = "SHOPKEEPER_REBUILD_TEST_MISSING"
    monkeypatch.delenv(variable, raising=False)
    # 测试文件已经按模块移动到 tests/unit/conf，不能再依赖固定 parents 层数
    # 推算项目根目录；直接复用生产配置模块的稳定 PROJECT_ROOT。
    source = PROJECT_ROOT / "conf" / "app_config.yaml"
    config_text = source.read_text(encoding="utf-8").replace(
        "${oc.env:MYSQL_PASSWORD}", f"${{oc.env:{variable}}}"
    )
    config_file = tmp_path / "app_config.yaml"
    config_file.write_text(config_text, encoding="utf-8")

    with pytest.raises(InterpolationResolutionError):
        load_app_config(config_file=config_file, env_file=None)
