"""
api.configurations
~~~~~~~~~~~~~~~~~~
Domain package for platform configuration endpoints:
  • categories    — canonical taxonomy for agents & tools
  • env_config    — environment-based credentials
  • llm_configs   — per-workspace LLM provider configurations
"""
from .router import categories_router, env_router, llm_configs_router

__all__ = ["categories_router", "env_router", "llm_configs_router"]
