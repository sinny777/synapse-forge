"""
SynapseForge — Environment / Config API Routes

  • GET /api/env/llm-credentials — fetch LLM provider credentials from env vars
"""

import logging
import os

from fastapi import APIRouter

logger = logging.getLogger("ntr.api.config")

router = APIRouter(prefix="/api/env", tags=["Environment"])


@router.get("/llm-credentials")
async def get_llm_credentials():
    """Fetch LLM credentials from environment variables for all supported providers."""
    return {
        "teacher_model": os.getenv("TEACHER_MODEL", ""),
        "expansion_model": os.getenv("EXPANSION_MODEL", ""),
        "heavy_model": os.getenv("HEAVY_MODEL", ""),
        "ollama_api_base": os.getenv("OLLAMA_API_BASE", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "openai_api_base": os.getenv("OPENAI_API_BASE", ""),
        "openai_organization": os.getenv("OPENAI_ORGANIZATION", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "anthropic_api_base": os.getenv("ANTHROPIC_API_BASE", ""),
        "google_api_key": os.getenv("GOOGLE_API_KEY", ""),
        "google_application_credentials": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        "vertexai_project": os.getenv("VERTEXAI_PROJECT", ""),
        "vertexai_location": os.getenv("VERTEXAI_LOCATION", ""),
        "watsonx_api_key": os.getenv("WATSONX_API_KEY", ""),
        "watsonx_project_id": os.getenv("WATSONX_PROJECT_ID", ""),
        "watsonx_url": os.getenv("WATSONX_URL", ""),
        "watsonx_region": os.getenv("WATSONX_REGION", ""),
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "azure_api_key": os.getenv("AZURE_API_KEY", ""),
        "azure_api_base": os.getenv("AZURE_API_BASE", ""),
        "azure_api_version": os.getenv("AZURE_API_VERSION", ""),
        "azure_ad_token": os.getenv("AZURE_AD_TOKEN", ""),
        "cohere_api_key": os.getenv("COHERE_API_KEY", ""),
        "huggingface_api_key": os.getenv("HUGGINGFACE_API_KEY", ""),
        "huggingface_api_base": os.getenv("HUGGINGFACE_API_BASE", ""),
        "replicate_api_key": os.getenv("REPLICATE_API_KEY", ""),
    }
