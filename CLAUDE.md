# CLAUDE.md — Hoff Backend

## Product Overview

Hoff is an AI-powered tool that **automatically discovers and extracts onboarding workflows from any website**. A browser extension sends a URL (with optional session cookies), and the backend uses LLM-driven browser agents to navigate the site, identify key user journeys, and return structured step-by-step guides with CSS selectors pointing to exact UI elements.

### Core Pipeline

```
Client (browser extension)
  → POST /query {url, query, cookies}
    → Research LLM (optional): navigation hints from product knowledge
    → Browser agent: navigates site, calls resolve_selector per element
    → 3-layer selector validation pipeline
    → Selector review: structural vs dynamic classification
    → Brand extraction (parallel): colors, fonts, border-radius
  ← SSE stream: phases, thoughts, screenshots, workflow JSON, brand
  → Persisted to database by domain
```

### Key Concepts

- **Workflow**: A named user journey (e.g., "Create a project") with ordered Steps
- **Step**: A single UI interaction — carries a CSS selector (or text fallback), title, description, tooltip side, and a `dynamic` flag
- **Brand**: Visual identity tokens extracted from a page (colors, font, border-radius)
- **WorkflowSpec**: Lightweight name+description used between discovery and extraction phases
- **ResearchContext**: Optional LLM-generated navigation hints to guide extraction

---

## Tech Stack

- **Python 3.12+** — required minimum
- **uv** — package manager (replaces pip/poetry)
- **FastAPI** — web framework
- **browser-use** — LLM-driven browser automation (wraps Playwright)
- **LangChain** — LLM abstraction (OpenAI, Anthropic, Gemini providers)
- **Motor** — async MongoDB driver
- **SSE (sse-starlette)** — server-sent events for real-time streaming
- **Pydantic v2** — data validation and settings
- **pytest** — testing framework (with pytest-asyncio for async tests)

---

## Running the Project

```bash
# Install dependencies
uv sync

# Copy and fill environment variables
cp .env.example .env

# Run the dev server
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
uv run pytest

# Run linter
uv run ruff check .

# Run formatter
uv run ruff format .
```

### Environment Variables

| Variable | Required | Description |
|---|---|---|
| `LLM_PROVIDER` | Yes | `browser-use`, `openai`, `anthropic`, or `gemini` |
| `LLM_MODEL` | No | Override default model for the chosen provider |
| `RESEARCH_PROVIDER` | No | `gemini` (default) or `minimax` |
| `RESEARCH_MODEL` | No | Override default research model |
| `BROWSER_USE_API_KEY` | If provider=browser-use | API key for browser-use |
| `OPENAI_API_KEY` | If provider=openai | OpenAI API key |
| `ANTHROPIC_API_KEY` | If provider=anthropic | Anthropic API key |
| `GEMINI_API_KEY` | If provider=gemini | Google Gemini API key |
| `MONGODB_URI` | Yes | MongoDB connection string (include database name) |
| `DATABASE_URL` | If using PostgreSQL | PostgreSQL connection string |

---

## Architecture — Domain-Driven Design

### Target Directory Structure

The codebase is moving toward a **ports & adapters** (hexagonal) architecture organized by bounded context. Each domain owns its models, use cases, and port interfaces. Infrastructure adapters live at the edges.

