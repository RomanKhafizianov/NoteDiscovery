# 🔒 NoteDiscovery Authentication Guide

## ⚠️ Default Password Warning

> **Default password is `admin`** — CHANGE THIS before exposing to any network!

---

## Overview

NoteDiscovery includes simple password protection for single-user deployments. When enabled, users must log in before accessing notes.

- ✅ Single user / self-hosted use
- ✅ Passwords hashed with bcrypt
- ✅ Session-based (7 days default, configurable)

---

## Quick Test (Local Only)

For local testing, authentication is **disabled by default**. To test with auth:

1. Set `authentication.enabled: true` in `config.yaml`
2. Restart the app
3. Log in with password: `admin`

⚠️ **Don't use the default password on any network!**

---

## Production Setup

For any deployment exposed to a network, follow these steps:

### Step 1: Generate a Secret Key

The secret key encrypts session cookies. Generate a random one:

```bash
# Docker
docker exec -it notediscovery python -c "import secrets; print(secrets.token_hex(32))"

# Local
python -c "import secrets; print(secrets.token_hex(32))"
```

**Save this key** — you'll need it in Step 2.

---

### Step 2: Configure Authentication

Choose **one** of these options:

#### Option A: Plain Text Password (Recommended)

The easiest approach. Your password is automatically hashed at startup.

**Via Environment Variables (Docker):**
```bash
docker run -d \
  -e AUTHENTICATION_ENABLED=true \
  -e AUTHENTICATION_PASSWORD=your_secure_password \
  -e AUTHENTICATION_SECRET_KEY=your_generated_secret_key \
  ...
```

**Via config.yaml:**
```yaml
authentication:
  enabled: true
  password: "your_secure_password"
  secret_key: "your_generated_secret_key"
```

---

#### Option B: Pre-Hashed Password (Advanced)

For users who prefer to hash passwords themselves.

**Generate a hash:**
```bash
# Docker
docker exec -it notediscovery python generate_password.py

# Local
python generate_password.py
```

**Then configure:**
```yaml
authentication:
  enabled: true
  password_hash: "$2b$12$..."  # paste your hash here
  secret_key: "your_generated_secret_key"
```

---

### Step 3: Restart & Test

```bash
# Docker Compose
docker-compose restart

# Docker run
docker restart notediscovery

# Local
python run.py
```

Navigate to `http://localhost:8000` — you'll be redirected to the login page.

---

## Configuration Priority

If multiple sources are configured, this priority applies (first wins):

| Priority | Source | Type |
|----------|--------|------|
| 1st | `AUTHENTICATION_PASSWORD` env var | Plain text |
| 2nd | `AUTHENTICATION_PASSWORD_HASH` env var | Pre-hashed |
| 3rd | `password` in config.yaml | Plain text |
| 4th | `password_hash` in config.yaml | Pre-hashed |

**Example:** If you set `AUTHENTICATION_PASSWORD` as an env var, it overrides anything in config.yaml.

---

## Security Considerations

### ✅ What This Protects

- Unauthorized access to your notes
- All API endpoints
- Viewing, creating, editing, deleting notes

### ⚠️ What This Doesn't Protect

This is a **simple single-user** system. NOT suitable for:

- ❌ Multi-user environments
- ❌ Public internet without HTTPS
- ❌ Compliance requirements (HIPAA, GDPR, etc.)

### 🛡️ Best Practices

1. **Use HTTPS** — Run behind a reverse proxy (Traefik, nginx, Caddy)
2. **Strong password** — At least 12 characters, mixed case, numbers, symbols
3. **Unique secret key** — Never reuse across applications
4. **Keep config secure** — Don't commit credentials to version control

---

## Disabling Authentication

```yaml
authentication:
  enabled: false
```

Restart the app to apply.
