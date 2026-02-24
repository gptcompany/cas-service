"""Project-level .env config file reader/writer for engine paths and keys."""

from __future__ import annotations

import os
import re
from pathlib import Path

# Project root .env (next to pyproject.toml)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
DEFAULT_CAS_PORT = 8769
DEFAULT_CAS_HOST = "localhost"


def env_path() -> Path:
    """Return the .env file path."""
    return _ENV_FILE


def read_config() -> dict[str, str]:
    """Read all CAS_* variables from the project .env file."""
    config: dict[str, str] = {}
    if not _ENV_FILE.exists():
        return config
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if match:
            key = match.group(1)
            value = match.group(2).strip("\"'")
            config[key] = value
    return config


def write_key(key: str, value: str) -> None:
    """Set a single key in the .env file (create if missing, update if exists)."""
    lines: list[str] = []
    found = False
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            if re.match(rf"^{re.escape(key)}=", line):
                lines.append(f"{key}={value}")
                found = True
            else:
                lines.append(line)
    if not found:
        lines.append(f"{key}={value}")
    _ENV_FILE.write_text("\n".join(lines) + "\n")


def get_key(key: str) -> str | None:
    """Get a single key value, checking .env then os.environ."""
    config = read_config()
    if key in config:
        return config[key]
    return os.environ.get(key) or None


def get_cas_port(default: int = DEFAULT_CAS_PORT) -> int:
    """Resolve CAS_PORT from config/env, with validation and fallback."""
    raw = get_key("CAS_PORT")
    if raw is None:
        return default
    try:
        port = int(raw)
    except ValueError:
        return default
    if not (1 <= port <= 65535):
        return default
    return port


def get_service_url(host: str = DEFAULT_CAS_HOST) -> str:
    """Return the local CAS base URL using the configured CAS_PORT."""
    return f"http://{host}:{get_cas_port()}"
