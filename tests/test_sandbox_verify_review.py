"""Rilievi della review nativa su sandbox-validate (F-775): build prima del down, porta da Compose, sonda diretta."""

import http.server
import threading

from tests.test_sandbox_verify import WORKFLOW, _load, _steps


def _redirecting_server():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                self.send_response(302)
                self.send_header("Location", "/other")
                self.end_headers()
            else:
                self.send_response(200)
                self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_image_is_built_before_the_running_stack_is_stopped():
    run = next(s["run"] for s in _steps() if "docker compose down" in s.get("run", ""))
    assert "docker compose build" in run
    assert run.index("docker compose build") < run.index("docker compose down")


def test_port_is_resolved_from_compose_config():
    resolve = next(s["run"] for s in _steps() if "GITHUB_ENV" in s.get("run", ""))
    assert "sandbox_verify.py port" in resolve
    assert ":-8769" not in WORKFLOW.read_text()


def test_port_from_compose_reads_the_effective_service_port():
    sv = _load()
    cfg = '{"services": {"cas-service": {"environment": {"CAS_PORT": "9000"}}}}'
    assert sv.port_from_compose(cfg) == 9000


def test_health_probe_does_not_follow_redirects():
    sv = _load()
    server = _redirecting_server()
    try:
        assert sv._health(server.server_address[1]) is False
    finally:
        server.shutdown()


def test_health_probe_ignores_proxy_environment(monkeypatch):
    sv = _load()
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.delenv("NO_PROXY", raising=False)

    class Ok(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Ok)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert sv._health(server.server_address[1]) is True
    finally:
        server.shutdown()
