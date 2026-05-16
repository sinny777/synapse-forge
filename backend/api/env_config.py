"""
SynapseForge — Environment / Config API Routes

  • GET /api/env/llm-credentials — fetch Ollama config from env vars
"""

import logging
import os

from fastapi import APIRouter

logger = logging.getLogger("ntr.api.config")

router = APIRouter(prefix="/api/env", tags=["Environment"])


@router.get("/llm-credentials")
async def get_llm_credentials():
    """Fetch LLM credentials from environment variables.
    
    Only Ollama details are served from env vars. All other provider
    configurations are managed per-workspace via the LLM Config API
    (/api/workspaces/{id}/llm-configs).
    """
    return {
        "ollama_api_base": os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
    }
