"""CAS Microservice — HTTP handler for LaTeX formula validation.

Standalone service (separate repo, not shared.server). Provides
/validate, /health, /status, /engines endpoints using stdlib http.server.

Usage:
    python -m cas_service.main

Environment:
    CAS_PORT=8769              # HTTP listen port
    CAS_MAXIMA_PATH=/usr/bin/maxima  # Maxima binary path
    CAS_MAXIMA_TIMEOUT=10      # Maxima subprocess timeout (seconds)
    CAS_MATLAB_PATH=matlab                 # MATLAB binary (searches PATH)
    CAS_MATLAB_TIMEOUT=30      # MATLAB subprocess timeout (seconds)
    CAS_SYMPY_TIMEOUT=5        # SymPy parse/simplify timeout (seconds)
    CAS_GAP_PATH=gap           # GAP binary path
    CAS_GAP_TIMEOUT=10         # GAP subprocess timeout (seconds)
    CAS_LOG_LEVEL=INFO         # Logging level
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from cas_service.engines.base import Capability, ComputeRequest
from cas_service.engines.gap_engine import GapEngine
from cas_service.engines.matlab_engine import MatlabEngine
from cas_service.engines.maxima_engine import MaximaEngine
from cas_service.engines.sympy_engine import SympyEngine
from cas_service.preprocessing import preprocess_latex

logger = logging.getLogger(__name__)

# Engine registry (initialized once at startup)
ENGINES: dict[str, Any] = {}

_start_time: float = 0.0


class JsonFormatter(logging.Formatter):
    """JSON log formatter for Loki/journald."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "service": "cas-service",
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


class CASHandler(BaseHTTPRequestHandler):
    """HTTP handler for CAS microservice."""

    def do_POST(self) -> None:
        if self.path == "/validate":
            self._handle_validate()
        elif self.path == "/compute":
            self._handle_compute()
        else:
            self._send_error("Not found", "NOT_FOUND", 404)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/status":
            self._handle_status()
        elif self.path == "/engines":
            self._handle_engines()
        else:
            self._send_error("Not found", "NOT_FOUND", 404)

    def _handle_validate(self) -> None:
        data = self._read_json()
        if data is None:
            return

        latex = data.get("latex")
        if not latex:
            self._send_error("latex field is required", "INVALID_REQUEST", 400)
            return

        engines_requested = data.get("engines", list(ENGINES.keys()))

        unknown = [e for e in engines_requested if e not in ENGINES]
        if unknown:
            self._send_error(
                f"Unknown engine: {', '.join(unknown)}",
                "UNKNOWN_ENGINE", 422,
                {"available": list(ENGINES.keys())},
            )
            return

        start = time.time()
        preprocessed = preprocess_latex(latex)

        results = []
        for engine_name in engines_requested:
            engine = ENGINES[engine_name]
            result = engine.validate(preprocessed)
            results.append({
                "engine": result.engine,
                "success": result.success,
                "is_valid": result.is_valid,
                "simplified": result.simplified,
                "original_parsed": result.original_parsed,
                "error": result.error,
                "time_ms": result.time_ms,
            })

        elapsed = int((time.time() - start) * 1000)
        self._send_json({
            "results": results,
            "latex_preprocessed": preprocessed,
            "time_ms": elapsed,
        })

    def _handle_health(self) -> None:
        self._send_json({
            "status": "ok",
            "service": "cas-service",
            "uptime_seconds": round(time.time() - _start_time, 1),
        })

    def _handle_status(self) -> None:
        engines_info = {}
        for name, engine in ENGINES.items():
            info: dict[str, Any] = {
                "available": engine.is_available(),
                "version": engine.get_version(),
            }
            if hasattr(engine, "maxima_path"):
                info["path"] = engine.maxima_path
            engines_info[name] = info

        self._send_json({
            "service": "cas-service",
            "version": "0.1.0",
            "uptime_seconds": round(time.time() - _start_time, 1),
            "engines": engines_info,
        })

    def _handle_compute(self) -> None:
        data = self._read_json()
        if data is None:
            return

        engine_name = data.get("engine")
        if not engine_name:
            self._send_error(
                "engine field is required", "INVALID_REQUEST", 400,
            )
            return

        if engine_name not in ENGINES:
            self._send_error(
                f"Unknown engine: {engine_name}",
                "UNKNOWN_ENGINE", 422,
                {"available": list(ENGINES.keys())},
            )
            return

        task_type = data.get("task_type")
        if task_type != "template":
            self._send_error(
                "task_type must be 'template'",
                "INVALID_REQUEST", 400,
            )
            return

        template = data.get("template")
        if not template:
            self._send_error(
                "template field is required", "INVALID_REQUEST", 400,
            )
            return

        inputs = data.get("inputs", {})
        if not isinstance(inputs, dict):
            self._send_error(
                "inputs must be an object", "INVALID_REQUEST", 400,
            )
            return

        timeout_s = data.get("timeout_s", 5)
        if not isinstance(timeout_s, (int, float)) or timeout_s <= 0:
            self._send_error(
                "timeout_s must be a positive number", "INVALID_REQUEST", 400,
            )
            return

        engine = ENGINES[engine_name]
        if Capability.COMPUTE not in engine.capabilities:
            self._send_error(
                f"Engine '{engine_name}' does not support compute",
                "NOT_IMPLEMENTED", 400,
            )
            return

        if not engine.is_available():
            self._send_error(
                f"Engine '{engine_name}' is not available",
                "ENGINE_UNAVAILABLE", 503,
            )
            return

        request = ComputeRequest(
            engine=engine_name,
            task_type=task_type,
            template=template,
            inputs={str(k): str(v) for k, v in inputs.items()},
            timeout_s=int(timeout_s),
        )
        result = engine.compute(request)

        self._send_json({
            "engine": result.engine,
            "success": result.success,
            "time_ms": result.time_ms,
            "result": result.result,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "error": result.error,
            "error_code": result.error_code,
        })

    def _handle_engines(self) -> None:
        engine_list = []
        for name, engine in ENGINES.items():
            engine_list.append({
                "name": name,
                "available": engine.is_available(),
                "capabilities": [c.value for c in engine.capabilities],
                "description": engine.__class__.__doc__ or "",
            })
        self._send_json({"engines": engine_list})

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, error: str, code: str, status: int = 400,
                    details: dict | None = None) -> None:
        response: dict[str, Any] = {"error": error, "code": code}
        if details:
            response["details"] = details
        self._send_json(response, status)

    def _read_json(self) -> dict | None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            self._send_error("Request body is empty", "INVALID_JSON", 400)
            return None
        try:
            body = self.rfile.read(content_length)
            return json.loads(body)
        except (json.JSONDecodeError, ValueError) as e:
            self._send_error(f"Invalid JSON: {e}", "INVALID_JSON", 400)
            return None

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s %s", self.client_address[0], format % args)


