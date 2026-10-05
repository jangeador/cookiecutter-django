"""Exercise template rendering and cleanup without installing generated dependencies."""

from pathlib import Path

import pytest
import yaml
from cookiecutter import hooks
from cookiecutter.exceptions import FailedHookException
from cookiecutter.utils import create_env_with_context

from tests.test_cookiecutter_generation import SUPPORTED_COMBINATIONS
from tests.test_cookiecutter_generation import build_files_list
from tests.test_cookiecutter_generation import check_paths


@pytest.fixture
def bake_without_dependency_install(cookies, monkeypatch):
    """Run real generation hooks, replacing only the external dependency install."""
    original_run = hooks.run_script_with_context

    def run_hook(script_path, cwd, context):
        if Path(script_path).name != "post_gen_project.py":
            return original_run(script_path, cwd, context)
        env = create_env_with_context(context)
        source = env.from_string(Path(script_path).read_text()).render(**context)
        namespace = {"__name__": "rendered_post_gen_hook"}
        exec(compile(source, str(script_path), "exec"), namespace)  # noqa: S102
        namespace["setup_dependencies"] = lambda: None
        with monkeypatch.context() as hook_patch:
            hook_patch.chdir(cwd)
            namespace["main"]()
        return None

    monkeypatch.setattr(hooks, "run_script_with_context", run_hook)
    return cookies.bake


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"traefik_acme_challenge": "HTTP"},
        {"use_celery": "n", "use_sentry": "n", "rest_api": "None", "postgresql_version": "16"},
        {"cloud_provider": "None", "use_whitenoise": "y", "traefik_acme_challenge": "HTTP"},
        {"cloud_provider": "GCP", "rest_api": "Django Ninja"},
        {"use_docker": "n"},
    ],
)
def test_production_defaults_and_overrides(bake_without_dependency_install, overrides):
    result = bake_without_dependency_install(extra_context=overrides)
    assert result.exit_code == 0, result.exception
    project = result.project_path
    assert project is not None
    has_docker = overrides.get("use_docker", "y") == "y"
    has_cloudflare = has_docker and overrides.get("traefik_acme_challenge", "Cloudflare") == "Cloudflare"
    token_file = project / ".envs/.production/.traefik"
    assert token_file.exists() == has_cloudflare
    if not has_docker:
        assert not (project / "docker-compose.production.yml").exists()
        assert not (project / "compose").exists()
        return

    compose = yaml.safe_load((project / "docker-compose.production.yml").read_text())
    services = compose["services"]
    traefik = yaml.safe_load((project / "compose/production/traefik/traefik.yml").read_text())
    acme = traefik["certificatesResolvers"]["letsencrypt"]["acme"]
    if has_cloudflare:
        assert acme["dnsChallenge"]["provider"] == "cloudflare"
        assert "httpChallenge" not in acme
        assert services["traefik"]["env_file"] == ["./.envs/.production/.traefik"]
        assert "CF_DNS_API_TOKEN=\n" in token_file.read_text()
        assert ".envs/*" in (project / ".gitignore").read_text().splitlines()
    else:
        assert acme["httpChallenge"] == {"entryPoint": "web"}
        assert "dnsChallenge" not in acme
        assert "env_file" not in services["traefik"]
    for service in ("django", "celeryworker", "celerybeat", "flower"):
        if service in services:
            assert "./.envs/.production/.traefik" not in services[service].get("env_file", [])

    has_celery = overrides.get("use_celery", "y") == "y"
    assert ("celeryworker" in services) == has_celery
    assert ("celerybeat" in services) == has_celery
    assert ("flower" in services) == has_celery
    assert ("awscli" in services) == (overrides.get("cloud_provider", "AWS") == "AWS")
    postgres_version = overrides.get("postgresql_version", "18")
    dockerfile = (project / "compose/production/postgres/Dockerfile").read_text()
    assert f"postgres:{postgres_version}" in dockerfile
    production_settings = (project / "config/settings/production.py").read_text()
    assert ("sentry_sdk.init(" in production_settings) == (overrides.get("use_sentry", "y") == "y")
    base_settings = (project / "config/settings/base.py").read_text()
    assert ('"rest_framework"' in base_settings) == (overrides.get("rest_api", "DRF") == "DRF")


@pytest.mark.parametrize("overrides", SUPPORTED_COMBINATIONS)
def test_supported_combinations_still_render(bake_without_dependency_install, overrides):
    result = bake_without_dependency_install(extra_context=overrides)
    assert result.exit_code == 0, result.exception
    assert result.project_path is not None
    check_paths(build_files_list(result.project_path))


@pytest.mark.parametrize("overrides", [{}, {"theme": "Tailwind"}, {"theme": "Tailwind", "use_celery": "n"}])
def test_theme_assets_and_templates(bake_without_dependency_install, overrides):
    result = bake_without_dependency_install(extra_context=overrides)
    assert result.exit_code == 0, result.exception
    project = result.project_path
    assert project is not None
    assert not (project / "theme_templates").exists()
    app = project / "my_awesome_project"
    is_tailwind = overrides.get("theme") == "Tailwind"
    assert (project / "frontend/tailwind.css").exists() == is_tailwind
    assert (app / "static/css/project.css").exists() != is_tailwind
    templates = list((app / "templates").rglob("*.html"))
    assert templates
    settings = (project / "config/settings/base.py").read_text()
    requirements = (project / "requirements/base.txt").read_text()
    compose = yaml.safe_load((project / "docker-compose.local.yml").read_text())
    if is_tailwind:
        for template in templates:
            source = template.read_text()
            assert "bootstrap" not in source.lower(), template
            assert "crispy" not in source.lower(), template
            assert "btn-primary" not in source, template
        assert '"django_tailwind_cli"' in settings
        assert '"crispy_bootstrap5"' not in settings
        assert "django-tailwind-cli==4.8.1" in requirements
        assert "crispy-bootstrap5" not in requirements
        assert "django-crispy-forms" not in requirements
        assert compose["services"]["tailwind"]["command"] == "python manage.py tailwind watch"
        assert compose["services"]["tailwind"]["ports"] == []
        assert compose["services"]["tailwind"]["container_name"] != compose["services"]["django"]["container_name"]
        assert not (project / "package.json").exists()
        assert not (app / "static/sass").exists()
        dockerfile = (project / "compose/production/django/Dockerfile").read_text()
        assert "python manage.py tailwind build" in dockerfile
        assert "node:" not in dockerfile
        assert "tailwind_css" in (app / "templates/base.html").read_text()
    else:
        assert "bootstrap/5.2.3" in (app / "templates/base.html").read_text()
        assert '"crispy_bootstrap5"' in settings
        assert "django-tailwind-cli" not in requirements
        assert "tailwind" not in compose["services"]


@pytest.mark.parametrize("pipeline", ["Django Compressor", "Gulp", "Webpack"])
def test_tailwind_rejects_conflicting_asset_pipelines(bake_without_dependency_install, pipeline):
    result = bake_without_dependency_install(extra_context={"theme": "Tailwind", "frontend_pipeline": pipeline})
    assert result.exit_code != 0
    assert isinstance(result.exception, FailedHookException)
