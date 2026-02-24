"""Tests for /compute endpoint and /engines capability extension (Slice A)."""

from __future__ import annotations

import json
from http.server import HTTPServer
from threading import Thread

import pytest

from cas_service.engines.base import (
    BaseEngine,
    Capability,
    ComputeRequest,
    ComputeResult,
    EngineResult,
)


# ---------------------------------------------------------------------------
# Fixtures: minimal test engine + server
# ---------------------------------------------------------------------------


class _ValidateOnlyEngine(BaseEngine):
    """Test engine that only supports validate."""

    name = "test_validate"

    def validate(self, latex: str) -> EngineResult:
        return EngineResult(engine=self.name, success=True, is_valid=True)


class _ComputeEngine(BaseEngine):
    """Test engine that supports compute."""

    name = "test_compute"

    def validate(self, latex: str) -> EngineResult:
        return EngineResult(engine=self.name, success=True, is_valid=True)

    def compute(self, request: ComputeRequest) -> ComputeResult:
        if request.template == "echo":
            return ComputeResult(
                engine=self.name,
                success=True,
                time_ms=1,
                result={"value": request.inputs.get("msg", "")},
                stdout=request.inputs.get("msg", "") + "\n",
            )
        return ComputeResult(
            engine=self.name,
            success=False,
            error=f"Unknown template: {request.template}",
            error_code="UNKNOWN_TEMPLATE",
        )

    @property
    def capabilities(self) -> list[Capability]:
        return [Capability.VALIDATE, Capability.COMPUTE]


@pytest.fixture()
def cas_server():
    """Start a CAS HTTP server with test engines and yield (host, port)."""
    import cas_service.main as cas_main

    original_engines = cas_main.ENGINES.copy()
    cas_main.ENGINES.clear()
    cas_main.ENGINES["test_validate"] = _ValidateOnlyEngine()
    cas_main.ENGINES["test_compute"] = _ComputeEngine()

    server = HTTPServer(("127.0.0.1", 0), cas_main.CASHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield ("127.0.0.1", port)

    server.shutdown()
    cas_main.ENGINES.clear()
    cas_main.ENGINES.update(original_engines)


def _post(addr, path, body):
    """HTTP POST helper returning (status, parsed_json)."""
    import http.client

    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=5)
    conn.request(
        "POST",
        path,
        body=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )
    resp = conn.getresponse()
    data = json.loads(resp.read())
    status = resp.status
    conn.close()
    return status, data


def _get(addr, path):
    """HTTP GET helper returning (status, parsed_json)."""
    import http.client

    conn = http.client.HTTPConnection(addr[0], addr[1], timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    status = resp.status
    conn.close()
    return status, data


# ===========================================================================
# /engines — capability extension
# ===========================================================================


class TestEnginesCapabilities:
    def test_engines_includes_capabilities(self, cas_server):
        status, data = _get(cas_server, "/engines")
        assert status == 200
        engines = {e["name"]: e for e in data["engines"]}

        assert "test_validate" in engines
        assert engines["test_validate"]["capabilities"] == ["validate"]

        assert "test_compute" in engines
        assert set(engines["test_compute"]["capabilities"]) == {
            "validate",
            "compute",
        }

    def test_engines_available_field(self, cas_server):
        status, data = _get(cas_server, "/engines")
        for engine in data["engines"]:
            assert "available" in engine
            assert isinstance(engine["available"], bool)


# ===========================================================================
# /compute — request validation
# ===========================================================================


class TestComputeValidation:
    def test_missing_engine(self, cas_server):
        status, data = _post(
            cas_server,
            "/compute",
            {
                "task_type": "template",
                "template": "echo",
            },
        )
        assert status == 400
        assert data["code"] == "INVALID_REQUEST"

    def test_unknown_engine(self, cas_server):
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "nonexistent",
                "task_type": "template",
                "template": "echo",
            },
        )
        assert status == 422
        assert data["code"] == "UNKNOWN_ENGINE"
        assert "available" in data["details"]

    def test_missing_task_type(self, cas_server):
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "test_compute",
                "template": "echo",
            },
        )
        assert status == 400
        assert data["code"] == "INVALID_REQUEST"

    def test_invalid_task_type(self, cas_server):
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "test_compute",
                "task_type": "script",
                "template": "echo",
            },
        )
        assert status == 400

    def test_missing_template(self, cas_server):
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "test_compute",
                "task_type": "template",
            },
        )
        assert status == 400

    def test_invalid_inputs_type(self, cas_server):
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "test_compute",
                "task_type": "template",
                "template": "echo",
                "inputs": "not_a_dict",
            },
        )
        assert status == 400

    def test_invalid_timeout(self, cas_server):
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "test_compute",
                "task_type": "template",
                "template": "echo",
                "timeout_s": -1,
            },
        )
        assert status == 400

    def test_empty_body(self, cas_server):
        """Empty body should return INVALID_JSON."""
        import http.client

        conn = http.client.HTTPConnection(cas_server[0], cas_server[1], timeout=5)
        conn.request(
            "POST",
            "/compute",
            body=b"",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "0",
            },
        )
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        assert data["code"] == "INVALID_JSON"


