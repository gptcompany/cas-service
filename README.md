# CAS Service

![CI](https://github.com/gptcompany/cas-service/actions/workflows/ci.yml/badge.svg?branch=main)
![Sandbox Validation](https://github.com/gptcompany/cas-service/actions/workflows/sandbox-validate.yml/badge.svg?branch=main)
![Coverage](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/gptprojectmanager/ac39e6516b7114f96b84ba445b8e7a83/raw/cas-service-coverage.json)
![Python](https://img.shields.io/badge/python-3.11%2B-blue?style=flat-square&logo=python)
![CAS Engines](https://img.shields.io/badge/CAS-SymPy%20%7C%20Sage%20%7C%20MATLAB%20%7C%20WA-orange?style=flat-square)
![License](https://img.shields.io/github/license/gptcompany/cas-service?style=flat-square)
![Last Commit](https://img.shields.io/github/last-commit/gptcompany/cas-service?style=flat-square)
![Issues](https://img.shields.io/github/issues/gptcompany/cas-service?style=flat-square)
![Lines of Code](https://sloc.xyz/github/gptcompany/cas-service)

Multi-engine Computer Algebra System microservice. Validates mathematical formulas using SymPy, SageMath, and optionally MATLAB with consensus-based verification. Supports template-based compute via SymPy (6 templates), SageMath (11 templates, incl. group theory), MATLAB (4 templates), and WolframAlpha (3 templates). Engines run in parallel for validation.

## Quick Setup

```bash
uv sync --extra setup
cas-setup              # Interactive guided setup
```

`cas-setup` (without subcommands) opens an interactive menu with per-step status, free navigation, and a `Run all pending` action.

The wizard covers Python/SymPy checks, optional MATLAB/SageMath/WolframAlpha configuration, deployment mode selection (`systemd` / `docker compose` / foreground), and service verification.

Subcommands (kept as linear flows): `cas-setup engines | configure | service | verify`

Practical notes:
- Optional steps (for example MATLAB or WolframAlpha) may be marked `Skipped` and do not fail the wizard.
- `cas-setup` exits `0` when all remaining steps are `OK` / `Skipped` / `Warning`; exits `1` on abort or unresolved `Pending` / `Failed` steps.

## Manual Setup

```bash
uv sync
# Install system CAS engines:
sudo apt install sagemath              # Ubuntu/Debian
uv run python -m cas_service.main
```

## Engines

| Engine | Required | Capabilities | Description |
|--------|----------|-------------|-------------|
| SymPy >= 1.13 | Yes | validate, compute | Pure Python CAS, always available. 6 compute templates |
| SageMath 9.5+ | Yes | validate, compute | Full CAS: 11 compute templates (incl. group theory) |
| MATLAB | No | validate, compute | Commercial CAS, optional. 4 compute templates |
| WolframAlpha | No | compute, remote | Remote API oracle |

- **Validation engines** run in parallel via ThreadPoolExecutor
- **Consensus**: formula is VALID only if all available engines agree
- **Graceful degradation**: service starts even if some engines are unavailable

### SymPy Compute Templates

| Template | Required Inputs | Description |
|----------|----------------|-------------|
| `evaluate` | `expression` | Evaluate a mathematical expression numerically |
| `simplify` | `expression` | Simplify a mathematical expression |
| `solve` | `equation`, `variable`? | Solve an equation (default: x) |
| `factor` | `expression` | Factor a polynomial |
| `integrate` | `expression`, `variable`? | Symbolic integration |
| `differentiate` | `expression`, `variable`? | Symbolic differentiation |

### MATLAB Compute Templates

| Template | Required Inputs | Description |
|----------|----------------|-------------|
| `evaluate` | `expression` | Evaluate via `str2sym` + `simplify` |
| `simplify` | `expression` | Simplify a mathematical expression |
| `solve` | `equation`, `variable`? | Solve an equation (default: x) |
| `factor` | `expression` | Factor a polynomial |

### SageMath Compute Templates

| Template | Required Inputs | Description |
|----------|----------------|-------------|
| `evaluate` | `expression` | Evaluate a mathematical expression |
| `simplify` | `expression` | Simplify a mathematical expression |
| `solve` | `equation`, `variable`? | Solve an equation (default: x) |
| `factor` | `expression` | Factor a polynomial |
| `integrate` | `expression`, `variable`? | Symbolic integration |
| `differentiate` | `expression`, `variable`? | Symbolic differentiation |
| `matrix_rank` | `matrix` | Compute matrix rank |
| `latex_to_sage` | `expression` | Parse LaTeX → Sage representation |
| `group_order` | `group_expr` | Compute the order (size) of a group |
| `is_abelian` | `group_expr` | Check if a group is abelian |
| `center_size` | `group_expr` | Compute the size of the center of a group |

### WolframAlpha Compute Templates

| Template | Required Inputs | Description |
|----------|----------------|-------------|
| `evaluate` | `expression` | Evaluate a mathematical expression |
| `solve` | `equation` | Solve an equation |
| `simplify` | `expression` | Simplify an expression |

## API

Default port: `CAS_PORT` (default `8769`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET /health` | Health check (includes engine count) |
| `GET /status` | Full status with engine versions |
| `GET /engines` | List engines with capabilities and versions |
| `POST /validate` | Validate LaTeX formula (default: single engine, opt-in consensus) |
| `POST /compute` | Run a template-based compute task |

### Validate Example

Examples below assume the default port (`CAS_PORT=8769`). If you changed it, replace
`localhost:8769` with your configured port.

```bash
# Default: single engine (SageMath if available, else SymPy)
curl -s -X POST http://localhost:8769/validate \
  -H "Content-Type: application/json" \
  -d '{"latex": "x^2 + 2*x + 1"}' | jq .

# Consensus: multi-engine parallel validation (opt-in)
curl -s -X POST http://localhost:8769/validate \
  -H "Content-Type: application/json" \
  -d '{"latex": "x^2 + 2*x + 1", "consensus": true}' | jq .

# Specific engines
curl -s -X POST http://localhost:8769/validate \
  -H "Content-Type: application/json" \
  -d '{"latex": "x^2 + 2*x + 1", "engines": ["sympy", "sage"]}' | jq .
```

### Compute Examples

```bash
# SymPy: simplify
curl -s -X POST http://localhost:8769/compute \
  -H "Content-Type: application/json" \
  -d '{"engine": "sympy", "task_type": "template", "template": "simplify", "inputs": {"expression": "x**2 + 2*x + 1"}}' | jq .

# SymPy: solve equation
curl -s -X POST http://localhost:8769/compute \
  -H "Content-Type: application/json" \
  -d '{"engine": "sympy", "task_type": "template", "template": "solve", "inputs": {"equation": "x**2 - 4", "variable": "x"}}' | jq .

# MATLAB: evaluate (requires MATLAB on PATH)
curl -s -X POST http://localhost:8769/compute \
  -H "Content-Type: application/json" \
  -d '{"engine": "matlab", "task_type": "template", "template": "evaluate", "inputs": {"expression": "2^10"}, "timeout_s": 60}' | jq .

# SageMath: group order
curl -s -X POST http://localhost:8769/compute \
  -H "Content-Type: application/json" \
  -d '{"engine": "sage", "task_type": "template", "template": "group_order", "inputs": {"group_expr": "SymmetricGroup(4)"}, "timeout_s": 30}' | jq .

# SageMath: factor polynomial
curl -s -X POST http://localhost:8769/compute \
  -H "Content-Type: application/json" \
  -d '{"engine": "sage", "task_type": "template", "template": "factor", "inputs": {"expression": "x^2 - 1"}, "timeout_s": 30}' | jq .

# SageMath: differentiate
curl -s -X POST http://localhost:8769/compute \
  -H "Content-Type: application/json" \
  -d '{"engine": "sage", "task_type": "template", "template": "differentiate", "inputs": {"expression": "x^3 + 2*x", "variable": "x"}, "timeout_s": 30}' | jq .
```

## Environment Variables

| Variable | Default | Engine | Description |
|----------|---------|--------|-------------|
| `CAS_PORT` | `8769` | - | HTTP listen port |
| `CAS_DEFAULT_ENGINE` | `sage` | - | Default validation engine (auto: sage > sympy > first) |
| `CAS_SYMPY_TIMEOUT` | `5` | SymPy | Parse/simplify timeout (s) |
| `CAS_MATLAB_PATH` | `matlab` | MATLAB | Binary path |
| `CAS_MATLAB_TIMEOUT` | `30` | MATLAB | Subprocess timeout (s) |
| `CAS_SAGE_PATH` | `sage` | SageMath | Binary path |
| `CAS_SAGE_TIMEOUT` | `30` | SageMath | Subprocess timeout (s) |
| `CAS_WOLFRAMALPHA_APPID` | - | WolframAlpha | API key (secret) |
| `CAS_WOLFRAMALPHA_TIMEOUT` | `10` | WolframAlpha | Request timeout (s) |
| `CAS_LOG_LEVEL` | `INFO` | - | Logging level |

## Deployment

### Docker Compose

```bash
docker compose build
dotenvx run -f .env -- docker compose up -d
curl -s localhost:8769/health | jq .
```

Or with an explicit shell fallback:

```bash
curl -s "localhost:${CAS_PORT:-8769}/health" | jq .
```

The `.env` file is encrypted with dotenvx. `dotenvx run` decrypts it and passes the environment variables to the container. If you don't use dotenvx, pass variables manually:

```bash
CAS_WOLFRAMALPHA_APPID=your-key docker compose up -d
```

To mount a MATLAB installation, uncomment the volumes section in `docker-compose.yml`:

```yaml
volumes:
  - /usr/local/MATLAB:/opt/matlab:ro
```

Stop: `docker compose down`

### systemd

```bash
cas-setup service       # Renders + installs cas-service.service for this machine
sudo systemctl enable cas-service
sudo systemctl start cas-service
```

### Foreground

```bash
uv run python -m cas_service.main
```

### Configuration

Engine paths and API keys are stored in the project `.env` file. Use the wizard to configure:

```bash
cas-setup configure     # Re-configure engine paths and API keys (linear subcommand)
cas-setup verify        # Verify running service + smoke test all engines (linear subcommand)
```
