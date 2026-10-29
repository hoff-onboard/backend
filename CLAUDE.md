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
| `RESEARCH_PROVIDER` | No | `gemini` (default), `minimax`, or `openai` |
| `RESEARCH_MODEL` | No | Override default research model |
| `BROWSER_USE_API_KEY` | If provider=browser-use | API key for browser-use |
| `OPENAI_API_KEY` | If provider=openai | OpenAI API key |
| `ANTHROPIC_API_KEY` | If provider=anthropic | Anthropic API key |
| `GEMINI_API_KEY` | If provider=gemini | Google Gemini API key |
| `MONGODB_URI` | Yes | MongoDB connection string (include database name) |
| `DATABASE_URL` | If using PostgreSQL | PostgreSQL connection string |

---

## Architecture — Domain-Driven Design

### Directory Structure

Ports & adapters (hexagonal). The domain owns models and port interfaces, use cases in `application/` depend only on those ports, and `infrastructure/` holds the adapters. `api/dependencies.py` is the single composition root that picks adapters.

```
app/
├── main.py                          # FastAPI app, middleware, lifespan (Mongo indexes)
├── config.py                        # Pydantic settings from .env
│
├── domain/                          # ── DOMAIN (pure, imports nothing else from app) ──
│   ├── workflows/
│   │   ├── models.py                # Workflow, Step (+ selector validator), WorkflowSpec, AgentStep, requests
│   │   ├── events.py                # SSE event factories
│   │   └── ports.py                 # WorkflowRepository, WorkflowDiscoverer, WorkflowExtractor,
│   │                                #   SelectorReviewer, BrowserSessionStore, ResultArchive, StepCallback
│   ├── branding/                    # Brand + BrandExtractor port
│   └── research/                    # ResearchContext + ResearchProvider port
│
├── application/                     # ── USE CASES (depend on domain only) ──
│   ├── pipeline.py                  # Pipeline: the bundle of ports a use case needs; cancel_pending()
│   ├── query.py                     # run_query / stream_query: research → extract → review → save
│   ├── crawl.py                     # run_crawl / stream_crawl: discover → extract each flow
│   └── job_manager.py               # In-memory jobs: background task, SSE fan-out with replay, cancel
│
├── infrastructure/                  # ── ADAPTERS ──
│   ├── browser/
│   │   ├── agents.py                # BrowserUseDiscoverer, BrowserUseExtractor
│   │   ├── agent_runtime.py         # Browser session, step budget + loop detection, step reports
│   │   ├── selector.py              # Selector layer 1: resolve_selector action builds CSS from the DOM
│   │   ├── validate.py              # Selector layer 3: syntax + DOM presence on the live page
│   │   ├── brand_extractor.py       # PlaywrightBrandExtractor
│   │   └── storage_state.py         # TempFileSessionStore (cookie files, 0600, removed after the run)
│   ├── llm/
│   │   ├── factory.py               # Agent LLM, research LLM (gemini/openai/minimax), JSON reply parsing
│   │   ├── research.py              # LLMResearchProvider
│   │   └── selector_review.py       # LLMSelectorReviewer (structural vs dynamic)
│   ├── prompts/                     # Discovery + extraction agent prompts
│   └── persistence/
│       ├── mongodb/                 # Motor client, MongoWorkflowRepository
│       ├── postgresql/              # Stub adapter (NotImplementedError)
│       └── json_archive.py          # JsonFileArchive (outputs/*.json)
│
└── api/                             # ── HTTP ──
    ├── dependencies.py              # Composition root: get_pipeline(), get_workflow_repo()
    └── routers/                     # jobs, query (+ /workflows), crawl (+ /stream/crawl)

tests/
├── conftest.py                      # In-memory fakes for every port + make_pipeline fixture
├── unit/                            # Architecture rules, selector rules, agent runtime, JSON parsing
├── application/                     # Use cases and job manager against fakes
└── api/                             # Routes via TestClient with dependency_overrides
```

### Layer Rules

| Layer | May depend on | Must NOT depend on |
|---|---|---|
| **Domain** | Nothing (pure Python + Pydantic) | Application, Infrastructure, API, FastAPI |
| **Application** | Domain | Infrastructure, API, FastAPI |
| **Infrastructure** | Domain, external libs | Application, API |
| **API** | Application, Domain, FastAPI | Infrastructure (only `api/dependencies.py` may, as the composition root) |

`tests/unit/test_architecture.py` enforces these rules on every test run.

### Ports & Adapters Pattern

**Ports** are abstract interfaces (Python `Protocol` classes) defined in the domain layer. **Adapters** are concrete implementations in the infrastructure layer. Adapters subclass their port explicitly, and `tests/unit/test_adapters_match_ports.py` checks that every adapter wired in `api/dependencies.py` matches its port signature for signature. The application layer depends only on ports; the API layer wires adapters via FastAPI dependency injection.

```python
# domain/workflows/ports.py
from typing import Protocol

class WorkflowRepository(Protocol):
    async def save(self, result: CrawlResponse, screenshots_map: dict[int, list[str]] | None = None) -> None: ...
    async def get_by_domain(self, domain: str) -> dict | None: ...
    async def soft_delete(self, domain: str, workflow_name: str) -> bool: ...


# infrastructure/persistence/mongodb/workflow_repo.py
class MongoWorkflowRepository(WorkflowRepository):
    """Implements WorkflowRepository using Motor (async MongoDB)."""
    ...


# infrastructure/persistence/postgresql/workflow_repo.py
class PostgresWorkflowRepository(WorkflowRepository):
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

### Framework: pytest + pytest-asyncio (`asyncio_mode = "auto"`)

See the `tests/` tree above. Use cases are tested with the fakes in `tests/conftest.py`, so no browser, LLM or database is needed.

### Test Principles
- **Unit tests** cover domain models, validators, selector logic — no network, no browser, no database
- **Integration tests** use FastAPI's `TestClient` with injected in-memory/mock adapters
- Test files mirror the source structure under `tests/`
- Async tests need no decorator (`asyncio_mode = "auto"`)
- Use `conftest.py` fixtures for reusable test setup (fake repos, mock settings)

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

## Current State

The ports & adapters migration is complete; the remaining stub is the PostgreSQL adapter, which nothing uses yet.

### What NOT to Change

- The 3-layer selector validation pipeline is well-designed — preserve it
- The SSE streaming architecture works well — keep the event factory pattern
- The `browser-use` agent integration lives behind the `WorkflowDiscoverer`/`WorkflowExtractor` ports; keep browser-use types out of `application/`
