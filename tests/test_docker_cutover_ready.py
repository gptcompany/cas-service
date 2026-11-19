import json
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

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


def test_healthcheck_targets_the_configured_ipv4_host_and_port():
    """La sonda legge CAS_HOST e CAS_PORT dall'ambiente del container: stesso indirizzo e porta con cui CAS si lega."""
    svc = _compose_config()["services"]["cas-service"]
    cmd = " ".join(svc["healthcheck"]["test"])
    assert cmd.startswith("CMD /app/.venv/bin/python -c")
    assert "localhost" not in cmd
    assert "CAS_HOST" in cmd and "CAS_PORT" in cmd
    assert svc["environment"]["CAS_HOST"] == "127.0.0.1" and svc["environment"]["CAS_PORT"] == "8769"


class _Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass


class _HTTPv6(HTTPServer):
    address_family = socket.AF_INET6


# Risoluzione di `localhost` come negli host con `::1 localhost` in /etc/hosts: prima ::1, poi 127.0.0.1.
_IPV6_FIRST = """\
import socket
_orig = socket.getaddrinfo


def getaddrinfo(host, port, *args, **kwargs):
    if host == "localhost":
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", port, 0, 0)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
    return _orig(host, port, *args, **kwargs)


socket.getaddrinfo = getaddrinfo
"""


def _healthcheck_exit(server_cls, host: str, tmp_path) -> int:
    """Esegue il comando del healthcheck da Compose con un solo listener, su `host`, che risponde 200."""
    (tmp_path / "sitecustomize.py").write_text(_IPV6_FIRST)
    try:
        server = server_cls((host, 0), _Health)
    except OSError:
        pytest.skip(f"{host} non disponibile su questo host")
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    try:
        port = server.server_address[1]
        svc = _compose_config({"CAS_DOCKER_PORT": str(port)})["services"]["cas-service"]
        env = {k: v for k, v in svc["environment"].items() if isinstance(v, str)} | {"PYTHONPATH": str(tmp_path)}
        argv = [sys.executable, *svc["healthcheck"]["test"][2:]]
        return subprocess.run(argv, env=env, capture_output=True, timeout=30, check=False).returncode
    finally:
        server.shutdown()
        server.server_close()


def test_healthcheck_is_not_certified_by_another_service_on_ipv6_loopback(tmp_path):
    """M3: in rete host un altro server su ::1 con la stessa porta non deve far risultare sano CAS (che ascolta su 127.0.0.1)."""
    assert _healthcheck_exit(_HTTPv6, "::1", tmp_path) != 0


def test_healthcheck_succeeds_on_the_ipv4_listener_cas_binds(tmp_path):
    assert _healthcheck_exit(HTTPServer, "127.0.0.1", tmp_path) == 0


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


def test_docker_compose_caps_memory_without_swap_and_uses_host_network_on_loopback():
    """F-775: limite di isolamento 4g (decisione limiti-risorse-calcolo-agenti), niente swap, rete host con bind su 127.0.0.1."""
    svc = _compose_config()["services"]["cas-service"]

    assert int(svc["mem_limit"]) == 4 * 1024**3
    assert int(svc["memswap_limit"]) == int(svc["mem_limit"])
    assert svc["restart"] == "unless-stopped"
    assert svc["network_mode"] == "host"
    assert svc["pull_policy"] == "build"
    assert "ports" not in svc and "extra_hosts" not in svc
    assert svc["environment"]["CAS_HOST"] == "127.0.0.1"