# ===========================================================================
# /compute — engine capability checks
# ===========================================================================


class TestComputeCapability:
    def test_compute_on_validate_only_engine(self, cas_server):
        """Engine without compute capability returns NOT_IMPLEMENTED."""
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "test_validate",
                "task_type": "template",
                "template": "echo",
            },
        )
        assert status == 400
        assert data["code"] == "NOT_IMPLEMENTED"

    def test_compute_success(self, cas_server):
        """Compute-capable engine returns valid result."""
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "test_compute",
                "task_type": "template",
                "template": "echo",
                "inputs": {"msg": "hello"},
            },
        )
        assert status == 200
        assert data["success"] is True
        assert data["engine"] == "test_compute"
        assert data["result"]["value"] == "hello"
        assert data["stdout"] == "hello\n"
        assert data["error"] is None

    def test_compute_unknown_template(self, cas_server):
        """Unknown template returns engine-level error (still 200, success=false)."""
        status, data = _post(
            cas_server,
            "/compute",
            {
                "engine": "test_compute",
                "task_type": "template",
                "template": "nonexistent_template",
            },
        )
        assert status == 200
        assert data["success"] is False
        assert "UNKNOWN_TEMPLATE" in (data.get("error_code") or "")


# ===========================================================================
# /validate — backward compatibility
# ===========================================================================


class TestValidateBackwardCompat:
    def test_validate_still_works(self, cas_server):
        """Existing /validate endpoint remains functional."""
        status, data = _post(
            cas_server,
            "/validate",
            {
                "latex": "x^2",
                "engines": ["test_validate"],
            },
        )
        assert status == 200
        assert "results" in data
        assert data["results"][0]["engine"] == "test_validate"
        assert data["results"][0]["success"] is True


# ===========================================================================
# BaseEngine defaults
# ===========================================================================


class TestBaseEngineDefaults:
    def test_default_capabilities_is_validate(self):
        engine = _ValidateOnlyEngine()
        assert engine.capabilities == [Capability.VALIDATE]

    def test_default_compute_returns_not_implemented(self):
        engine = _ValidateOnlyEngine()
        req = ComputeRequest(
            engine="test",
            task_type="template",
            template="foo",
        )
        result = engine.compute(req)
        assert result.success is False
        assert result.error_code == "NOT_IMPLEMENTED"

    def test_default_cleanup_is_noop(self):
        engine = _ValidateOnlyEngine()
        # cleanup should not raise
        engine.cleanup()


# ===========================================================================
# /validate — 503 when no engines
# ===========================================================================


class _UnavailableEngine(BaseEngine):
    """Engine that reports itself as unavailable."""

    name = "test_unavailable"

    def validate(self, latex: str) -> EngineResult:
        return EngineResult(engine=self.name, success=False, error="unavailable")

    def is_available(self) -> bool:
        return False


@pytest.fixture()
def cas_server_no_engines():
    """CAS server with no available engines and no default engine."""
    import cas_service.main as cas_main

    original_engines = cas_main.ENGINES.copy()
    original_default = cas_main._default_engine
    cas_main.ENGINES.clear()
    cas_main._default_engine = ""

    server = HTTPServer(("127.0.0.1", 0), cas_main.CASHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield ("127.0.0.1", port)

    server.shutdown()
    cas_main.ENGINES.clear()
    cas_main.ENGINES.update(original_engines)
    cas_main._default_engine = original_default


@pytest.fixture()
def cas_server_unavailable():
    """CAS server with only unavailable engines and no default engine."""
    import cas_service.main as cas_main

    original_engines = cas_main.ENGINES.copy()
    original_default = cas_main._default_engine
    cas_main.ENGINES.clear()
    cas_main.ENGINES["test_unavailable"] = _UnavailableEngine()
    cas_main._default_engine = ""

    server = HTTPServer(("127.0.0.1", 0), cas_main.CASHandler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield ("127.0.0.1", port)

    server.shutdown()
    cas_main.ENGINES.clear()
    cas_main.ENGINES.update(original_engines)
    cas_main._default_engine = original_default


class TestValidateNoEngines:
    def test_503_when_no_engines_registered(self, cas_server_no_engines):
        """Should return 503 when no engines are registered."""
        status, data = _post(
            cas_server_no_engines,
            "/validate",
            {
                "latex": "x^2",
            },
        )
        assert status == 503
        assert data["code"] == "NO_ENGINES"

    def test_503_when_all_engines_unavailable(self, cas_server_unavailable):
        """Should return 503 when engines exist but none available."""
        status, data = _post(
            cas_server_unavailable,
            "/validate",
            {
                "latex": "x^2",
            },
        )
        assert status == 503
        assert data["code"] == "NO_ENGINES"
