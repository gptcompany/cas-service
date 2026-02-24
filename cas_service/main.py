"""CAS Microservice — HTTP handler for LaTeX formula validation.

Standalone service (separate repo, not shared.server). Provides
/validate, /health, /status, /engines, /compute endpoints using stdlib http.server.

Usage:
    python -m cas_service.main

Environment:
    CAS_PORT=8769              # HTTP listen port
    CAS_SYMPY_TIMEOUT=5        # SymPy parse/simplify timeout (seconds)
    CAS_MATLAB_PATH=matlab     # MATLAB binary (searches PATH)
    CAS_MATLAB_TIMEOUT=30      # MATLAB subprocess timeout (seconds)
    CAS_SAGE_PATH=sage         # SageMath binary path
    CAS_SAGE_TIMEOUT=30        # SageMath subprocess timeout (seconds)
    CAS_WOLFRAMALPHA_APPID=    # WolframAlpha API key (optional)
    CAS_WOLFRAMALPHA_TIMEOUT=10 # WolframAlpha request timeout (seconds)
    CAS_LOG_LEVEL=INFO         # Logging level
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from cas_service.engines.base import Capability, ComputeRequest
from cas_service.engines.matlab_engine import MatlabEngine
from cas_service.engines.sage_engine import SageEngine
from cas_service.engines.sympy_engine import SympyEngine
from cas_service.engines.wolframalpha_engine import WolframAlphaEngine
from cas_service.preprocessing import preprocess_latex

logger = logging.getLogger(__name__)

# Engine registry (initialized once at startup)
ENGINES: dict[str, Any] = {}

_start_time: float = 0.0

# Default validation engine (set during init, overridable via CAS_DEFAULT_ENGINE)
_default_engine: str = ""

# Thread pool for parallel validation (one thread per engine)
_validate_pool: ThreadPoolExecutor | None = None


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

        consensus = data.get("consensus", False)
        engines_explicit = data.get("engines")

        # Determine which engines to use:
        # - "engines" explicit list → use those
        # - "consensus": true → all validation engines
        # - default → single default engine
        if engines_explicit is not None:
            engines_requested = engines_explicit
        elif consensus:
            engines_requested = [
                n for n, e in ENGINES.items()
                if Capability.VALIDATE in e.capabilities and e.is_available()
            ]
        else:
            engines_requested = [_default_engine] if _default_engine else list(ENGINES.keys())

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

        # Run engines in parallel via ThreadPoolExecutor
        results = _validate_parallel(engines_requested, preprocessed)

        elapsed = int((time.time() - start) * 1000)

        # Log request
        successes = sum(1 for r in results if r.get("success"))
        logger.info(
            "validate latex=%s engines=%d success=%d time_ms=%d consensus=%s",
            latex[:50], len(results), successes, elapsed, consensus,
        )

        self._send_json({
            "results": results,
            "consensus": consensus,
            "latex_preprocessed": preprocessed,
            "time_ms": elapsed,
        })

    def _handle_health(self) -> None:
        available_count = sum(
            1 for e in ENGINES.values() if e.is_available()
        )
        self._send_json({
            "status": "ok",
            "service": "cas-service",
            "uptime_seconds": round(time.time() - _start_time, 1),
            "engines_total": len(ENGINES),
            "engines_available": available_count,
        })

    def _handle_status(self) -> None:
        engines_info = {}
        for name, engine in ENGINES.items():
            info: dict[str, Any] = {
                "available": engine.is_available(),
                "version": engine.get_version(),
            }
            engines_info[name] = info

        self._send_json({
            "service": "cas-service",
            "version": "0.3.0",
            "uptime_seconds": round(time.time() - _start_time, 1),
            "default_engine": _default_engine,
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

        start = time.time()
        request = ComputeRequest(
            engine=engine_name,
            task_type=task_type,
            template=template,
            inputs={str(k): str(v) for k, v in inputs.items()},
            timeout_s=int(timeout_s),
        )
        result = engine.compute(request)
        elapsed = int((time.time() - start) * 1000)

        # Log request
        logger.info(
            "compute engine=%s template=%s success=%s time_ms=%d",
            engine_name, template, result.success, elapsed,
        )

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
            entry: dict[str, Any] = {
                "name": name,
                "available": engine.is_available(),
                "version": engine.get_version(),
                "capabilities": [c.value for c in engine.capabilities],
                "description": engine.__class__.__doc__ or "",
            }
            reason = getattr(engine, "availability_reason", None)
            if reason is not None:
                entry["availability_reason"] = reason
            engine_list.append(entry)
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


def _validate_parallel(
    engine_names: list[str], preprocessed: str,
) -> list[dict[str, Any]]:
    """Run validation across multiple engines in parallel.

    Each engine runs in its own thread. Results are returned in the
    same order as engine_names.
    """
    if len(engine_names) <= 1 or _validate_pool is None:
        # Single engine or no pool: run sequentially
        results = []
        for name in engine_names:
            result = _validate_one(name, preprocessed)
            results.append(result)
        return results

    # Submit all engines to thread pool
    future_to_name = {}
    for name in engine_names:
        future = _validate_pool.submit(_validate_one, name, preprocessed)
        future_to_name[future] = name

    # Collect results preserving original order
    result_map: dict[str, dict] = {}
    for future in as_completed(future_to_name):
        name = future_to_name[future]
        try:
            result_map[name] = future.result()
        except Exception as exc:
            logger.exception("Engine %s raised exception during validation", name)
            result_map[name] = {
                "engine": name,
                "success": False,
                "is_valid": None,
                "simplified": None,
                "original_parsed": None,
                "error": str(exc),
                "time_ms": 0,
            }

    return [result_map[name] for name in engine_names]


def _validate_one(engine_name: str, preprocessed: str) -> dict[str, Any]:
    """Validate with a single engine, catching any exception."""
    engine = ENGINES[engine_name]
    try:
        result = engine.validate(preprocessed)
        return {
            "engine": result.engine,
            "success": result.success,
            "is_valid": result.is_valid,
            "simplified": result.simplified,
            "original_parsed": result.original_parsed,
            "error": result.error,
            "time_ms": result.time_ms,
        }
    except Exception as exc:
        logger.exception("Engine %s validation error", engine_name)
        return {
            "engine": engine_name,
            "success": False,
            "is_valid": None,
            "simplified": None,
            "original_parsed": None,
            "error": str(exc),
            "time_ms": 0,
        }


def _init_engines() -> None:
    """Initialize engine registry with graceful per-engine failure handling."""
    global ENGINES, _validate_pool, _default_engine

    engine_configs = [
        ("sympy", lambda: SympyEngine(
            timeout=int(os.environ.get("CAS_SYMPY_TIMEOUT", "5")),
        )),
        ("matlab", lambda: MatlabEngine(
            matlab_path=os.environ.get("CAS_MATLAB_PATH", "matlab"),
            timeout=int(os.environ.get("CAS_MATLAB_TIMEOUT", "30")),
        )),
        ("sage", lambda: SageEngine(
            sage_path=os.environ.get("CAS_SAGE_PATH", "sage"),
            timeout=int(os.environ.get("CAS_SAGE_TIMEOUT", "30")),
        )),
        ("wolframalpha", lambda: WolframAlphaEngine(
            app_id=os.environ.get("CAS_WOLFRAMALPHA_APPID", ""),
            timeout=int(os.environ.get("CAS_WOLFRAMALPHA_TIMEOUT", "10")),
        )),
    ]

    for name, factory in engine_configs:
        try:
            engine = factory()
            ENGINES[name] = engine
            available = engine.is_available()
            version = engine.get_version()
            logger.info(
                "Engine %s: available=%s version=%s", name, available, version,
            )
        except Exception:
            logger.exception("Failed to initialize engine %s — skipping", name)

    available_count = sum(1 for e in ENGINES.values() if e.is_available())
    logger.info(
        "Initialized %d engines (%d available)", len(ENGINES), available_count,
    )

    # Set default validation engine: env override > sage > sympy > first available
    env_default = os.environ.get("CAS_DEFAULT_ENGINE", "")
    if env_default and env_default in ENGINES and ENGINES[env_default].is_available():
        _default_engine = env_default
    else:
        # Prefer sage, then sympy, then first available validation engine
        for candidate in ["sage", "sympy"]:
            if candidate in ENGINES and ENGINES[candidate].is_available():
                _default_engine = candidate
                break
        else:
            for name, engine in ENGINES.items():
                if Capability.VALIDATE in engine.capabilities and engine.is_available():
                    _default_engine = name
                    break
    if _default_engine:
        logger.info("Default validation engine: %s", _default_engine)

    # Create thread pool sized to number of engines
    _validate_pool = ThreadPoolExecutor(
        max_workers=max(len(ENGINES), 2),
        thread_name_prefix="cas-validate",
    )


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
        if _validate_pool:
            _validate_pool.shutdown(wait=False)
        server.server_close()
        logger.info("CAS service stopped")


if __name__ == "__main__":
    main()
