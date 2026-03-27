# Webapp Setup Guide

This guide covers setting up and deploying the FastAPI webapp with Google OAuth authentication.

## Prerequisites

- Python 3.13+
- Google Cloud Platform account
- (Optional) Render account for deployment

## Local Development Setup

### 1. Install Dependencies

Install the webapp dependencies:

```bash
uv sync --extra webapp
```

Or with pip:

```bash
pip install -e ".[webapp]"
```

### 2. Configure Google OAuth

#### Configure OAuth Consent Screen

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
1. Create a new project or select an existing one
1. Go to **APIs & Services** → **OAuth consent screen**
1. Select **External** (or Internal for Google Workspace)
1. Fill in the required fields:
   - App name
   - User support email
   - Developer contact email
1. Add scopes: `email`, `profile`, `openid`
1. Add test users if in testing mode

#### Create OAuth Credentials

1. Navigate to **APIs & Services** → **Credentials**
1. Click **Create Credentials** → **OAuth client ID**
1. Select **Web application**
1. Configure the following:
   - **Name**: Your app name (e.g., "Repomgr Dev")
   - **Authorized JavaScript origins**: `http://localhost:8000`
   - **Authorized redirect URIs**: `http://localhost:8000/auth/google/callback`
1. Click **Create** and note your **Client ID** and **Client Secret**

### 3. Set Environment Variables

Create a `.env` file at `~/cred/repomgr/.env`:

```bash
# Google OAuth (required)
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here

# OAuth redirect URI - must exactly match the entry in Google Cloud Console
# Defaults to http://localhost:{WEBAPP_PORT}/auth/google/callback when unset
# GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback

# Session security (required in production, auto-generated in dev)
SESSION_SECRET_KEY=your_64_char_hex_string_here

# Optional: explicit public base URL for building absolute links in templates
# and API responses (separate from the OAuth redirect URI above)
# PUBLIC_BASE_URL=http://localhost:8000

# Optional overrides
WEBAPP_HOST=0.0.0.0
WEBAPP_PORT=8000
WEBAPP_DEBUG=true
ENV_STAGE_TYPE=dev
ENV_LOCATION_TYPE=local
```

Generate a secure session secret:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Run the Application

Start the development server:

```bash
# Using uvicorn directly
uv run uvicorn repomgr.webapp.app:app --reload

# Or using the app module
uv run python -m repomgr.webapp.app
```

The API will be available at:

- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs (Swagger UI)
- **ReDoc**: http://localhost:8000/redoc

### 5. Download Static Assets