```
app/
├── main.py                          # FastAPI app, middleware, lifespan
├── config.py                        # Pydantic settings
│
├── domain/                          # ── DOMAIN LAYER (pure, no framework deps) ──
│   ├── workflows/
│   │   ├── models.py                # Workflow, Step, WorkflowSpec, WorkflowsResponse
│   │   ├── events.py                # Domain events (SSE event factories)
│   │   └── ports.py                 # WorkflowRepository protocol
│   │
│   ├── branding/
│   │   ├── models.py                # Brand
│   │   └── ports.py                 # BrandExtractor protocol
│   │
│   └── research/
│       ├── models.py                # ResearchContext
│       └── ports.py                 # ResearchProvider protocol
│
├── application/                     # ── APPLICATION LAYER (use cases / orchestration) ──
│   ├── crawl_service.py             # Full crawl: discovery → extraction → branding
│   ├── query_service.py             # Single query: research → extraction → review
│   ├── crawl_stream_service.py      # Streaming crawl with SSE events
│   ├── query_stream_service.py      # Streaming query with SSE events
│   └── job_manager.py              # In-memory async job queue
│
├── infrastructure/                  # ── INFRASTRUCTURE LAYER (adapters) ──
│   ├── persistence/
│   │   ├── mongodb/
│   │   │   ├── client.py            # Motor client lifecycle
│   │   │   └── workflow_repo.py     # MongoWorkflowRepository (implements port)
│   │   └── postgresql/
│   │       ├── client.py            # asyncpg/SQLAlchemy async client
│   │       └── workflow_repo.py     # PostgresWorkflowRepository (implements port)
│   │
│   ├── llm/
│   │   ├── factory.py               # get_llm() provider factory
│   │   ├── research_gemini.py       # Gemini research adapter
│   │   └── research_minimax.py      # MiniMax research adapter
│   │
│   ├── browser/
│   │   ├── discovery_agent.py       # Discovery agent (browser-use)
│   │   ├── extraction_agent.py      # Extraction agent (browser-use)
│   │   ├── selector.py              # CSS selector builder + resolve_selector action
│   │   ├── validate.py              # Post-extraction selector validation
│   │   ├── review.py                # Selector structural/dynamic classification
│   │   └── brand_extractor.py       # Playwright-based brand extraction
│   │
│   └── prompts/
│       ├── discovery.py             # Discovery agent system + task prompts
│       └── extraction.py            # Extraction agent system + task prompts
│
├── api/                             # ── API LAYER (FastAPI routers + deps) ──
│   ├── dependencies.py              # Dependency injection (get_repo, get_settings, etc.)
│   ├── crawl_router.py
│   ├── query_router.py
│   ├── jobs_router.py
│   └── stream_router.py
│
└── tests/                           # ── TESTS ──
    ├── conftest.py                  # Shared fixtures (in-memory repo, fake LLM, etc.)
    ├── unit/
    │   ├── domain/                  # Pure model/logic tests
    │   └── infrastructure/          # Adapter-specific tests
    └── integration/
        └── api/                     # FastAPI TestClient tests
```

### Layer Rules

| Layer | May depend on | Must NOT depend on |
|---|---|---|
| **Domain** | Nothing (pure Python + Pydantic) | Application, Infrastructure, API, FastAPI |
| **Application** | Domain | Infrastructure, API, FastAPI |
| **Infrastructure** | Domain, external libs | Application, API |
| **API** | Application, Domain, FastAPI | Infrastructure (use DI) |

### Ports & Adapters Pattern

**Ports** are abstract interfaces (Python `Protocol` classes) defined in the domain layer. **Adapters** are concrete implementations in the infrastructure layer. The application layer depends only on ports; the API layer wires adapters via FastAPI dependency injection.

```python
# domain/workflows/ports.py
from typing import Protocol

class WorkflowRepository(Protocol):
    async def save(self, result: CrawlResponse, screenshots_map: dict[int, list[str]] | None = None) -> None: ...
    async def get_by_domain(self, domain: str) -> dict | None: ...
    async def soft_delete(self, domain: str, workflow_name: str) -> bool: ...


# infrastructure/persistence/mongodb/workflow_repo.py
class MongoWorkflowRepository:
    """Implements WorkflowRepository using Motor (async MongoDB)."""
    ...


# infrastructure/persistence/postgresql/workflow_repo.py
class PostgresWorkflowRepository:
    """Implements WorkflowRepository using SQLAlchemy async."""
    ...


# api/dependencies.py
from fastapi import Depends

def get_workflow_repo() -> WorkflowRepository:
    # Wire the concrete adapter here — single place to swap implementations
    ...
```

