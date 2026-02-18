# Caddy Reverse Proxy Patterns Reference

A concise reference guide for Caddy as a reverse proxy in docker-compose environments.

---

## Table of Contents

1. [Why Caddy Over Nginx](#1-why-caddy-over-nginx)
2. [Basic Setup](#2-basic-setup)
3. [Common Patterns](#3-common-patterns)
4. [Docker Compose Integration](#4-docker-compose-integration)
5. [HTTPS & Certificates](#5-https--certificates)
6. [Authentication](#6-authentication)
7. [WebSocket Support](#7-websocket-support)
8. [CORS Handling](#8-cors-handling)
9. [Static File Serving](#9-static-file-serving)
10. [Kubernetes Integration](#10-kubernetes-integration)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Why Caddy Over Nginx

| Feature | Caddy | Nginx |
|---------|-------|-------|
| Auto HTTPS | ✅ Built-in Let's Encrypt | ❌ Requires Certbot setup |
| Config syntax | Simple, readable | Complex, verbose |
| Hot reload | ✅ Automatic | Requires `nginx -s reload` |
| Default security | ✅ Secure defaults | Manual hardening needed |
| WebSocket | ✅ Automatic | Manual configuration |
| Docker-native | ✅ Service names work | Requires resolver config |

**Equivalent configs:**

```nginx
# Nginx (12 lines)
server {
    listen 80;
    server_name app.example.com;
    location / {
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```caddyfile
# Caddy (2 lines)
app.example.com {
    reverse_proxy backend:8000
}
```

---

## 2. Basic Setup

### Minimal Caddyfile

```caddyfile
{
    email your@email.com
}

app.example.com {
    reverse_proxy backend:8000
}
```

### Global Options Block

```caddyfile
{
    email your@email.com           # For Let's Encrypt notifications
    # acme_ca https://acme-staging-v02.api.letsencrypt.org/directory  # Staging (testing)
    # debug                        # Verbose logging
}
```

### Caddy in Docker Compose

```yaml
# docker-compose.yml
services:
  caddy:
    image: caddy:2-alpine
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"  # HTTP/3 (QUIC)
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data        # Certificates
      - caddy_config:/config    # Runtime config
    networks:
      - caddy-shared
    environment:
      - N8N_HOSTNAME=n8n.example.com
      - WEBUI_HOSTNAME=webui.example.com

volumes:
  caddy_data:
  caddy_config:

networks:
  caddy-shared:
    external: true
```

### Shared Network Pattern

For Caddy to proxy to containers in **other** docker-compose stacks:

```bash
# Create shared network once
docker network create caddy-shared
```

```yaml
# In each docker-compose.yml that Caddy needs to reach
services:
  myapp:
    # ...
    networks:
      - default
      - caddy-shared

networks:
  caddy-shared:
    external: true
```

---

## 3. Common Patterns

### Simple Reverse Proxy

```caddyfile
app.example.com {
    reverse_proxy backend:8000
}
```

### With Environment Variables

```caddyfile
{$N8N_HOSTNAME} {
    reverse_proxy n8n:5678
}
```

Set in docker-compose or `.env`:
```bash
N8N_HOSTNAME=n8n.example.com
```

### With Compression

```caddyfile
app.example.com {
    encode zstd gzip
    reverse_proxy backend:8000
}
```

### Multiple Backends (Load Balancing)

```caddyfile
app.example.com {
    reverse_proxy backend1:8000 backend2:8000 {
        lb_policy round_robin
        health_uri /health
        health_interval 30s
    }
}
```

### Path-Based Routing

```caddyfile
example.com {
    handle /api/* {
        reverse_proxy api:8000
    }
    handle {
        reverse_proxy frontend:3000
    }
}
```

### Redirect HTTP to HTTPS

Caddy does this automatically! But if you need explicit control:

```caddyfile
http://example.com {
    redir https://{host}{uri} permanent
}
```

---

## 4. Docker Compose Integration

### FastAPI + React + Caddy Stack

```yaml
version: '3.8'

services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
    networks:
      - app-network
    depends_on:
      - backend
      - frontend

  backend:
    build: ./backend
    expose:
      - "8000"
    environment:
      - DATABASE_URL=sqlite:///./data/app.db
    volumes:
      - ./data:/app/data
    networks:
      - app-network

  frontend:
    build: ./frontend
    expose:
      - "3000"
    networks:
      - app-network

volumes:
  caddy_data:

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
    
    # API routes
    handle /api/* {
        reverse_proxy backend:8000
    }
    
    # Frontend (React/Vite)
    handle {
        reverse_proxy frontend:3000
    }
}
```

### Service Discovery

Caddy resolves Docker service names automatically when on the same network:

```caddyfile
# These just work™ - no IP addresses needed
n8n.example.com {
    reverse_proxy n8n:5678
}

flowise.example.com {
    reverse_proxy flowise:3000
}
```

---

## 5. HTTPS & Certificates

### Automatic HTTPS (Default)

Caddy automatically:
1. Obtains Let's Encrypt certificates
2. Renews certificates before expiry
3. Redirects HTTP → HTTPS
4. Enables OCSP stapling

**Requirements:**
- Port 80 and 443 accessible from internet
- Valid DNS pointing to your server
- Email configured in global options

### With Cloudflare Proxy (Orange Cloud)

When Cloudflare terminates SSL (orange cloud enabled):

```caddyfile
{
    email your@email.com
    # Cloudflare handles external SSL; Caddy handles internal
}

# Option 1: Trust Cloudflare's edge (simple)
app.example.com {
    reverse_proxy backend:8000
}
```

**Cloudflare SSL/TLS settings:**
- SSL mode: **Full (strict)** — Cloudflare → Caddy (both encrypted)
- Or **Full** — if using self-signed on Caddy side

### Manual/Internal Certificates

For internal services or custom certs:

```caddyfile
app.internal.local {
    tls internal  # Self-signed cert
    reverse_proxy backend:8000
}

# Or with custom certs
app.example.com {
    tls /path/to/cert.pem /path/to/key.pem
    reverse_proxy backend:8000
}
```

### Staging Certificates (Testing)

Avoid Let's Encrypt rate limits during testing:

```caddyfile
{
    acme_ca https://acme-staging-v02.api.letsencrypt.org/directory
}
```

---

## 6. Authentication

### Basic Auth

```caddyfile
app.example.com {
    basic_auth {
        # Generate hash: caddy hash-password
        username $2a$14$hashedpasswordhere
    }
    reverse_proxy backend:8000
}
```

**Generate password hash:**

```bash
docker run --rm caddy:2-alpine caddy hash-password
# Enter password when prompted
```

### Basic Auth for Specific Paths Only

```caddyfile
app.example.com {
    # Protect only /admin and /swagger
    @protected {
        path /admin* /swagger*
    }
    
    route @protected {
        basic_auth {
            admin $2a$14$hashedpassword
        }
        reverse_proxy backend:8000
    }
    
    # No auth for other paths
    reverse_proxy backend:8000
}
```

### Using Environment Variables for Auth

```caddyfile
app.example.com {
    basic_auth /* {
        {$AUTH_USER} {$AUTH_HASH}
    }
    reverse_proxy backend:8000
}
```

---

## 7. WebSocket Support

Caddy handles WebSocket automatically, but for explicit configuration:

```caddyfile
voice.example.com {
    # WebSocket matcher
    @websockets {
        header Connection *Upgrade*
        header Upgrade websocket
    }
    
    # WebSocket connections
    reverse_proxy @websockets backend:3000
    
    # HTTP connections
    reverse_proxy backend:3000
}
```

### Real-Time Apps (n8n, Flowise, etc.)

WebSocket-heavy apps work without special config:

```caddyfile
n8n.example.com {
    reverse_proxy n8n:5678
}

flowise.example.com {
    reverse_proxy flowise:3000
}
```

---

## 8. CORS Handling

### Full CORS Support (API Backend)

```caddyfile
api.example.com {
    encode zstd gzip
    
    # Handle preflight OPTIONS requests
    @preflight method OPTIONS
    handle @preflight {
        header Access-Control-Allow-Origin "*"
        header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        header Access-Control-Allow-Headers "Content-Type, Authorization"
        header Access-Control-Max-Age "86400"
        respond "" 204
    }
    
    # Add CORS headers to all responses
    header Access-Control-Allow-Origin "*"
    reverse_proxy backend:8000
}
```

### Specific Origins (More Secure)

```caddyfile
api.example.com {
    header Access-Control-Allow-Origin "https://app.example.com"
    header Access-Control-Allow-Credentials "true"
    reverse_proxy backend:8000
}
```

### CORS + Basic Auth on Swagger Only

```caddyfile
api.example.com {
    encode zstd gzip
    
    # Basic auth ONLY for Swagger UI
    @swagger path /swagger* /docs* /redoc*
    route @swagger {
        basic_auth {
            admin $2a$14$hashedpassword
        }
        reverse_proxy backend:8000
    }
    
    # CORS for API endpoints (no auth)
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

---

## 9. Static File Serving

### Simple Static Site

```caddyfile
site.example.com {
    encode zstd gzip
    root * /var/www/site
    file_server
}
```

### SPA (Single Page Application)

For React/Vue/Angular with client-side routing:

```caddyfile
app.example.com {
    encode zstd gzip
    root * /var/www/app
    
    # Try files, fall back to index.html for SPA routing
    try_files {path} /index.html
    file_server
}
```

### Static + API Backend

```caddyfile
app.example.com {
    encode zstd gzip
    
    # API routes to backend
    handle /api/* {
        reverse_proxy backend:8000
    }
    
    # Static files for everything else
    handle {
        root * /var/www/app
        try_files {path} /index.html
        file_server
    }
}
```

### Volume Mount for Static Files

```yaml
services:
  caddy:
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - ./frontend/dist:/var/www/app:ro  # Built React app
      - caddy_data:/data
```

---

## 10. Kubernetes Integration

### Proxy to KIND Cluster

When Caddy runs in Docker and needs to reach a KIND cluster:

```caddyfile
# Direct to KIND control-plane container IP
k8s.example.com {
    encode zstd gzip
    reverse_proxy http://172.23.0.3:80
}

# Or via host.docker.internal (if NodePort exposed)
k8s.example.com {
    reverse_proxy http://host.docker.internal:9080
}
```

### Wildcard Subdomain to K8s Ingress

```caddyfile
*.k8s.example.com {
    encode zstd gzip
    reverse_proxy http://172.23.0.3:80
}
```

**Note:** Requires wildcard DNS (e.g., `*.k8s.example.com → your-server-ip`)

### Specific K8s Services

```caddyfile
# MCP Hub on NodePort 30800
mcp.example.com {
    reverse_proxy http://172.23.0.3:30800
}

# Service via Ingress
app.k8s.example.com {
    reverse_proxy http://172.23.0.3:80
}
```

---

## 11. Troubleshooting

### Check Caddy Logs

```bash
docker logs caddy -f

# Or with compose
docker-compose logs -f caddy
```

### Test Configuration

```bash
docker exec caddy caddy validate --config /etc/caddy/Caddyfile
```

### Reload Without Restart

```bash
docker exec caddy caddy reload --config /etc/caddy/Caddyfile
```

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| 502 Bad Gateway | Backend not reachable | Check network connectivity, service name |
| Certificate errors | Port 80 blocked | Ensure port 80 open for ACME challenge |
| Service not found | Wrong network | Add service to `caddy-shared` network |
| WebSocket disconnects | Timeout | Usually works; check backend WebSocket handling |

### Debug Mode

```caddyfile
{
    debug
}
```

### Check Certificate Status

```bash
docker exec caddy caddy list-certs
```

---

## Quick Reference

### Essential Caddyfile Syntax

```caddyfile
# Global options
{
    email your@email.com
}

# Site block
example.com {
    # Directives
    encode zstd gzip
    reverse_proxy backend:8000
}

# Environment variables
{$HOSTNAME} {
    reverse_proxy {$BACKEND}:8000
}

# Matchers
@api path /api/*
handle @api {
    reverse_proxy api:8000
}

# Multiple handlers
handle {
    file_server
}
```

### Common Commands

```bash
# Generate password hash
docker run --rm caddy:2-alpine caddy hash-password

# Validate config
docker exec caddy caddy validate --config /etc/caddy/Caddyfile

# Reload config
docker exec caddy caddy reload --config /etc/caddy/Caddyfile

# Format Caddyfile
docker exec caddy caddy fmt --overwrite /etc/caddy/Caddyfile
```

---

## Resources

- [Caddy Documentation](https://caddyserver.com/docs/)
- [Caddyfile Concepts](https://caddyserver.com/docs/caddyfile/concepts)
- [Caddy Docker Hub](https://hub.docker.com/_/caddy)
- [Caddy Community](https://caddy.community/)
