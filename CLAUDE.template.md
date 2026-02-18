# {{PROJECT_NAME}}

{{Brief description of what this project does.}}

## Tech Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy, structlog
- **Frontend**: React 18, Vite, Tailwind CSS, TanStack Query
- **Database**: SQLite (development), Postgres/Supabase (production)
- **Testing**: pytest, Vitest, Playwright
- **Package Manager**: UV (Python), npm (Node)

## Project Structure

```
{{project-name}}/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI entry point
│   │   ├── config.py         # Pydantic settings
│   │   ├── database.py       # Database connection
│   │   ├── models.py         # SQLAlchemy models
│   │   ├── schemas.py        # Pydantic schemas
│   │   └── routers/          # API endpoints
│   ├── pyproject.toml
│   └── uv.lock
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   ├── features/         # Feature modules
│   │   ├── api/              # API client
│   │   └── App.jsx
│   └── package.json
├── tests/
│   ├── unit/                 # Unit tests
│   ├── integration/          # API integration tests
│   └── e2e/                  # Playwright E2E tests
├── docker-compose.yml
├── Caddyfile
└── .claude/
    ├── PRD.md                # Product requirements
    ├── commands/             # Slash commands
    └── reference/            # Best practices docs
```

## Commands

```bash
# Backend
cd backend
uv sync                                              # Install dependencies
uv run uvicorn app.main:app --reload --port 8000    # Development server

# Frontend
cd frontend
npm install                                          # Install dependencies
npm run dev                                          # Development server (port 5173)

# Testing
cd backend
uv run pytest tests/ -v                             # All tests
uv run pytest tests/unit/ -v                        # Unit tests only
uv run pytest --cov=app                             # With coverage

# E2E Testing
npx playwright test                                  # Run E2E tests

# Linting
uv run ruff check .                                 # Check
uv run ruff check . --fix                           # Auto-fix

# Docker
docker-compose up --build                           # Build and run
docker-compose logs -f                              # View logs
```

## Reference Documentation

Read these documents when working on specific areas:

| Document | When to Read |
|----------|--------------|
| `.claude/PRD.md` | Understanding requirements, features, API spec |
| `.claude/reference/fastapi-best-practices.md` | Building API endpoints, Pydantic schemas |
| `.claude/reference/uv-python-workflow.md` | Python dependencies, UV commands |
| `.claude/reference/sqlite-best-practices.md` | Database schema, queries, SQLAlchemy |
| `.claude/reference/react-frontend-best-practices.md` | Components, hooks, state management |
| `.claude/reference/caddy-patterns.md` | Reverse proxy, HTTPS, docker networking |
| `.claude/reference/deployment-best-practices.md` | Docker, production builds |
| `.claude/reference/testing-and-logging.md` | structlog, pytest patterns |

## Code Conventions

### Backend (Python)

- Use UV for all package management (`uv add`, `uv sync`, `uv run`)
- Use Pydantic models for all request/response schemas
- Separate schemas: `{{Model}}Create`, `{{Model}}Update`, `{{Model}}Response`
- Use `Depends()` for database sessions and validation
- Use structlog for all logging

### Frontend (React)

- Feature-based folder structure under `src/features/`
- Use TanStack Query for all API calls
- Tailwind CSS for styling — no separate CSS files
- Forms with react-hook-form + Zod validation

### API Design

- RESTful endpoints under `/api/`
- Return 201 for POST, 204 for DELETE
- Consistent error response format

### Database

- SQLite with WAL mode for development
- Store dates as ISO-8601 TEXT (`YYYY-MM-DD`)
- Enable foreign keys via PRAGMA

## Logging

Use **structlog** for all logging:

```python
import structlog
logger = structlog.get_logger()

# Log with structured data
logger.info("Action completed", resource_id=1, user="system")
```

## Testing Strategy

- **70% Unit tests**: Pure functions, business logic
- **20% Integration tests**: API endpoints with real database
- **10% E2E tests**: Critical user journeys with Playwright

## Deployment

- **Reverse Proxy**: Caddy (automatic HTTPS)
- **Containerization**: Docker Compose
- **See**: `.claude/reference/caddy-patterns.md` and `.claude/reference/deployment-best-practices.md`

---

{{Delete everything above this line and customize for your project}}