def _init_engines() -> None:
    """Initialize engine registry."""
    global ENGINES

    sympy_timeout = int(os.environ.get("CAS_SYMPY_TIMEOUT", "5"))
    maxima_path = os.environ.get("CAS_MAXIMA_PATH", "/usr/bin/maxima")
    maxima_timeout = int(os.environ.get("CAS_MAXIMA_TIMEOUT", "10"))
    matlab_path = os.environ.get("CAS_MATLAB_PATH", "matlab")
    matlab_timeout = int(os.environ.get("CAS_MATLAB_TIMEOUT", "30"))
    gap_path = os.environ.get("CAS_GAP_PATH", "gap")
    gap_timeout = int(os.environ.get("CAS_GAP_TIMEOUT", "10"))

    sympy_engine = SympyEngine(timeout=sympy_timeout)
    maxima_engine = MaximaEngine(maxima_path=maxima_path, timeout=maxima_timeout)
    matlab_engine = MatlabEngine(matlab_path=matlab_path, timeout=matlab_timeout)
    gap_engine = GapEngine(gap_path=gap_path, timeout=gap_timeout)

    ENGINES["sympy"] = sympy_engine
    ENGINES["maxima"] = maxima_engine
    ENGINES["matlab"] = matlab_engine
    ENGINES["gap"] = gap_engine

    for name, engine in ENGINES.items():
        available = engine.is_available()
        version = engine.get_version()
        logger.info("Engine %s: available=%s version=%s", name, available, version)


def main() -> None:
    """Start the CAS microservice."""
    global _start_time

    log_level = os.environ.get("CAS_LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))
    root.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)

    _init_engines()

    port = int(os.environ.get("CAS_PORT", "8769"))
    _start_time = time.time()

    server = HTTPServer(("0.0.0.0", port), CASHandler)

    if threading.current_thread() is threading.main_thread():
        def sigterm_handler(signum: int, frame: Any) -> None:
            logger.info("SIGTERM received, shutting down...")
            server.shutdown()
        signal.signal(signal.SIGTERM, sigterm_handler)

    logger.info("CAS service starting on port %d", port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        logger.info("CAS service stopped")


if __name__ == "__main__":
    main()
