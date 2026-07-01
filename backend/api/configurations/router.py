"""
api.configurations.router
~~~~~~~~~~~~~~~~~~~~~~~~~
Route handlers for all configuration endpoints.

Three APIRouter instances are defined (one per sub-domain) so that route
prefixes and OpenAPI tags stay identical to the previous flat-package layout.
They are all exported and registered individually in api/__init__.py.
"""
from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.configurations.helpers import get_workspace, llm_config_from_doc
from db.engine import get_db, prepare_document, utcnow
from db.models import LLMConfig
from db.schemas import LLMConfigCreate, LLMConfigRead, LLMConfigUpdate

logger = logging.getLogger("ntr.api.configurations")

# ---------------------------------------------------------------------------
# Categories router
# ---------------------------------------------------------------------------

categories_router = APIRouter(prefix="/api/categories", tags=["Categories"])

CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "common",
        "label": "Common",
        "description": "General-purpose agents and tools that work across any use case as common sub-agents or utilities.",
        "sub_categories": [
            {"id": "utility", "label": "Utility"},
            {"id": "data_processing", "label": "Data Processing"},
            {"id": "communication", "label": "Communication"},
            {"id": "search_retrieval", "label": "Search & Retrieval"},
            {"id": "workflow", "label": "Workflow Automation"},
        ],
    },
    {
        "id": "bfsi",
        "label": "BFSI",
        "description": "Banking, Financial Services, and Insurance — agents and tools specific to financial industry use cases.",
        "sub_categories": [
            {"id": "wealth_management", "label": "Wealth Management"},
            {"id": "trading", "label": "Trading & Markets"},
            {"id": "banking_operations", "label": "Banking Operations"},
            {"id": "insurance", "label": "Insurance"},
            {"id": "tax_compliance", "label": "Tax & Compliance"},
            {"id": "risk_management", "label": "Risk Management"},
            {"id": "payments", "label": "Payments & Transfers"},
            {"id": "fraud_detection", "label": "Fraud Detection"},
        ],
    },
    {
        "id": "healthcare",
        "label": "Healthcare",
        "description": "Healthcare and life-sciences agents and tools for clinical, administrative, and insurance use cases.",
        "sub_categories": [
            {"id": "mediclaim", "label": "Mediclaim & Insurance"},
            {"id": "clinical", "label": "Clinical Operations"},
            {"id": "patient_management", "label": "Patient Management"},
            {"id": "pharmacy", "label": "Pharmacy & Prescriptions"},
            {"id": "diagnostics", "label": "Diagnostics & Lab"},
            {"id": "telemedicine", "label": "Telemedicine"},
        ],
    },
    {
        "id": "retail",
        "label": "Retail & E-Commerce",
        "description": "Retail, e-commerce, and supply chain agents and tools.",
        "sub_categories": [
            {"id": "product_catalog", "label": "Product Catalog"},
            {"id": "order_management", "label": "Order Management"},
            {"id": "customer_service", "label": "Customer Service"},
            {"id": "inventory", "label": "Inventory & Supply Chain"},
            {"id": "promotions", "label": "Promotions & Pricing"},
        ],
    },
    {
        "id": "hr",
        "label": "HR & People",
        "description": "Human resources, talent management, and workforce automation agents and tools.",
        "sub_categories": [
            {"id": "recruitment", "label": "Recruitment & Hiring"},
            {"id": "onboarding", "label": "Onboarding"},
            {"id": "payroll", "label": "Payroll & Benefits"},
            {"id": "performance", "label": "Performance Management"},
            {"id": "learning", "label": "Learning & Development"},
        ],
    },
    {
        "id": "legal",
        "label": "Legal & Compliance",
        "description": "Legal research, document analysis, and regulatory compliance agents and tools.",
        "sub_categories": [
            {"id": "contract_review", "label": "Contract Review"},
            {"id": "regulatory", "label": "Regulatory Compliance"},
            {"id": "legal_research", "label": "Legal Research"},
            {"id": "intellectual_property", "label": "Intellectual Property"},
        ],
    },
    {
        "id": "technology",
        "label": "Technology",
        "description": "Software development, IT operations, and DevOps agents and tools.",
        "sub_categories": [
            {"id": "devops", "label": "DevOps & CI/CD"},
            {"id": "code_generation", "label": "Code Generation"},
            {"id": "incident_management", "label": "Incident Management"},
            {"id": "security", "label": "Security & Compliance"},
            {"id": "data_engineering", "label": "Data Engineering"},
        ],
    },
    {
        "id": "customer_experience",
        "label": "Customer Experience",
        "description": "Customer support, engagement, and experience automation agents and tools.",
        "sub_categories": [
            {"id": "support", "label": "Customer Support"},
            {"id": "sales", "label": "Sales & CRM"},
            {"id": "marketing", "label": "Marketing Automation"},
            {"id": "loyalty", "label": "Loyalty & Retention"},
        ],
    },
]


