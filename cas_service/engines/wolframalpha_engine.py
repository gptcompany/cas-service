"""WolframAlpha engine — optional remote compute oracle."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from cas_service.engines.base import (
    BaseEngine,
    Capability,
    ComputeRequest,
    ComputeResult,
    EngineResult,
)

logger = logging.getLogger(__name__)

_WA_API_URL = "https://api.wolframalpha.com/v2/query"

# Templates map to WolframAlpha query strings
_TEMPLATES: dict[str, dict[str, Any]] = {
    "evaluate": {
        "required_inputs": ["expression"],
        "build_query": lambda inputs: inputs["expression"],
        "description": "Evaluate a mathematical expression",
    },
    "solve": {
        "required_inputs": ["equation"],
        "build_query": lambda inputs: f"solve {inputs['equation']}",
        "description": "Solve an equation",
    },
    "simplify": {
        "required_inputs": ["expression"],
        "build_query": lambda inputs: f"simplify {inputs['expression']}",
        "description": "Simplify a mathematical expression",
    },
}


class WolframAlphaEngine(BaseEngine):
    """WolframAlpha remote compute engine — optional, needs CAS_WOLFRAMALPHA_APPID."""

    name = "wolframalpha"

    def __init__(self, app_id: str | None = None, timeout: int = 10) -> None:
        if app_id is None:
            self._app_id = os.environ.get("CAS_WOLFRAMALPHA_APPID", "")
        else:
            self._app_id = app_id
        self.timeout = timeout

    def validate(self, latex: str) -> EngineResult:
        """WolframAlpha is not used for consensus validation."""
        return EngineResult(
            engine=self.name,
            success=False,
            error="WolframAlpha is not part of the validation consensus",
        )

    def compute(self, request: ComputeRequest) -> ComputeResult:
        start = time.time()

        if not self.is_available():
            return ComputeResult(
                engine=self.name,
                success=False,
                error="WolframAlpha API key not configured",
                error_code="ENGINE_UNAVAILABLE",
                time_ms=int((time.time() - start) * 1000),
            )

        tmpl = _TEMPLATES.get(request.template)
        if tmpl is None:
            return ComputeResult(
                engine=self.name,
                success=False,
                error=f"Unknown template: {request.template}",
                error_code="UNKNOWN_TEMPLATE",
                time_ms=int((time.time() - start) * 1000),
            )

        missing = [k for k in tmpl["required_inputs"] if k not in request.inputs]
        if missing:
            return ComputeResult(
                engine=self.name,
                success=False,
                error=f"Missing required inputs: {', '.join(missing)}",
                error_code="MISSING_INPUT",
                time_ms=int((time.time() - start) * 1000),
            )

        query = tmpl["build_query"](request.inputs)
        timeout_s = min(request.timeout_s, self.timeout)
        return self._call_api(query, timeout_s, start)

    def _call_api(
        self,
        query: str,
        timeout_s: int,
        start: float,
    ) -> ComputeResult:
        """Call the WolframAlpha Full Results API."""
        params = urllib.parse.urlencode(
            {
                "input": query,
                "appid": self._app_id,
                "format": "plaintext",
                "output": "json",
            }
        )
        url = f"{_WA_API_URL}?{params}"

        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data = json.loads(resp.read().decode())

            elapsed = int((time.time() - start) * 1000)
            return self._parse_response(data, elapsed)

        except urllib.error.HTTPError as exc:
            elapsed = int((time.time() - start) * 1000)
            if exc.code == 403:
                return ComputeResult(
                    engine=self.name,
                    success=False,
                    time_ms=elapsed,
                    error="WolframAlpha API: invalid or expired AppID",
                    error_code="AUTH_ERROR",
                )
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                error=f"WolframAlpha API HTTP {exc.code}",
                error_code="REMOTE_ERROR",
            )
        except urllib.error.URLError as exc:
            elapsed = int((time.time() - start) * 1000)
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                error=f"Network error: {exc.reason}",
                error_code="NETWORK_ERROR",
            )
        except TimeoutError:
            elapsed = int((time.time() - start) * 1000)
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                error=f"WolframAlpha timed out after {timeout_s}s",
                error_code="TIMEOUT",
            )
        except Exception as exc:
            logger.exception("WolframAlpha API error")
            elapsed = int((time.time() - start) * 1000)
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                error=str(exc),
                error_code="REMOTE_ERROR",
            )

    def _parse_response(
        self,
        data: dict,
        elapsed: int,
    ) -> ComputeResult:
        """Extract result from WolframAlpha JSON response."""
        queryresult = data.get("queryresult", {})

        if not queryresult.get("success"):
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                error="WolframAlpha could not interpret the query",
                error_code="QUERY_FAILED",
                stdout=json.dumps(queryresult.get("tips", {})),
            )

        # Extract primary result from "Result" or "Decimal approximation" pod
        result_text = None
        for pod in queryresult.get("pods", []):
            pod_id = pod.get("id", "")
            if pod_id in ("Result", "DecimalApproximation", "Solution"):
                subpods = pod.get("subpods", [])
                if subpods:
                    result_text = subpods[0].get("plaintext", "")
                    break

        # Fallback: use first non-Input pod
        if not result_text:
            for pod in queryresult.get("pods", []):
                if pod.get("id") != "Input":
                    subpods = pod.get("subpods", [])
                    if subpods and subpods[0].get("plaintext"):
                        result_text = subpods[0]["plaintext"]
                        break

        if not result_text:
            return ComputeResult(
                engine=self.name,
                success=False,
                time_ms=elapsed,
                error="No result found in WolframAlpha response",
                error_code="NO_RESULT",
            )

        return ComputeResult(
            engine=self.name,
            success=True,
            time_ms=elapsed,
            result={"value": result_text},
            stdout=result_text,
        )

    def is_available(self) -> bool:
        return bool(self._app_id)

    def get_version(self) -> str:
        return "v2-api"

    @property
    def availability_reason(self) -> str | None:
        """Return reason if unavailable, None if available."""
        if not self._app_id:
            return "missing CAS_WOLFRAMALPHA_APPID"
        return None

    @property
    def capabilities(self) -> list[Capability]:
        return [Capability.COMPUTE, Capability.REMOTE]

    @classmethod
    def available_templates(cls) -> dict[str, str]:
        """Return template name -> description mapping."""
        return {k: v["description"] for k, v in _TEMPLATES.items()}
