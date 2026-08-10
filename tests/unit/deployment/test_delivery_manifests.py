from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_compose_contains_the_complete_application_stack() -> None:
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker/docker-compose.yaml").read_text(encoding="utf-8")
    )
    services = compose["services"]

    assert {
        "mysql",
        "qdrant",
        "elasticsearch",
        "kibana",
        "embedding",
        "api",
        "frontend",
    } <= services.keys()
    assert services["frontend"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert services["api"]["environment"] == {
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


def test_embedding_uses_a_persistent_download_cache() -> None:
    compose = yaml.safe_load(
        (PROJECT_ROOT / "docker/docker-compose.yaml").read_text(encoding="utf-8")
    )
    embedding = compose["services"]["embedding"]

    assert "--model-id" in embedding["command"]
    assert "embedding_data:/data" in embedding["volumes"]
    assert all("./embedding" not in volume for volume in embedding["volumes"])
    assert "embedding_data" in compose["volumes"]


def test_application_images_are_locked_and_run_without_root() -> None:
    api_dockerfile = (PROJECT_ROOT / "docker/api/Dockerfile").read_text(
        encoding="utf-8"
    )
    frontend_dockerfile = (PROJECT_ROOT / "frontend/Dockerfile").read_text(
        encoding="utf-8"
    )

    assert "uv sync --locked --no-dev" in api_dockerfile
    assert "USER shopkeeper" in api_dockerfile
    assert "pnpm install --frozen-lockfile" in frontend_dockerfile
    assert "nginx-unprivileged" in frontend_dockerfile


def test_nginx_preserves_streaming_and_spa_routing() -> None:
    nginx = (PROJECT_ROOT / "frontend/docker/nginx.conf").read_text(encoding="utf-8")

    assert "proxy_buffering off" in nginx
    assert "proxy_request_buffering off" in nginx
    assert "proxy_read_timeout 180s" in nginx
    assert "try_files $uri $uri/ /index.html" in nginx


def test_full_stack_operational_scripts_are_present() -> None:
    required = {
        "common.ps1",
        "validate_env.ps1",
        "build_knowledge.ps1",
        "start_full_stack.ps1",
        "smoke_full_stack.ps1",
        "stop_full_stack.ps1",
    }
    assert required <= {path.name for path in (PROJECT_ROOT / "scripts").glob("*.ps1")}
