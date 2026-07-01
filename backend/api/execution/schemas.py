"""
SynapseForge — Execution domain: request / response schemas.
"""

from pydantic import BaseModel, Field


class ExecuteRequest(BaseModel):
    user_prompt: str = Field(..., min_length=1, examples=["What is my account balance?"])
    top_k: int = Field(default=5, ge=1, le=50)
    thread_id: str | None = Field(default=None, description="Session thread for multi-turn")
