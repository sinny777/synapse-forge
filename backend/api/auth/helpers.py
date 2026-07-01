"""
api.auth.helpers
~~~~~~~~~~~~~~~~
Helper functions for building auth responses and OAuth redirect URIs.
"""
import os

from fastapi.responses import JSONResponse, RedirectResponse

from api.auth.config import serializer


def _make_auth_response(user_data: dict, redirect_url: str) -> RedirectResponse:
    """Build a redirect response that carries signed auth cookies."""
    access_token = serializer.dumps(user_data, salt="access-token")
    refresh_token = serializer.dumps(user_data, salt="refresh-token")

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
    access_token = serializer.dumps(user_data, salt="access-token")
    refresh_token = serializer.dumps(user_data, salt="refresh-token")

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


def _callback_uri(provider: str) -> str:
    """
    Build the OAuth redirect URI.

    Prefers ``OAUTH_REDIRECT_BASE_URL`` so the value exactly matches what is
    registered in Google / GitHub Cloud Console.  Falls back to ``BACKEND_URL``.
    """
    base = (
        os.environ.get("OAUTH_REDIRECT_BASE_URL")
        or os.environ.get("BACKEND_URL", "http://localhost:8000")
    ).rstrip("/")
    return f"{base}/api/auth/callback/{provider}"
