"""
SynapseForge — API Package

All FastAPI routers organised into 7 domain packages.

Router registry:
  Platform CRUD (multi-tenant):
    • auth               — /api/auth/*
    • workspaces         — /api/workspaces
    • resources          — /api/workspaces/{id}/tools, /api/workspaces/{id}/agents, /api/workspaces/{id}/orchestrations
    • configurations     — /api/workspaces/{id}/llm-configs, /api/categories, /api/env/*
    • workspace_ops      — /api/clone/*, /api/workspaces/{id}/environment/start|stop

  Execution:
    • execution          — /api/router/predict, /api/orchestrator/{id}/execute (SSE)

  Standalone Workflow Pipeline:
    • neural_router_pipeline — /api/generate, /api/train, /api/run, /api/evaluate, /api/status,
                               /api/data/*, /api/datasets/*, /api/models/*, /api/agents/scenarios, /api/agents/execute
"""

from api.auth import router as auth_router
from api.workspaces import router as workspaces_router
from api.resources import router as resources_router
from api.configurations import categories_router, env_router, llm_configs_router
from api.execution import router_predict, orchestrator_router
from api.neural_router_pipeline import router as neural_router_pipeline_router

ALL_ROUTERS = [
    # Platform CRUD
    auth_router,
    workspaces_router,
    resources_router,
    llm_configs_router,
    categories_router,
    env_router,
    # Execution
    router_predict,
    orchestrator_router,
    # Standalone workflow pipeline
    neural_router_pipeline_router,
]
