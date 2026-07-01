"""
api.auth.config
~~~~~~~~~~~~~~~
OAuth provider setup, token serializer, and demo credentials.
Loaded once at import time using environment variables.
"""
import os

from authlib.integrations.starlette_client import OAuth
from itsdangerous import URLSafeTimedSerializer
from starlette.config import Config

# ---------------------------------------------------------------------------
# Token signing
# ---------------------------------------------------------------------------

SECRET_KEY: str = os.environ.get("SECRET_KEY", "super-secret-key-for-dev")
serializer: URLSafeTimedSerializer = URLSafeTimedSerializer(SECRET_KEY)

# ---------------------------------------------------------------------------
# Demo credentials
# ---------------------------------------------------------------------------

DEMO_EMAIL: str = "demo@synapseforge.dev"
DEMO_PASSWORD: str = "#1SatnamW"

# ---------------------------------------------------------------------------
# OAuth credentials (read from environment)
# ---------------------------------------------------------------------------

_GOOGLE_CLIENT_ID: str = os.environ.get("GOOGLE_CLIENT_ID", "")
_GOOGLE_CLIENT_SECRET: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
_GITHUB_CLIENT_ID: str = os.environ.get("GITHUB_CLIENT_ID", "")
_GITHUB_CLIENT_SECRET: str = os.environ.get("GITHUB_CLIENT_SECRET", "")

_config_data = {
    "GOOGLE_CLIENT_ID": _GOOGLE_CLIENT_ID,
    "GOOGLE_CLIENT_SECRET": _GOOGLE_CLIENT_SECRET,
    "GITHUB_CLIENT_ID": _GITHUB_CLIENT_ID,
    "GITHUB_CLIENT_SECRET": _GITHUB_CLIENT_SECRET,
}
_starlette_config = Config(environ=_config_data)
oauth = OAuth(_starlette_config)

if _GOOGLE_CLIENT_ID and _GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

if _GITHUB_CLIENT_ID and _GITHUB_CLIENT_SECRET:
    oauth.register(
        name="github",
        access_token_url="https://github.com/login/oauth/access_token",
        access_token_params=None,
        authorize_url="https://github.com/login/oauth/authorize",
        authorize_params=None,
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "user:email"},
    )
