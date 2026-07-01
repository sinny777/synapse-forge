"""
api.auth.schemas
~~~~~~~~~~~~~~~~
Pydantic request/response models for the auth domain.
"""
from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Request body for demo username+password login."""
    email: str
    password: str
