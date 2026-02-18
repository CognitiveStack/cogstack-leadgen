# UV Python Workflow Reference

A concise reference guide for using UV as your Python package manager and workflow tool.

---

## Table of Contents

1. [Why UV](#1-why-uv)
2. [Installation](#2-installation)
3. [Project Setup](#3-project-setup)
4. [Dependency Management](#4-dependency-management)
5. [Running Code](#5-running-code)
6. [pip Compatibility](#6-pip-compatibility)
7. [Virtual Environments](#7-virtual-environments)
8. [pyproject.toml Patterns](#8-pyprojecttoml-patterns)
9. [Docker Integration](#9-docker-integration)
10. [Migration from pip](#10-migration-from-pip)
11. [Common Workflows](#11-common-workflows)

---

## 1. Why UV

UV is a fast Python package installer and resolver written in Rust. It replaces `pip`, `pip-tools`, `virtualenv`, and `venv`.

| Task | Traditional | UV |
|------|-------------|-----|
| Create venv | `python -m venv .venv` | `uv venv` |
| Install deps | `pip install -r requirements.txt` | `uv sync` |
| Add package | Edit requirements.txt + `pip install` | `uv add package` |
| Run script | `source .venv/bin/activate && python` | `uv run python` |
| Lock deps | `pip-compile` | `uv lock` |

### Speed Comparison

```bash
# pip install flask + dependencies
pip install flask  # ~5-10 seconds

# uv install flask + dependencies
uv add flask       # ~0.5-1 second (10x faster)
```

### Key Benefits

- **10-100x faster** than pip
- **Unified tool** — replaces pip, venv, pip-tools
- **Lockfile support** — reproducible builds via `uv.lock`
- **pyproject.toml native** — modern Python packaging
- **Drop-in pip replacement** — `uv pip` works like pip

---

## 2. Installation

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Homebrew

```bash
brew install uv
```

### pipx (if you must)

```bash
pipx install uv
```

### Verify Installation

```bash
uv --version
# uv 0.5.x
```

### Shell Completion

```bash
# Bash
echo 'eval "$(uv generate-shell-completion bash)"' >> ~/.bashrc

# Zsh
echo 'eval "$(uv generate-shell-completion zsh)"' >> ~/.zshrc
```

---

## 3. Project Setup

### New Project

```bash
# Create project with pyproject.toml
uv init myproject
cd myproject

# Or init in current directory
uv init
```

**Generated structure:**

```
myproject/
├── pyproject.toml
├── README.md
├── .python-version
└── src/
    └── myproject/
        └── __init__.py
```

### Existing Project (No pyproject.toml)

```bash
cd existing-project

# Initialize UV with pyproject.toml
uv init

# Or create minimal pyproject.toml manually
```

### Set Python Version

```bash
# Use specific Python version
uv python pin 3.12

# Or create .python-version file
echo "3.12" > .python-version
```

### Install Python (if needed)

```bash
# List available versions
uv python list

# Install specific version
uv python install 3.12
```

---

## 4. Dependency Management

### Add Dependencies

```bash
# Add to [project.dependencies]
uv add fastapi
uv add sqlalchemy pydantic

# Add dev dependencies to [dependency-groups.dev]
uv add --dev pytest pytest-cov ruff

# Add with version constraint
uv add "fastapi>=0.100"
uv add "pydantic>=2.0,<3.0"
```

### Remove Dependencies

```bash
uv remove flask
uv remove --dev pytest-xdist
```

### Sync (Install from Lock)

```bash
# Install all dependencies from uv.lock
uv sync

# Include dev dependencies (default)
uv sync

# Production only (no dev deps)
uv sync --no-dev
```

### Update Dependencies

```bash
# Update all packages
uv lock --upgrade

# Update specific package
uv lock --upgrade-package fastapi

# Then sync to install
uv sync
```

### Lock File

UV automatically creates `uv.lock` — commit this to git for reproducible builds:

```bash
# Regenerate lock from pyproject.toml
uv lock

# Check lock is up to date
uv lock --check
```

---

## 5. Running Code

### Run Python Scripts

```bash
# Run script (auto-creates venv, installs deps)
uv run python script.py

# Run module
uv run python -m pytest

# Run with arguments
uv run python main.py --port 8000
```

### Run Uvicorn (FastAPI)

```bash
# Development with reload
uv run uvicorn app.main:app --reload --port 8000

# Production
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Run CLI Tools

```bash
# Tools installed as dependencies
uv run pytest
uv run ruff check .
uv run alembic upgrade head

# One-off tool execution (not installed)
uv tool run ruff check .
uvx ruff check .  # shorthand
```

### Interactive Shell

```bash
# Python REPL with project deps
uv run python

# IPython
uv add --dev ipython
uv run ipython
```

---

## 6. pip Compatibility

UV provides a pip-compatible interface for legacy workflows:

### pip Commands → UV Equivalents

```bash
# Traditional pip
pip install flask
pip install -r requirements.txt
pip freeze > requirements.txt
pip uninstall flask

# UV pip (drop-in replacement)
uv pip install flask
uv pip install -r requirements.txt
uv pip freeze > requirements.txt
uv pip uninstall flask
```

### When to Use `uv pip`

- Legacy projects with `requirements.txt`
- CI systems expecting pip interface
- Quick one-off installs without pyproject.toml

### Preferred: Native UV Commands

```bash
# Instead of: pip install flask
uv add flask

# Instead of: pip install -r requirements.txt
uv sync

# Instead of: pip freeze
uv pip freeze  # or just commit uv.lock
```

---

## 7. Virtual Environments

### UV Handles Venvs Automatically

```bash
# uv run automatically:
# 1. Creates .venv if missing
# 2. Installs dependencies
# 3. Runs command in venv

uv run python script.py  # Just works™
```

### Manual Venv Management (Rarely Needed)

```bash
# Create venv explicitly
uv venv

# Create with specific Python
uv venv --python 3.12

# Create in custom location
uv venv /path/to/venv
```

### Activate Venv (Traditional Workflow)

If you prefer activating (IDE compatibility, etc.):

```bash
# Create venv
uv venv

# Activate (Linux/macOS)
source .venv/bin/activate

# Activate (Windows)
.venv\Scripts\activate

# Now use uv pip or regular pip
uv pip install flask
```

### IDE Configuration

Most IDEs auto-detect `.venv`. For VS Code:

```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python"
}
```

---

## 8. pyproject.toml Patterns

### Minimal FastAPI Project

```toml
[project]
name = "myapi"
version = "0.1.0"
description = "My FastAPI application"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sqlalchemy>=2.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "structlog>=24.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-cov>=4.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "ruff>=0.8",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

### With Optional Dependencies

```toml
[project]
name = "myapi"
version = "0.1.0"
dependencies = [
    "fastapi",
    "uvicorn",
]

[project.optional-dependencies]
postgres = ["psycopg2-binary", "asyncpg"]
redis = ["redis", "hiredis"]
all = ["myapi[postgres,redis]"]

[dependency-groups]
dev = ["pytest", "ruff"]
```

Install optionals:

```bash
uv sync --extra postgres
uv sync --all-extras
```

### Entry Points (CLI Scripts)

```toml
[project.scripts]
myapi = "myapi.cli:main"
```

```bash
# After uv sync, run as:
uv run myapi
```

---

## 9. Docker Integration

### Dockerfile with UV

```dockerfile
# Build stage
FROM python:3.12-slim AS builder

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application
COPY . .

# Install project itself
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application
COPY --from=builder /app .

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Docker Compose

```yaml
services:
  backend:
    build: ./backend
    expose:
      - "8000"
    environment:
      - DATABASE_URL=sqlite:///./data/app.db
    volumes:
      - ./data:/app/data
```

### Development with Hot Reload

```yaml
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile.dev
    volumes:
      - ./backend:/app
      - /app/.venv  # Exclude venv from mount
    command: uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Dockerfile.dev:**

```dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install deps first for caching
COPY pyproject.toml uv.lock ./
RUN uv sync

COPY . .

CMD ["uv", "run", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0"]
```

---

## 10. Migration from pip

### From requirements.txt

```bash
# Option 1: Import into pyproject.toml
uv add $(cat requirements.txt | grep -v '^#' | tr '\n' ' ')

# Option 2: Keep using requirements.txt with uv pip
uv pip install -r requirements.txt
```

### From pip + venv Workflow

| Old Command | New Command |
|-------------|-------------|
| `python -m venv .venv` | `uv venv` (or let `uv run` handle it) |
| `source .venv/bin/activate` | Not needed with `uv run` |
| `pip install package` | `uv add package` |
| `pip install -r requirements.txt` | `uv sync` |
| `pip freeze > requirements.txt` | Commit `uv.lock` instead |
| `python script.py` | `uv run python script.py` |
| `deactivate` | Not needed |

### Gradual Migration

1. **Week 1**: Use `uv pip` as drop-in replacement
2. **Week 2**: Switch to `uv run` for executing scripts
3. **Week 3**: Create pyproject.toml, use `uv add/sync`
4. **Week 4**: Remove requirements.txt, use uv.lock

---

## 11. Common Workflows

### New FastAPI Project

```bash
# Create project
mkdir myapi && cd myapi
uv init

# Add dependencies
uv add fastapi "uvicorn[standard]" sqlalchemy pydantic-settings structlog
uv add --dev pytest pytest-cov httpx ruff

# Create structure
mkdir -p app/routers tests

# Run development server
uv run uvicorn app.main:app --reload
```

### Daily Development

```bash
# Start of day: sync deps (if uv.lock changed)
uv sync

# Run dev server
uv run uvicorn app.main:app --reload --port 8000

# Run tests
uv run pytest

# Lint
uv run ruff check .
uv run ruff format .

# Add new package
uv add httpx
```

### CI/CD Pipeline

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Install uv
        uses: astral-sh/setup-uv@v4
        
      - name: Install dependencies
        run: uv sync
        
      - name: Run tests
        run: uv run pytest --cov
        
      - name: Lint
        run: uv run ruff check .
```

### Database Migrations

```bash
# Add alembic
uv add alembic

# Initialize
uv run alembic init migrations

# Create migration
uv run alembic revision --autogenerate -m "Add users table"

# Apply migrations
uv run alembic upgrade head
```

### One-Off Tools (Without Installing)

```bash
# Run ruff without adding to project
uvx ruff check .

# Run black formatter
uvx black .

# Run specific version
uvx ruff@0.1.0 check .
```

---

## Quick Reference

### Essential Commands

```bash
# Project setup
uv init                    # Create new project
uv venv                    # Create virtual environment
uv python pin 3.12         # Set Python version

# Dependencies
uv add package             # Add dependency
uv add --dev package       # Add dev dependency
uv remove package          # Remove dependency
uv sync                    # Install from lock
uv lock                    # Update lock file

# Running
uv run python script.py    # Run script
uv run uvicorn app:app     # Run server
uv run pytest              # Run tests

# pip compatibility
uv pip install package     # pip-like install
uv pip freeze              # List installed

# Tools
uvx tool                   # Run tool without installing
uv tool install tool       # Install global tool
```

### File Structure

```
project/
├── pyproject.toml    # Project config + dependencies
├── uv.lock           # Locked dependencies (commit this!)
├── .python-version   # Python version
├── .venv/            # Virtual environment (gitignore)
├── src/
│   └── project/
└── tests/
```

### .gitignore Additions

```gitignore
# UV
.venv/
*.egg-info/
__pycache__/
.pytest_cache/
.ruff_cache/
```

---

## Resources

- [UV Documentation](https://docs.astral.sh/uv/)
- [UV GitHub](https://github.com/astral-sh/uv)
- [Astral (creators of UV and Ruff)](https://astral.sh/)
- [pyproject.toml Specification](https://packaging.python.org/en/latest/specifications/pyproject-toml/)
