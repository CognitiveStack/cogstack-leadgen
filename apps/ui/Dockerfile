# Stage 1: install dependencies + build the package wheel
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# --frozen: exact versions from uv.lock
# --no-dev: skip test/lint extras
# --no-editable: install package into .venv (templates included via hatchling)
RUN uv sync --frozen --no-dev --no-editable


# Stage 2: lean runtime image — only the installed venv, no uv, no build tools
FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH"

RUN useradd --system --uid 10001 --user-group --shell /usr/sbin/nologin \
    --no-create-home appuser
RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# --proxy-headers: trust X-Forwarded-* from Caddy
CMD ["uvicorn", "cogstack_ui.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--proxy-headers"]