### Dependency Injection

Use **FastAPI's `Depends()`** to inject adapters into routers. Never import infrastructure directly in routers or application services — always go through a port or a dependency function.

```python
# In routers
@router.get("/workflows/{domain}")
async def get_workflows(
    domain: str,
    repo: WorkflowRepository = Depends(get_workflow_repo),
):
    doc = await repo.get_by_domain(domain)
    ...
```

---

## FastAPI Best Practices

### Router Organization
- One router per bounded context / resource
- Keep route handlers thin — delegate to application services
- Use `response_model` to enforce response schemas
- Use Pydantic models for all request bodies (never raw dicts)

### Error Handling
- Use `HTTPException` with appropriate status codes in routers only
- Application/domain layers raise domain-specific exceptions (e.g., `WorkflowNotFoundError`)
- Routers catch domain exceptions and translate to HTTP responses
- Never expose internal stack traces in production responses

```python
# domain/workflows/exceptions.py
class WorkflowNotFoundError(Exception):
    def __init__(self, domain: str):
        self.domain = domain

# In the router
try:
    result = await service.get_workflows(domain)
except WorkflowNotFoundError:
    raise HTTPException(status_code=404, detail="No workflows found")
```

### Lifespan Management
- Use FastAPI's `lifespan` context manager for startup/shutdown
- Initialize and tear down database connections, indexes, etc. in lifespan
- Never use `@app.on_event` (deprecated)

### Middleware
- CORS is configured permissively (`allow_origins=["*"]`) for local extension development — restrict in production
- `PrivateNetworkMiddleware` enables Chrome extensions on HTTPS to reach localhost

### Streaming (SSE)
- Use `sse-starlette`'s `EventSourceResponse` for SSE endpoints
- Yield structured event dicts: `{"event": "<type>", "data": "<json>"}`
- Always emit a `done` event at the end of a stream
- Emit `error` events on failure before `done`

---

## Coding Conventions

### General
- **Python 3.12+** features are encouraged: `type` statements, `X | Y` unions, etc.
- Use `from __future__ import annotations` only when needed for forward references
- Prefer composition over inheritance
- No wildcard imports (`from x import *`)
- Keep functions short and focused — extract helpers when a function exceeds ~40 lines

### Type Annotations
- All public function signatures must have type annotations
- Use `str | None` over `Optional[str]`
- Use `list[X]` over `List[X]` (lowercase generics)
- Use `Protocol` for port interfaces (structural subtyping)

### Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private helpers: prefix with `_`

### Pydantic Models
- Use Pydantic v2 style (`model_validate`, `model_dump`, `model_copy`)
- Define `field_validator` for input sanitization on domain models
- Use `BaseSettings` for configuration (with `.env` file support)
- Prefer `model_validate_json()` over manual `json.loads()` + `model_validate()`

### Async
- All I/O-bound operations must be `async`
- Use `asyncio.create_task()` for concurrent work (e.g., branding runs alongside extraction)
- Use `asyncio.gather()` for parallel fan-out (e.g., extracting multiple workflows)
- Offload CPU-heavy work (image resizing) to `run_in_executor()`
- Never use blocking calls in async functions

### Logging
- Use `logging.getLogger(__name__)` per module
- Log at `INFO` for business events (phase transitions, completions)
- Log at `WARNING` for recoverable failures (extraction returned no result)
- Log at `ERROR`/`EXCEPTION` for unexpected failures
- Never log secrets or full API responses

---

## Testing Strategy

### Framework: pytest + pytest-asyncio

```
tests/
├── conftest.py            # Shared fixtures
├── unit/
│   ├── domain/            # Pure model and logic tests (fast, no I/O)
│   │   ├── test_models.py
│   │   └── test_selector_validation.py
│   └── infrastructure/
│       ├── test_selector_builder.py
│       └── test_brand_extractor.py
└── integration/
    └── api/
        ├── test_crawl_router.py
        └── test_query_router.py
```

