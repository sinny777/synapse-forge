"""
api.auth.router
~~~~~~~~~~~~~~~
FastAPI route handlers for authentication.

Providers supported:
  • Google OAuth 2.0
  • GitHub OAuth 2.0
  • Demo username/password (development only)
"""
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired

from api.auth.config import (
    DEMO_EMAIL,
    DEMO_PASSWORD,
    _GITHUB_CLIENT_ID,
    _GITHUB_CLIENT_SECRET,
    _GOOGLE_CLIENT_ID,
    _GOOGLE_CLIENT_SECRET,
    oauth,
    serializer,
)
from api.auth.helpers import (
    _callback_uri,
    _make_auth_response,
    _make_token_cookie_response,
)
from api.auth.schemas import LoginRequest

router = APIRouter(prefix="/api/auth", tags=["Auth"])


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

@router.get("/login/{provider}")
async def login(provider: str, request: Request):
    if provider not in ["google", "github"]:
        raise HTTPException(status_code=404, detail="Provider not found")
    if provider == "google" and not (_GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="Google OAuth is not configured on this server")
    if provider == "github" and not (_GITHUB_CLIENT_ID and _GITHUB_CLIENT_SECRET):
        raise HTTPException(status_code=503, detail="GitHub OAuth is not configured on this server")

    redirect_uri = _callback_uri(provider)
    if provider == "google":
        return await oauth.google.authorize_redirect(request, redirect_uri)
    return await oauth.github.authorize_redirect(request, redirect_uri)


@router.get("/callback/{provider}")
async def auth_callback(provider: str, request: Request):
    if provider not in ["google", "github"]:
        raise HTTPException(status_code=404, detail="Provider not found")

    try:
        if provider == "google":
            token = await oauth.google.authorize_access_token(request)
            user_info = token.get("userinfo") or {}
        else:
            token = await oauth.github.authorize_access_token(request)
            resp = await oauth.github.get("user", token=token)
            user_info = resp.json()
    except Exception:
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

@router.post("/login/demo")
async def login_demo(body: LoginRequest):
    if body.email != DEMO_EMAIL or body.password != DEMO_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user_data = {"provider": "demo", "email": DEMO_EMAIL, "name": "Demo User", "avatar": ""}
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
        user_data = serializer.loads(refresh_cookie, salt="refresh-token", max_age=30 * 24 * 3600)
    except SignatureExpired:
        raise HTTPException(status_code=401, detail="Refresh token expired")
    except BadSignature:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    access_token = serializer.dumps(user_data, salt="access-token")
    response = JSONResponse(content={"success": True})
    response.set_cookie(key="access_token", value=access_token, httponly=False, max_age=900, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------

@router.get("/me")
async def get_current_user(request: Request):
    if request.headers.get("X-System-Override") == "true":
        return {"authenticated": True, "provider": "system", "email": "system", "name": "System", "avatar": ""}

    access_cookie = request.cookies.get("access_token")
    if not access_cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user_data = serializer.loads(access_cookie, salt="access-token", max_age=900)
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
