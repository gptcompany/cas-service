# CAS Service

Multi-engine Computer Algebra System microservice. Validates mathematical formulas using SymPy, Maxima, and optionally MATLAB with consensus-based verification.

## Quick Setup

```bash
uv sync --extra setup
cas-setup              # Interactive guided setup
```

The wizard checks Python, SymPy, Maxima (and optionally MATLAB), then configures and starts the service.

Subcommands: `cas-setup engines | service | verify`

## Manual Setup

```bash
uv sync
# Install Maxima: sudo apt install maxima (Ubuntu) / brew install maxima (macOS)
uv run python -m cas_service.main
```

## Requirements

| Dependency | Required | Notes |
|-----------|----------|-------|
| Python >= 3.11 | Yes | |
| SymPy >= 1.13 | Yes | Installed via uv |
| Maxima >= 5.44 | Yes | System package |
| MATLAB | No | Optional engine, improves consensus |

## API

Default port: **8769**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET /health` | Health check |
| `GET /engines` | List available CAS engines |
| `POST /validate` | Validate a LaTeX formula |

### Validate Example

```bash
curl -s -X POST http://localhost:8769/validate \
  -H "Content-Type: application/json" \
  -d '{"latex": "x^2 + 2*x + 1", "cas": "maxima"}' | jq .
```

## Engines

- **SymPy** — Pure Python CAS, always available
- **Maxima** — GPL CAS with strong symbolic algebra support
- **MATLAB** — Commercial CAS, optional. Requires valid license

Consensus validation: formula is VALID only if all available engines agree.
