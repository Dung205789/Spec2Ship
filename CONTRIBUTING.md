# Contributing to Spec2Ship

Thanks for your interest in improving Spec2Ship! This guide explains how to set
up a dev environment and the expectations for contributions.

## Development setup

```bash
# 1. Configure environment
make setup            # copies .env.example -> .env

# 2. Start the full stack with hot reload
make dev              # API + worker + web + postgres + redis

# 3. (optional) Run with local LLM inference
make dev-llm          # adds an Ollama service
```

Services after startup:

| Service | URL |
| --- | --- |
| Web UI | http://localhost:3000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Health check | http://localhost:8000/healthz |

### Backend without Docker

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

## Code style

- **Python:** formatted and linted with [Ruff](https://docs.astral.sh/ruff/)
  (`ruff format .` then `ruff check .`). Line length 100, target Python 3.11.
- Type hints are expected on public functions.
- Keep services pure where possible; side effects belong in `use_cases/` and
  `repositories/`.

Install the pre-commit hooks so this runs automatically:

```bash
pip install pre-commit
pre-commit install
```

## Pull requests

- Keep PRs small, focused, and easy to review.
- Use the PR template: **Problem → Approach → Validation**.
- Run `ruff check .`, `ruff format --check .`, and `pytest -q` before opening a PR.
- Never commit secrets, credentials, or runtime data (`data/`, `artifacts/`).
- All CI checks must pass before merge.

## Project layout

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full system design and
[`README.md`](README.md) for the directory map.
