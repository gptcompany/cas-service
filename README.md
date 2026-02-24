# CAS Service

Multi-engine Computer Algebra System microservice. Validates mathematical formulas using SymPy, SageMath, and optionally MATLAB with consensus-based verification. Supports template-based compute via SageMath (including group theory) and optional WolframAlpha backend. Engines run in parallel for validation.

## Quick Setup

```bash
uv sync --extra setup
cas-setup              # Interactive guided setup
```

The wizard checks Python, SymPy, MATLAB, SageMath, and WolframAlpha, configures paths/keys to `.env`, and starts the service.

Subcommands: `cas-setup engines | configure | service | verify`

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
| SymPy >= 1.13 | Yes | validate | Pure Python CAS, always available |
| SageMath 9.5+ | Yes | validate, compute | Full CAS: 11 compute templates (incl. group theory) |
| MATLAB | No | validate | Commercial CAS, optional |
| WolframAlpha | No | compute, remote | Remote API oracle |

- **Validation engines** run in parallel via ThreadPoolExecutor
- **Consensus**: formula is VALID only if all available engines agree
- **Graceful degradation**: service starts even if some engines are unavailable

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

Default port: **8769**

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET /health` | Health check (includes engine count) |
| `GET /status` | Full status with engine versions |
| `GET /engines` | List engines with capabilities and versions |
| `POST /validate` | Validate LaTeX formula (default: single engine, opt-in consensus) |
| `POST /compute` | Run a template-based compute task |

### Validate Example

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

### systemd

```bash
cas-setup service       # Generates cas-service.service
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
cas-setup configure     # Re-configure engine paths and API keys
cas-setup verify        # Verify running service + smoke test all engines
```
