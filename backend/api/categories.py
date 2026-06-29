"""
SynapseForge — Categories API

Provides the canonical list of categories and sub-categories
available for classifying Agents and Tools.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(
    prefix="/api/categories",
    tags=["Categories"],
)

# ---------------------------------------------------------------------------
# Canonical category taxonomy
# ---------------------------------------------------------------------------

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


@router.get("")
async def list_categories() -> list[dict[str, Any]]:
    """
    Return the canonical list of categories and sub-categories for classifying agents and tools.
    """
    return CATEGORIES


@router.get("/flat")
async def list_categories_flat() -> list[dict[str, str]]:
    """
    Return a flat list of all category labels (useful for dropdown menus).
    """
    return [{"id": cat["id"], "label": cat["label"]} for cat in CATEGORIES]


@router.get("/{category_id}/sub-categories")
async def list_sub_categories(category_id: str) -> list[dict[str, str]]:
    """
    Return sub-categories for a given category.
    """
    for cat in CATEGORIES:
        if cat["id"] == category_id:
            return cat.get("sub_categories", [])
    return []

# Made with Bob
