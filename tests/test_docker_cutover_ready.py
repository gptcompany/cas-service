import json
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV = {
    "CAS_PORT": "8769",
    "CAS_DOCKER_PORT": "8769",
    "CAS_DOCKER_MATLAB_HOST_PATH": "/media/sam/3TB-WDC/matlab2025",
}


def _compose_config(extra_env: dict[str, str] | None = None) -> dict:
    env_values = DEFAULT_ENV.copy()
    if extra_env:
        env_values.update(extra_env)

    with NamedTemporaryFile("w", suffix=".env", delete=False) as handle:
        for key, value in env_values.items():
            handle.write(f"{key}={value}\n")
        env_file = Path(handle.name)

    try:
        result = subprocess.run(
            ["docker", "compose", "--env-file", str(env_file), "config", "--format", "json"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
    finally:
        env_file.unlink(missing_ok=True)

    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_docker_compose_uses_docker_specific_runtime_settings_when_project_env_has_host_overrides():
    config = _compose_config()
    svc = config["services"]["cas-service"]
    env = svc["environment"]

    assert env["CAS_PORT"] == "8769"
    assert env["CAS_DEFAULT_ENGINE"] == "sage"
    assert env["CAS_SAGE_PATH"] == "/usr/bin/sage"
    assert env["CAS_MATLAB_PATH"] == "/opt/matlab/bin/matlab"
    assert svc["ports"][0]["published"] == "8769"
    assert svc["ports"][0]["target"] == 8769


def test_healthcheck_targets_docker_specific_default_port():
    config = _compose_config()
    cmd = " ".join(config["services"]["cas-service"]["healthcheck"]["test"])
    assert cmd.startswith("CMD /app/.venv/bin/python -c")
    assert "localhost:8769/health" in cmd


def test_docker_compose_mounts_host_matlab_installation_into_container():
    config = _compose_config()
    volume = config["services"]["cas-service"]["volumes"][0]
    assert volume["type"] == "bind"
    assert volume["source"] == "/media/sam/3TB-WDC/matlab2025"
    assert volume["target"] == "/opt/matlab"
    assert volume["read_only"] is True


def test_docker_compose_honors_explicit_docker_port_override():
    config = _compose_config({"CAS_PORT": "7000", "CAS_DOCKER_PORT": "9000"})
    svc = config["services"]["cas-service"]
    env = svc["environment"]

    assert env["CAS_PORT"] == "9000"
    assert svc["ports"][0]["published"] == "9000"
    assert svc["ports"][0]["target"] == 9000
