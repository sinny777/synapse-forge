"""
SynapseForge — API Package

All FastAPI routers for the platform.

Router modules:
  Platform CRUD (multi-tenant):
    • workspaces.py      — /api/workspaces
    • tools.py           — /api/workspaces/{id}/tools
    • agents.py          — /api/workspaces/{id}/agents
    • orchestrations.py  — /api/workspaces/{id}/orchestrations
    • router.py          — /api/router/predict

  Standalone Workflow Pipeline:
    • workflow.py        — /api/generate, /api/train, /api/run, /api/evaluate, /api/status
    • data.py            — /api/data/synthetic, /api/data/tools
    • models.py          — /api/models
    • datasets.py        — /api/datasets
    • env_config.py      — /api/env/llm-credentials
    • scenarios.py       — /api/agents/scenarios, /api/agents/execute
"""
