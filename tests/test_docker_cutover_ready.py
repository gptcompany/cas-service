import json
import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def _compose_config() -> dict:
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_docker_compose_uses_docker_specific_port_when_project_env_has_host_override():
    config = _compose_config()
    svc = config["services"]["cas-service"]
    assert svc["environment"]["CAS_PORT"] == "8769"
    assert svc["ports"][0]["published"] == "8769"
    assert svc["ports"][0]["target"] == 8769


def test_healthcheck_targets_docker_specific_default_port():
    config = _compose_config()
    cmd = " ".join(config["services"]["cas-service"]["healthcheck"]["test"])
    assert "localhost:8769/health" in cmd