@categories_router.get("")
async def list_categories() -> list[dict[str, Any]]:
    """Return the canonical list of categories and sub-categories."""
    return CATEGORIES


@categories_router.get("/flat")
async def list_categories_flat() -> list[dict[str, str]]:
    """Return a flat list of all category labels (useful for dropdown menus)."""
    return [{"id": cat["id"], "label": cat["label"]} for cat in CATEGORIES]


@categories_router.get("/{category_id}/sub-categories")
async def list_sub_categories(category_id: str) -> list[dict[str, str]]:
    """Return sub-categories for a given category."""
    for cat in CATEGORIES:
        if cat["id"] == category_id:
            return cat.get("sub_categories", [])
    return []


# ---------------------------------------------------------------------------
# Environment config router
# ---------------------------------------------------------------------------

env_router = APIRouter(prefix="/api/env", tags=["Environment"])


@env_router.get("/llm-credentials")
async def get_llm_credentials():
    """
    Fetch LLM credentials from environment variables.

    Only Ollama details are served from env vars.  All other provider
    configurations are managed per-workspace via the LLM Config API
    (/api/workspaces/{id}/llm-configs).
    """
    return {
        "ollama_api_base": os.getenv("OLLAMA_API_BASE", "http://localhost:11434"),
    }


# ---------------------------------------------------------------------------
# LLM configurations router
# ---------------------------------------------------------------------------

llm_configs_router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/llm-configs",
    tags=["LLM Configurations"],
)


@llm_configs_router.get("", response_model=list[LLMConfigRead])
async def list_llm_configs(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List all LLM configurations for a workspace."""
    await get_workspace(workspace_id, db)
    cursor = db.llm_configs.find({"workspace_id": str(workspace_id)}).sort("created_at", 1)

    configs: list[LLMConfigRead] = []
    async for document in cursor:
        config = llm_config_from_doc(document)
        if config is not None:
            configs.append(LLMConfigRead.model_validate(config))
    return configs


@llm_configs_router.post("", response_model=LLMConfigRead, status_code=status.HTTP_201_CREATED)
async def create_llm_config(
    workspace_id: uuid.UUID,
    body: LLMConfigCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Create a new LLM configuration in a workspace."""
    ws = await get_workspace(workspace_id, db)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot create LLM configurations in the default workspace",
        )

    config = LLMConfig(
        workspace_id=str(workspace_id),
        name=body.name,
        provider=body.provider.value if hasattr(body.provider, "value") else body.provider,
        model_name=body.model_name,
        credentials=body.credentials,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
        created_by="system",
        updated_by="system",
    )
    await db.llm_configs.insert_one(prepare_document(config.model_dump()))
    logger.info("Created LLM config '%s' in workspace %s", config.name, workspace_id)
    return LLMConfigRead.model_validate(config)


@llm_configs_router.get("/{config_id}", response_model=LLMConfigRead)
async def get_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Get a specific LLM configuration."""
    await get_workspace(workspace_id, db)
    config = llm_config_from_doc(await db.llm_configs.find_one({"_id": str(config_id)}))
    if config is None or config.workspace_id != str(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found in workspace {workspace_id}",
        )
    return LLMConfigRead.model_validate(config)


@llm_configs_router.put("/{config_id}", response_model=LLMConfigRead)
async def update_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    body: LLMConfigUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Update an LLM configuration."""
    ws = await get_workspace(workspace_id, db)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify LLM configurations in the default workspace",
        )

    config = llm_config_from_doc(await db.llm_configs.find_one({"_id": str(config_id)}))
    if config is None or config.workspace_id != str(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "provider" and value is not None and hasattr(value, "value"):
            setattr(config, field, value.value)
        else:
            setattr(config, field, value)

    config.updated_by = "system"
    config.updated_at = utcnow()

    await db.llm_configs.replace_one(
        {"_id": str(config_id)},
        prepare_document(config.model_dump()),
    )
    logger.info("Updated LLM config '%s' (%s)", config.name, config_id)
    return LLMConfigRead.model_validate(config)


@llm_configs_router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_llm_config(
    workspace_id: uuid.UUID,
    config_id: uuid.UUID,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """Delete an LLM configuration."""
    ws = await get_workspace(workspace_id, db)

    if ws.is_default:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete LLM configurations from the default workspace",
        )

    config = llm_config_from_doc(await db.llm_configs.find_one({"_id": str(config_id)}))
    if config is None or config.workspace_id != str(workspace_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"LLM config {config_id} not found",
        )

    await db.llm_configs.delete_one({"_id": str(config_id)})
    logger.info("Deleted LLM config '%s' (%s)", config.name, config_id)
