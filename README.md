# CAS Service

Multi-engine Computer Algebra System microservice. Validates mathematical formulas using SymPy, Maxima, and optionally MATLAB with consensus-based verification. Supports template-based compute via GAP and optional WolframAlpha backend.

## Quick Setup

```bash
uv sync --extra setup
cas-setup              # Interactive guided setup
```

The wizard checks Python, SymPy, Maxima, GAP, MATLAB, SageMath, and WolframAlpha, then configures and starts the service.

Subcommands: `cas-setup engines | service | verify`

## Manual Setup

```bash
uv sync
# Install Maxima: sudo apt install maxima (Ubuntu) / brew install maxima (macOS)
uv run python -m cas_service.main
```

## Requirements

| Dependency | Required | Capability | Notes |
|-----------|----------|------------|-------|
| Python >= 3.11 | Yes | - | |
| SymPy >= 1.13 | Yes | validate | Installed via uv |
| Maxima >= 5.44 | Yes | validate | System package |
| MATLAB | No | validate | Optional, improves consensus |
| GAP | No | compute | Computational group theory |
| SageMath | No | - | Detection only (future engine) |
| WolframAlpha | No | compute, remote | Needs `CAS_WOLFRAMALPHA_APPID` |

## API

Default port: **8769**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET /health` | Health check |
| `GET /engines` | List available CAS engines (with capabilities) |
| `POST /validate` | Validate a LaTeX formula |
| `POST /compute` | Run a template-based compute task |

### Validate Example

```bash
curl -s -X POST http://localhost:8769/validate \
  -H "Content-Type: application/json" \
  -d '{"latex": "x^2 + 2*x + 1", "cas": "maxima"}' | jq .
```

### Compute Example

```bash
curl -s -X POST http://localhost:8769/compute \
  -H "Content-Type: application/json" \
  -d '{"engine": "gap", "task_type": "template", "template": "group_order", "inputs": {"group_expr": "SymmetricGroup(4)"}}' | jq .
```

The `/compute` endpoint accepts template-only tasks. Each engine declares its capabilities (`validate`, `compute`, `remote`) via `/engines`.

## Engines

### Validation Engines
- **SymPy** — Pure Python CAS, always available
- **Maxima** — GPL CAS with strong symbolic algebra support
- **MATLAB** — Commercial CAS, optional. Requires valid license

Consensus validation: formula is VALID only if all available engines agree.

### Compute Engines
- **GAP** — Computational group theory (template-only: `group_order`, `is_abelian`, `center_size`)
- **WolframAlpha** — Remote compute oracle, optional (`CAS_WOLFRAMALPHA_APPID`)

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CAS_PORT` | `8769` | HTTP listen port |
| `CAS_MAXIMA_PATH` | `/usr/bin/maxima` | Maxima binary |
| `CAS_GAP_PATH` | `gap` | GAP binary |
| `CAS_GAP_TIMEOUT` | `10` | GAP subprocess timeout (s) |
| `CAS_WOLFRAMALPHA_APPID` | - | WolframAlpha API key |
| `CAS_LOG_LEVEL` | `INFO` | Logging level |