### Test Principles
- **Unit tests** cover domain models, validators, selector logic — no network, no browser, no database
- **Integration tests** use FastAPI's `TestClient` with injected in-memory/mock adapters
- Test files mirror the source structure under `tests/`
- Use `@pytest.mark.asyncio` for async tests
- Use `conftest.py` fixtures for reusable test setup (fake repos, mock settings)

### In-Memory Adapter for Testing

```python
# tests/conftest.py
class InMemoryWorkflowRepository:
    def __init__(self):
        self._store: dict[str, dict] = {}

    async def save(self, result, screenshots_map=None):
        ...

    async def get_by_domain(self, domain):
        return self._store.get(domain)

    async def soft_delete(self, domain, workflow_name):
        ...
```

### Running Tests

```bash
# All tests
uv run pytest

# Unit tests only
uv run pytest tests/unit/

# With coverage
uv run pytest --cov=app --cov-report=term-missing

# Specific test
uv run pytest tests/unit/domain/test_models.py -v
```

---

## Linting & Formatting

### Ruff (linter + formatter)

Ruff replaces flake8, isort, and black in a single fast tool.

```bash
# Lint
uv run ruff check .

# Lint with auto-fix
uv run ruff check . --fix

# Format
uv run ruff format .
```

Recommended `pyproject.toml` config:

```toml
[tool.ruff]
target-version = "py312"
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N", "UP", "B", "A", "SIM", "TCH"]
ignore = ["E501"]  # line length handled by formatter

[tool.ruff.lint.isort]
known-first-party = ["app"]
```

---

## Git Conventions

### Branch Naming
- `main` — production-ready code
- `feature/<short-description>` — new features
- `fix/<short-description>` — bug fixes
- `claude/<description>-<session-id>` — Claude Code sessions

### Commit Messages
- Use imperative mood: "Add workflow research phase", not "Added..."
- Keep the first line under 72 characters
- Reference issue numbers when applicable: "Fix selector validation (#42)"

### PR Workflow
- One logical change per PR
- PRs must pass linting and tests before merge
- Squash-merge to keep main history clean

---

## CI / Deployment

### Docker

```dockerfile
FROM python:3.12-slim

# Install system deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk-bridge2.0-0 libdrm2 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libasound2 libpangocairo-1.0-0 libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .
RUN uv run playwright install chromium

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### CI Pipeline (GitHub Actions)

A CI pipeline should:
1. **Lint**: `uv run ruff check .`
2. **Format check**: `uv run ruff format . --check`
3. **Type check**: `uv run pyright` (optional, if adopted)
4. **Test**: `uv run pytest --cov=app`
5. **Build**: Docker image build (on main only)

---

## Current State & Migration Notes

The codebase currently uses a **flat module structure** (`app/agents/`, `app/modules/`, `app/routers/`, `app/services/`). The target is the DDD structure documented above. Migration should be incremental:

1. **Phase 1**: Define domain models and port interfaces in `domain/` — this is a pure extraction, no logic changes
2. **Phase 2**: Create adapters in `infrastructure/` — wrap existing MongoDB code in `MongoWorkflowRepository`, add PostgreSQL adapter
3. **Phase 3**: Wire dependency injection in `api/dependencies.py` — routers use `Depends()` instead of direct imports
4. **Phase 4**: Move orchestration logic from `services/` into `application/` layer
5. **Phase 5**: Add tests at each layer, starting with unit tests on domain models and selector logic

### What NOT to Change

- The 3-layer selector validation pipeline is well-designed — preserve it
- The SSE streaming architecture works well — keep the event factory pattern
- The `browser-use` agent integration is solid — just relocate files, don't restructure the agent logic
- Prompt files are well-organized — move to `infrastructure/prompts/` as-is
