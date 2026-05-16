"""
SynapseForge — API Package

All FastAPI routers for the platform.

Router modules:
  Platform CRUD (multi-tenant):
    • workspaces.py             — /api/workspaces
    • tools.py                  — /api/workspaces/{id}/tools
    • agents.py                 — /api/workspaces/{id}/agents
    • orchestrations.py         — /api/workspaces/{id}/orchestrations
    • llm_configs.py            — /api/workspaces/{id}/llm-configs
    • router.py                 — /api/router/predict
    • workspace_cloning.py      — /api/clone/* (deep-copy resources)
    • workspace_environment.py  — /api/workspaces/{id}/environment/start|stop

  Standalone Workflow Pipeline:
    • workflow.py        — /api/generate, /api/train, /api/run, /api/evaluate, /api/status
    • data.py            — /api/data/synthetic, /api/data/tools
    • models.py          — /api/models
    • datasets.py        — /api/datasets
    • env_config.py      — /api/env/llm-credentials
    • scenarios.py       — /api/agents/scenarios, /api/agents/execute
"""


