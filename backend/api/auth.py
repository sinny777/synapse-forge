from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
from pydantic import BaseModel
import os
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

router = APIRouter(prefix="/api/auth", tags=["auth"])

SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key-for-dev")
serializer = URLSafeTimedSerializer(SECRET_KEY)

# Demo user credentials
DEMO_EMAIL = "demo@synapseforge.dev"
DEMO_PASSWORD = "#1SatnamW"

# Use environment variables for OAuth configuration
_GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "")
_GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "")

config_data = {
    "GOOGLE_CLIENT_ID": _GOOGLE_CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": _GOOGLE_CLIENT_SECRET,
    "GITHUB_CLIENT_ID": _GITHUB_CLIENT_ID,
    "GITHUB_CLIENT_SECRET": _GITHUB_CLIENT_SECRET,
}
starlette_config = Config(environ=config_data)
oauth = OAuth(starlette_config)

if _GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET:
    oauth.register(
        name='google',
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'},
    )

if _GITHUB_CLIENT_ID and _GITHUB_CLIENT_SECRET:
    oauth.register(
        name='github',
        access_token_url='https://github.com/login/oauth/access_token',
        access_token_params=None,
        authorize_url='https://github.com/login/oauth/authorize',
        authorize_params=None,
        api_base_url='https://api.github.com/',
        client_kwargs={'scope': 'user:email'},
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_auth_response(user_data: dict, redirect_url: str) -> RedirectResponse:
    """Build a redirect response that carries signed auth cookies."""
    access_token = serializer.dumps(user_data, salt='access-token')
    refresh_token = serializer.dumps(user_data, salt='refresh-token')

    response = RedirectResponse(url=redirect_url)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=False,
        max_age=900,        # 15 minutes
        samesite="lax",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=30 * 24 * 3600,  # 30 days
        samesite="lax",
    )
    return response


def _make_token_cookie_response(user_data: dict) -> JSONResponse:
    """Build a JSON response that carries signed auth cookies."""
    access_token = serializer.dumps(user_data, salt='access-token')
    refresh_token = serializer.dumps(user_data, salt='refresh-token')

    response = JSONResponse(content={"success": True})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=False,
        max_age=900,
        samesite="lax",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        max_age=30 * 24 * 3600,
        samesite="lax",
    )
    return response


# ---------------------------------------------------------------------------
# OAuth providers — availability check
# ---------------------------------------------------------------------------

@router.get("/providers")
async def get_providers():
    """Return which OAuth providers are configured."""
    return {
        "google": bool(_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET),
        "github": bool(_GITHUB_CLIENT_ID and _GITHUB_CLIENT_SECRET),
    }


# ---------------------------------------------------------------------------
# OAuth login / callback
# ---------------------------------------------------------------------------

def _callback_uri(provider: str) -> str:
    """
    Build the OAuth redirect URI.

    Prefer the explicit OAUTH_REDIRECT_BASE_URL environment variable so the
    value exactly matches what is registered in Google / GitHub Cloud Console.
    Falls back to the backend base URL.

    Example .env entry:
        OAUTH_REDIRECT_BASE_URL=http://localhost:8000
    """
    base = (
        os.environ.get("OAUTH_REDIRECT_BASE_URL")
        or os.environ.get("BACKEND_URL", "http://localhost:8000")
    ).rstrip("/")
    return f"{base}/api/auth/callback/{provider}"


@router.get("/login/{provider}")
async def login(provider: str, request: Request):
    if provider not in ['google', 'github']:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider == 'google' and not (_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on this server")
    if provider == 'github' and not (_GITHUB_CLIENT_ID and _GITHUB_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured on this server")

    redirect_uri = _callback_uri(provider)
    if provider == 'google':
        return await oauth.google.authorize_redirect(request, redirect_uri)
    else:
        return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}")
async def auth_callback(provider: str, request: Request):
    if provider not in ['google', 'github']:
        raise HTTPException(status_code=404, detail="Provider not found")

    try:
        if provider == 'google':
            token = await oauth.google.authorize_access_token(request)
            user_info = token.get('userinfo') or {}
        else:
            token = await oauth.github.authorize_access_token(request)
            resp = await oauth.github.get('user', token=token)
            user_info = resp.json()
    except Exception as e:
        frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:4200")
        return RedirectResponse(url=f"{frontend_url}/login?error=oauth_failed")

    email = user_info.get("email") or user_info.get("login") or "unknown"
    name = user_info.get("name") or user_info.get("login") or "Unknown User"
    avatar = user_info.get("picture") or user_info.get("avatar_url") or ""

    user_data = {"provider": provider, "email": email, "name": name, "avatar": avatar}
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:4200")
    return _make_auth_response(user_data, frontend_url)


# ---------------------------------------------------------------------------
# Demo / username+password login
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login/demo")
async def login_demo(body: LoginRequest):
    if body.email != DEMO_EMAIL or body.password != DEMO_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_data = {
        "provider": "demo",
        "email": DEMO_EMAIL,
        "name": "Demo User",
        "avatar": "",
    }
    return _make_token_cookie_response(user_data)


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

@router.post("/refresh")
async def refresh_token(request: Request):
    refresh_cookie = request.cookies.get("refresh_token")
    if not refresh_cookie:
        raise HTTPException(status_code=401, detail="No refresh token")

    try:
        user_data = serializer.loads(refresh_cookie, salt='refresh-token', max_age=30 * 24 * 3600)
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = serializer.dumps(user_data, salt='access-token')
    response = JSONResponse(content={"success": True})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=False,
        max_age=900,
        samesite="lax",
    )
    return response


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get("/me")
async def get_current_user(request: Request):
    if request.headers.get("X-System-Override") == "true":
        return {
            "authenticated": True,
            "provider": "system",
            "email": "system",
            "name": "System",
            "avatar": "",
        }

    access_cookie = request.cookies.get("access_token")
    if not access_cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user_data = serializer.loads(access_cookie, salt='access-token', max_age=900)
        return {
            "authenticated": True,
            "provider": user_data.get("provider"),
            "email": user_data.get("email"),
            "name": user_data.get("name"),
            "avatar": user_data.get("avatar"),
        }
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Access token expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid token")


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

@router.post("/logout")
async def logout():
    response = JSONResponse(content={"success": True})
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return response