To ensure the webapp uses self-hosted assets, download the required files into the `static/` directory,
using the [cdn_load.sh](https://github.com/Pitrified/repomgr/blob/main/scripts/webapp/cdn_load.sh) script.

These files are referenced in the `/static/` routes of the webapp.

## API Endpoints

### Health Checks

| Endpoint                                              | Method | Description        |
| ----------------------------------------------------- | ------ | ------------------ |
| [`/health`](http://localhost:8000/health)             | GET    | Basic health check |
| [`/health/ready`](http://localhost:8000/health/ready) | GET    | Readiness probe    |
| [`/health/live`](http://localhost:8000/health/live)   | GET    | Liveness probe     |

### Authentication

| Endpoint                                                              | Method | Description                      |
| --------------------------------------------------------------------- | ------ | -------------------------------- |
| [`/auth/google/login`](http://localhost:8000/auth/google/login)       | GET    | Initiate Google OAuth flow       |
| [`/auth/google/callback`](http://localhost:8000/auth/google/callback) | GET    | OAuth callback handler           |
| [`/auth/logout`](http://localhost:8000/auth/logout)                   | POST   | Logout (requires auth)           |
| [`/auth/me`](http://localhost:8000/auth/me)                           | GET    | Get current user (requires auth) |
| [`/auth/status`](http://localhost:8000/auth/status)                   | GET    | Check authentication status      |

### API v1

| Endpoint                                                      | Method | Description                |
| ------------------------------------------------------------- | ------ | -------------------------- |
| [`/api/v1/`](http://localhost:8000/api/v1/)                   | GET    | API version info           |
| [`/api/v1/protected`](http://localhost:8000/api/v1/protected) | GET    | Protected endpoint example |

## Deploying to Render

### 1. Push to GitHub

Ensure your code is pushed to a GitHub repository.

### 2. Create Render Service

**Option A: Using render.yaml (recommended)**

1. Go to [Render Dashboard](https://dashboard.render.com/)
2. Click **New** → **Blueprint**
3. Connect your GitHub repository
4. Render will detect `render.yaml` and create the service

**Option B: Manual setup**

1. Click **New** → **Web Service**
2. Connect your repository
3. Configure:
   - **Build Command**: `pip install .`
   - **Start Command**: `uvicorn repomgr.webapp.app:app --host 0.0.0.0 --port $PORT`

### 3. Configure Environment Variables

In Render Dashboard → Your Service → **Environment**:

| Variable               | Value                                                |
| ---------------------- | ---------------------------------------------------- |
| `GOOGLE_CLIENT_ID`     | Your Google OAuth client ID                          |
| `GOOGLE_CLIENT_SECRET` | Your Google OAuth client secret                      |
| `SESSION_SECRET_KEY`   | Generate with `secrets.token_hex(32)`                |
| `ENV_STAGE_TYPE`       | `prod`                                               |
| `ENV_LOCATION_TYPE`    | `render`                                             |
| `GOOGLE_REDIRECT_URI`  | `https://your-app.onrender.com/auth/google/callback` |
| `PUBLIC_BASE_URL`      | `https://your-app.onrender.com` (for absolute links) |
| `CORS_ALLOWED_ORIGINS` | Your frontend domain(s)                              |

### 4. Update Google OAuth

Add your Render URL to Google OAuth credentials:

- **Authorized JavaScript origins**: `https://your-app.onrender.com`
- **Authorized redirect URIs**: `https://your-app.onrender.com/auth/google/callback`

## Security Considerations

### Production Checklist

- [ ] Set `ENV_STAGE_TYPE=prod`
- [ ] Use a strong `SESSION_SECRET_KEY` (64+ hex characters)
- [ ] Configure CORS with specific origins (no wildcards)
- [ ] Ensure HTTPS is enabled (automatic on Render)
- [ ] Review rate limiting settings
- [ ] Set up monitoring and alerting

### Security Headers

The webapp automatically adds these security headers:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security` (production only)
- `Content-Security-Policy`
- `Referrer-Policy: strict-origin-when-cross-origin`

### Session Security

- Sessions are stored server-side (in-memory by default)
- Session cookies are `HttpOnly` and `Secure` (in production)
- `SameSite=Lax` prevents CSRF attacks
- Sessions expire after 24 hours (configurable)

## Troubleshooting

### OAuth Errors

**"redirect_uri_mismatch"**

The OAuth redirect URI sent by the app must exactly match one of the URIs registered
in Google Cloud Console. The app uses `GOOGLE_REDIRECT_URI` (if set) or falls back to
`http://localhost:{WEBAPP_PORT}/auth/google/callback`.

Common causes:

- Accessing the app via `http://127.0.0.1:8000` while Google Console has
  `http://localhost:8000` (or vice versa). Always use the exact hostname registered.
- Running on a non-default port without setting `GOOGLE_REDIRECT_URI` to match.
- Missing or mismatched entry in Google Cloud Console (check the exact string,
  including scheme, host, port, and path).

Fix for local dev: add `http://localhost:8000/auth/google/callback` to **Authorized
redirect URIs** in Google Cloud Console and access the app via that exact URL.
Set `GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback` in your `.env`
if you want to make the configured value explicit.

**"invalid_client"**

- Verify `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are correct
- Check that the OAuth app is not in "Testing" mode with unverified users

### Session Issues

**"Not authenticated" after login**

- Check that cookies are being set (inspect browser dev tools)
- Verify `SESSION_SECRET_KEY` is consistent across restarts
- For local testing, ensure you're using `http://localhost:8000` (not `127.0.0.1`)

### Health Check Failures

**Readiness check failing**

- Verify `GOOGLE_CLIENT_ID` is set
- Check application logs for startup errors

## Extending the Webapp

### Adding New Routes

1. Create a new router in `src/repomgr/webapp/routers/`
2. Include it in `main.py`:
   ```python
   from repomgr.webapp.routers import new_router
   app.include_router(new_router)
   ```

### Adding Database Support

1. Install a database driver (e.g., `asyncpg` for PostgreSQL)
2. Update `dependencies.py` with database session management
3. Create models in a new `models/` directory
4. Add connection pooling in the lifespan context

### Adding Redis Sessions

1. Add Redis service in `render.yaml`
2. Install `redis` package
3. Replace `SessionStore` with Redis-backed implementation

## Related Documentation

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)
- [Render Documentation](https://render.com/docs)
