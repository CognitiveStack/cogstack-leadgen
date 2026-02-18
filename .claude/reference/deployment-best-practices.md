# Deployment Best Practices Reference

A concise reference guide for deploying Python/FastAPI + React applications.

---

## Table of Contents

1. [Local Development](#1-local-development)
2. [Production Builds](#2-production-builds)
3. [Backend Deployment](#3-backend-deployment)
4. [Frontend Deployment](#4-frontend-deployment)
5. [Docker](#5-docker)
6. [Reverse Proxy (Caddy)](#6-reverse-proxy-caddy)
7. [Reverse Proxy (Nginx Alternative)](#7-reverse-proxy-nginx-alternative)
8. [Environment & Configuration](#8-environment--configuration)
9. [Database in Production](#9-database-in-production)
10. [Monitoring & Logging](#10-monitoring--logging)
11. [Cloud Platforms](#11-cloud-platforms)
12. [Security](#12-security)
13. [Single Binary Deployment](#13-single-binary-deployment)

---

## 1. Local Development

### Running Frontend and Backend

**Two Terminal Approach:**

```bash
# Terminal 1: Backend
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm install
npm run dev  # Runs on port 5173
```

### Vite Proxy Configuration

Avoid CORS issues by proxying API requests through Vite:

```javascript
// frontend/vite.config.js
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
```

Now frontend code can use relative paths:
```javascript
fetch('/api/habits')  // Proxied to http://localhost:8000/api/habits
```

### Hot Reloading

- **Backend**: `uvicorn --reload` watches for file changes
- **Frontend**: Vite HMR (Hot Module Replacement) built-in

### Environment Variables

```bash
# backend/.env
DATABASE_URL=sqlite:///./habits.db
DEBUG=true
CORS_ORIGINS=["http://localhost:5173"]

# frontend/.env
VITE_API_URL=/api
```

---

## 2. Production Builds

### Frontend Build (Vite)

```bash
cd frontend
npm run build  # Creates dist/ folder
```

**Output:**
```
dist/
├── index.html
├── assets/
│   ├── index-abc123.js
│   └── index-def456.css
```

### Build Optimization

```javascript
// vite.config.js
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },
});
```

### Bundle Analysis

```bash
npm install rollup-plugin-visualizer --save-dev
```

```javascript
// vite.config.js
import { visualizer } from 'rollup-plugin-visualizer';

export default defineConfig({
  plugins: [
    react(),
    visualizer({ open: true }),
  ],
});
```

---

## 3. Backend Deployment

### Uvicorn (Recommended)

```bash
# Development
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production (with multiple workers)
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

**Worker count**: Number of CPU cores for async workers.

> **Note**: Gunicorn + Uvicorn workers is a legacy pattern. Modern Uvicorn handles process management well on its own. Use plain Uvicorn unless you have specific requirements for Gunicorn's features.

### Systemd Service

```ini
# /etc/systemd/system/myapp.service
[Unit]
Description=My FastAPI App
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/myapp/backend
ExecStart=/home/www-data/.local/bin/uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5
Environment="PATH=/home/www-data/.local/bin:/usr/bin"

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable myapp
sudo systemctl start myapp
sudo systemctl status myapp
```

---

## 4. Frontend Deployment

### Option 1: FastAPI Serves Static Files

```python
# app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse
import os

app = FastAPI()

# API routes first
@app.get("/api/habits")
async def list_habits():
    pass

# Serve React app
frontend_path = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")

@app.get("/")
async def serve_react_app():
    return FileResponse(os.path.join(frontend_path, "index.html"))

# Handle client-side routing
@app.exception_handler(404)
async def custom_404_handler(request, exc):
    if not request.url.path.startswith("/api"):
        return FileResponse(os.path.join(frontend_path, "index.html"))
    raise exc

# Mount static files AFTER routes
app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
```

**Benefits**: Single deployment, no CORS issues, simpler infrastructure.

### Option 2: Caddy Serves Static Files (Recommended)

Better performance for static assets, automatic HTTPS:

```caddyfile
app.example.com {
    encode zstd gzip
    
    # API routes to FastAPI
    handle /api/* {
        reverse_proxy backend:8000
    }
    
    # Static files for frontend
    handle {
        root * /var/www/app/dist
        try_files {path} /index.html
        file_server
    }
}
```

### Option 3: CDN/Static Hosting

Deploy frontend to Vercel, Netlify, or Cloudflare Pages:

```bash
# Vercel
npm install -g vercel
vercel --prod

# Netlify
npm install -g netlify-cli
netlify deploy --prod
```

Configure API URL for separate backend:
```javascript
// frontend/.env.production
VITE_API_URL=https://api.yourdomain.com
```

---

## 5. Docker

### Dockerfile (Multi-Stage Build with UV)

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim AS builder

# Install UV
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies (no dev deps, no project yet)
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev

# Runtime stage
FROM python:3.12-slim

WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy venv from builder
COPY --from=builder /app/.venv /app/.venv

# Copy application
COPY --from=builder /app .

# Set ownership
RUN chown -R appuser:appuser /app

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend Dockerfile (with Caddy)

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM caddy:2-alpine
COPY --from=builder /app/dist /var/www/app
COPY Caddyfile /etc/caddy/Caddyfile
EXPOSE 80 443
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile"]
```

### Docker Compose (Full Stack with Caddy)

```yaml
# docker-compose.yml
version: '3.8'

services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./frontend/dist:/var/www/app:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - backend
    networks:
      - app-network

  backend:
    build: ./backend
    container_name: backend
    restart: unless-stopped
    expose:
      - "8000"
    environment:
      - DATABASE_URL=sqlite:///./data/app.db
    volumes:
      - ./data:/app/data
    networks:
      - app-network

volumes:
  caddy_data:
  caddy_config:

networks:
  app-network:
```

**Caddyfile:**

```caddyfile
{
    email your@email.com
}

app.example.com {
    encode zstd gzip
    
    # API to FastAPI backend
    handle /api/* {
        reverse_proxy backend:8000
    }
    
    # Frontend static files
    handle {
        root * /var/www/app
        try_files {path} /index.html
        file_server
    }
}
```

### Docker Commands

```bash
# Build and run
docker-compose up --build

# Run in background
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Rebuild single service
docker-compose up --build backend
```

### Image Optimization Tips

| Tip | Impact |
|-----|--------|
| Use slim base images | `python:3.12-slim` is 45MB vs 125MB |
| Multi-stage builds | 70%+ smaller images |
| Use `.dockerignore` | Faster builds |
| Order layers by change frequency | Better caching |
| Use UV for faster installs | 10x faster than pip |

**.dockerignore:**
```
__pycache__
*.pyc
.git
.env
.venv
node_modules
dist
*.md
.ruff_cache
.pytest_cache
```

---

## 6. Reverse Proxy (Caddy)

> **Recommended**: Caddy is the preferred reverse proxy for its simplicity, automatic HTTPS, and Docker-native design.

### Why Caddy?

| Feature | Caddy | Nginx |
|---------|-------|-------|
| Auto HTTPS | ✅ Built-in Let's Encrypt | ❌ Requires Certbot |
| Config syntax | Simple, 2-3 lines | Complex, 10+ lines |
| Hot reload | ✅ Automatic | Manual `nginx -s reload` |
| WebSocket | ✅ Automatic | Manual configuration |
| Docker service names | ✅ Just work | Requires resolver |

### Basic Configuration

```caddyfile
{
    email your@email.com
}

app.example.com {
    encode zstd gzip
    reverse_proxy backend:8000
}
```

### Full Stack (API + Frontend)

```caddyfile
app.example.com {
    encode zstd gzip
    
    # API routes
    handle /api/* {
        reverse_proxy backend:8000
    }
    
    # Frontend SPA
    handle {
        root * /var/www/app
        try_files {path} /index.html
        file_server
    }
}
```

### With Basic Auth (Swagger Protection)

```caddyfile
api.example.com {
    encode zstd gzip
    
    # Protect Swagger UI only
    @swagger path /docs* /redoc* /openapi.json
    route @swagger {
        basic_auth {
            admin $2a$14$hashedpassword
        }
        reverse_proxy backend:8000
    }
    
    # No auth for API endpoints
    reverse_proxy backend:8000
}
```

Generate password hash:
```bash
docker run --rm caddy:2-alpine caddy hash-password
```

### With Environment Variables

```caddyfile
{$APP_HOSTNAME} {
    reverse_proxy backend:8000
}
```

```yaml
# docker-compose.yml
services:
  caddy:
    environment:
      - APP_HOSTNAME=app.example.com
```

### Multiple Services

```caddyfile
{
    email your@email.com
}

app.example.com {
    reverse_proxy frontend:3000
}

api.example.com {
    reverse_proxy backend:8000
}

n8n.example.com {
    reverse_proxy n8n:5678
}
```

### CORS Handling

```caddyfile
api.example.com {
    # Handle preflight
    @preflight method OPTIONS
    handle @preflight {
        header Access-Control-Allow-Origin "*"
        header Access-Control-Allow-Methods "GET, POST, PUT, DELETE, OPTIONS"
        header Access-Control-Allow-Headers "Content-Type, Authorization"
        respond "" 204
    }
    
    header Access-Control-Allow-Origin "*"
    reverse_proxy backend:8000
}
```

### Shared Network Pattern

For Caddy to reach containers in other docker-compose stacks:

```bash
# Create shared network once
docker network create caddy-shared
```

```yaml
# In each docker-compose.yml
services:
  myservice:
    networks:
      - default
      - caddy-shared

networks:
  caddy-shared:
    external: true
```

### Caddy Commands

```bash
# Validate config
docker exec caddy caddy validate --config /etc/caddy/Caddyfile

# Reload without restart
docker exec caddy caddy reload --config /etc/caddy/Caddyfile

# View certificates
docker exec caddy caddy list-certs

# Format Caddyfile
docker exec caddy caddy fmt --overwrite /etc/caddy/Caddyfile
```

> **See also**: `.claude/reference/caddy-patterns.md` for comprehensive Caddy patterns including WebSocket, Kubernetes integration, and Cloudflare setup.

---

## 7. Reverse Proxy (Nginx Alternative)

> **Note**: Use Nginx if you have existing Nginx infrastructure or specific requirements. For new projects, prefer Caddy.

### Basic Configuration

```nginx
# /etc/nginx/sites-available/myapp
server {
    listen 80;
    server_name app.example.com;

    # Serve React static files
    root /var/www/myapp/frontend/dist;
    index index.html;

    # Handle React Router (client-side routing)
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Proxy API requests to FastAPI
    location /api {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### Enable Site

```bash
sudo ln -s /etc/nginx/sites-available/myapp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### SSL with Let's Encrypt

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d app.example.com
```

### Nginx in Docker

```dockerfile
FROM nginx:alpine
COPY dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

---

## 8. Environment & Configuration

### 12-Factor App Principles

| Factor | Application |
|--------|-------------|
| Config | Environment variables |
| Dependencies | pyproject.toml / package.json |
| Processes | Stateless app |
| Port binding | App binds to port |
| Logs | Stream to stdout |
| Dev/prod parity | Use Docker |

### Pydantic Settings

```python
# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "My App"
    database_url: str = "sqlite:///./app.db"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:5173"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

### Environment Files

```bash
# .env.development
DATABASE_URL=sqlite:///./app.db
DEBUG=true
CORS_ORIGINS=["http://localhost:5173"]

# .env.production
DATABASE_URL=sqlite:///./data/app.db
DEBUG=false
CORS_ORIGINS=["https://app.example.com"]
```

### Secrets Management (Production)

| Environment | Solution |
|-------------|----------|
| Local | `.env` files (gitignored) |
| Docker | Environment variables / secrets |
| Cloud | Platform secrets (Railway, Fly.io) |
| Enterprise | HashiCorp Vault, AWS Secrets Manager |

---

## 9. Database in Production

### SQLite Considerations

**When SQLite works**:
- Single server deployment
- Low write concurrency
- Database < 1TB
- Local/personal applications

**When to migrate to PostgreSQL**:
- Multiple servers/load balancing
- High write concurrency
- Need for replication/HA

### Database File Location

```python
# Don't store in application directory
# BAD
DATABASE_URL = "sqlite:///./app.db"

# GOOD - absolute path outside app
DATABASE_URL = "sqlite:////var/data/myapp/app.db"
```

### Docker Volume for Persistence

```yaml
services:
  backend:
    volumes:
      - db-data:/app/data

volumes:
  db-data:
```

### Backup with Litestream

```yaml
# litestream.yml
dbs:
  - path: /data/app.db
    replicas:
      - url: s3://bucket-name/backups
        sync-interval: 1s
        retention: 24h
```

### Manual Backup

```bash
# Safe backup using SQLite CLI
sqlite3 /data/app.db "VACUUM INTO '/backups/app-$(date +%Y%m%d).db'"
```

### Migrations with Alembic

```bash
# Add alembic
uv add alembic

# Initialize
uv run alembic init migrations

# Generate migration
uv run alembic revision --autogenerate -m "Add users table"

# Apply migrations
uv run alembic upgrade head
```

---

## 10. Monitoring & Logging

### Structured Logging with structlog

```python
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()
logger.info("Request processed", path="/api/habits", duration=0.045)
```

### Request Logging Middleware

```python
import time
import structlog

logger = structlog.get_logger()

@app.middleware("http")
async def log_requests(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time

    logger.info(
        "Request completed",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration=f"{duration:.3f}s",
    )
    return response
```

### Health Check Endpoints

```python
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/health/ready")
async def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "not ready", "error": str(e)},
        )
```

---

## 11. Cloud Platforms

### Platform Comparison

| Platform | Pricing | Best For | SQLite Support |
|----------|---------|----------|----------------|
| **Hostinger VPS** | $5+/mo | Docker/Caddy stacks | Yes |
| **Fly.io** | $2+/mo | Global, SQLite | Yes (volumes) |
| **Railway** | Usage-based | Fast deploys | Limited |
| **DigitalOcean** | $4+/mo | VPS control | Yes |
| **Hetzner** | $4+/mo | Europe, budget | Yes |

### VPS Deployment (Hostinger/DigitalOcean)

```bash
# 1. SSH into server
ssh user@your-server

# 2. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 3. Clone repository
git clone https://github.com/you/myapp /opt/myapp

# 4. Configure environment
cd /opt/myapp
cp .env.example .env
nano .env

# 5. Create shared network
docker network create caddy-shared

# 6. Start services
docker-compose up -d

# 7. Check logs
docker-compose logs -f
```

### Fly.io Deployment

```bash
fly launch
fly volumes create data --size 1
fly deploy
```

**fly.toml:**
```toml
app = "myapp"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8000
  force_https = true

[mounts]
  source = "data"
  destination = "/data"
```

---

## 12. Security

### CORS Configuration (FastAPI)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,  # Specific origins only
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### Security Headers (Caddy)

```caddyfile
app.example.com {
    header {
        X-Frame-Options "SAMEORIGIN"
        X-Content-Type-Options "nosniff"
        X-XSS-Protection "1; mode=block"
        Referrer-Policy "strict-origin-when-cross-origin"
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
    }
    reverse_proxy backend:8000
}
```

### Docker Security

```dockerfile
# Run as non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

# Use specific versions
FROM python:3.12.3-slim

# Don't store secrets in image
# Use runtime environment variables
```

### Environment Security

```bash
# Never commit .env files
echo ".env" >> .gitignore
echo ".env.*" >> .gitignore

# Set restrictive permissions
chmod 600 .env
```

---

## 13. Single Binary Deployment

### PyInstaller

```bash
uv add pyinstaller

# Create spec file
uv run pyi-makespec --onefile --name myapp backend/app/main.py
```

**entrypoint.py:**
```python
import multiprocessing
import uvicorn

if __name__ == "__main__":
    multiprocessing.freeze_support()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
```

**Build:**
```bash
uv run pyinstaller --onefile --add-data "frontend/dist:frontend/dist" entrypoint.py
```

---

## Deployment Scenarios

### Scenario 1: Local/Personal Use

```
┌─────────────────────────────────┐
│  uvicorn + embedded React       │
│  SQLite file in ./data          │
└─────────────────────────────────┘
```

```bash
cd backend && uv run uvicorn app.main:app --port 8000
```

### Scenario 2: VPS with Docker Compose + Caddy (Recommended)

```
┌──────────────────────────────────────────┐
│  docker-compose                          │
│  ┌────────────┐    ┌────────────┐        │
│  │   Caddy    │────│  FastAPI   │        │
│  │  (HTTPS)   │    │  (uvicorn) │        │
│  └────────────┘    └─────┬──────┘        │
│                          │               │
│                    ┌─────▼──────┐        │
│                    │   volume   │        │
│                    │  (sqlite)  │        │
│                    └────────────┘        │
└──────────────────────────────────────────┘
```

**Cost**: ~$5/month (Hostinger VPS)

### Scenario 3: Cloud PaaS (Fly.io)

```
┌──────────────────────────────────────────┐
│  Fly.io                                  │
│  ┌────────────────────────┐              │
│  │  Docker container      │              │
│  │  FastAPI + React       │              │
│  └───────────┬────────────┘              │
│              │                           │
│        ┌─────▼─────┐                     │
│        │  Volume   │                     │
│        │  (SQLite) │                     │
│        └───────────┘                     │
└──────────────────────────────────────────┘
```

**Cost**: ~$2-5/month

---

## Quick Reference

### Essential Commands

```bash
# Development
uv run uvicorn app.main:app --reload
npm run dev

# Production build
npm run build
uv sync --no-dev

# Docker
docker-compose up --build
docker-compose logs -f

# Caddy
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
docker exec caddy caddy validate --config /etc/caddy/Caddyfile

# Database backup
sqlite3 db.db "VACUUM INTO 'backup.db'"
```

### Port Reference

| Service | Default Port |
|---------|--------------|
| Vite dev server | 5173 |
| FastAPI/Uvicorn | 8000 |
| Caddy HTTP | 80 |
| Caddy HTTPS | 443 |
| PostgreSQL | 5432 |

---

## Resources

- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [Caddy Documentation](https://caddyserver.com/docs/)
- [UV Documentation](https://docs.astral.sh/uv/)
- [Docker Documentation](https://docs.docker.com/)
- [Vite Static Deploy](https://vitejs.dev/guide/static-deploy.html)
- [Litestream](https://litestream.io/)
