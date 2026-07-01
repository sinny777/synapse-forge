"""
api.resources.helpers
~~~~~~~~~~~~~~~~~~~~~
Utility functions for the resources domain (tools, agents, orchestrations).

No DB mutations here — pure converters, formatters, and loaders.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from fastapi import HTTPException

from api.common.utils import model_from_doc, get_workspace_or_404
from db.models import Agent, LLMConfig, Orchestration, Tool, Workspace


# ---------------------------------------------------------------------------
# Doc → model converters
# (thin wrappers over the generic model_from_doc from api.common)
# ---------------------------------------------------------------------------

def tool_from_doc(document: dict | None) -> Tool | None:
    """Convert a MongoDB document into a Tool model."""
    return model_from_doc(document, Tool)


def agent_from_doc(document: dict | None) -> Agent | None:
    """Convert a MongoDB document into an Agent model."""
    return model_from_doc(document, Agent)


def orchestration_from_doc(document: dict | None) -> Orchestration | None:
    """Convert a MongoDB document into an Orchestration model."""
    return model_from_doc(document, Orchestration)


def llm_config_from_doc(document: dict | None) -> LLMConfig | None:
    """Convert a MongoDB document into an LLMConfig model."""
    return model_from_doc(document, LLMConfig)


# ---------------------------------------------------------------------------
# Workspace guard (re-exported for local use)
# ---------------------------------------------------------------------------

async def get_workspace(
    workspace_id: uuid.UUID,
    db: AsyncIOMotorDatabase,
) -> Workspace:
    """Fetch the workspace or raise 404."""
    return await get_workspace_or_404(db, workspace_id)


# ---------------------------------------------------------------------------
# Agent helpers
# ---------------------------------------------------------------------------

async def validate_collaborators(
    db: AsyncIOMotorDatabase,
    workspace_id: uuid.UUID,
    collaborator_ids: list[uuid.UUID] | None,
    agent_id: uuid.UUID | None = None,
) -> list[uuid.UUID] | None:
    """Validate collaborator agent IDs and return a deduplicated list."""
    if collaborator_ids is None:
        return None

    normalized_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for cid in collaborator_ids:
        cid_uuid = cid if isinstance(cid, uuid.UUID) else uuid.UUID(str(cid))
        if agent_id is not None and cid_uuid == agent_id:
            raise HTTPException(status_code=400, detail="An agent cannot collaborate with itself")
        if cid_uuid not in seen:
            seen.add(cid_uuid)
            normalized_ids.append(cid_uuid)

    if not normalized_ids:
        return []

    collaborator_docs = await db.agents.find(
        {
            "workspace_id": str(workspace_id),
            "_id": {"$in": [str(cid) for cid in normalized_ids]},
        },
        {"_id": 1},
    ).to_list(length=None)
    valid_ids = {str(doc["_id"]) for doc in collaborator_docs}
    missing = [str(cid) for cid in normalized_ids if str(cid) not in valid_ids]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid collaborator agents for this workspace: {', '.join(missing)}",
        )

    return normalized_ids


async def build_agent_read_payload(
    db: AsyncIOMotorDatabase,
    agent: Agent,
) -> Any:
    """Build the full AgentRead payload including collaborator summaries."""
    from db.schemas import AgentRead, CollaboratorAgentRead

    collaborator_ids = agent.collaborator_agent_ids or []
    collaborators: list[Agent] = []

    if collaborator_ids:
        collaborator_docs = await db.agents.find(
            {
                "workspace_id": agent.workspace_id,
                "_id": {"$in": [str(cid) for cid in collaborator_ids]},
            }
        ).to_list(length=None)
        collaborators_by_id = {
            c.id: c
            for c in (agent_from_doc(doc) for doc in collaborator_docs)
            if c is not None
        }
        collaborators = [
            collaborators_by_id[cid]
            for cid in collaborator_ids
            if cid in collaborators_by_id
        ]

    payload = AgentRead.model_validate(agent)
    payload.collaborators = [
        CollaboratorAgentRead(
            id=c.id,
            workspace_id=c.workspace_id,
            name=c.name,
            description=c.description,
            system_prompt=c.system_prompt,
        )
        for c in collaborators
    ]
    return payload


async def load_agent_with_workspace_guard(
    db: AsyncIOMotorDatabase,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> Agent:
    """Load an agent, enforcing workspace ownership."""
    agent = agent_from_doc(await db.agents.find_one({"_id": str(agent_id)}))
    if agent is None or agent.workspace_id != str(workspace_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def load_agent_llm_config(
    db: AsyncIOMotorDatabase, agent: Agent
) -> LLMConfig | None:
    """Load the LLM config for an agent, or return None."""
    if not agent.llm_config_id:
        return None
    config = llm_config_from_doc(
        await db.llm_configs.find_one({"_id": str(agent.llm_config_id)})
    )
    if config is None or config.workspace_id != agent.workspace_id:
        return None
    return config


async def load_agent_tools(db: AsyncIOMotorDatabase, agent: Agent) -> list[Tool]:
    """Load and expand all tools attached to an agent."""
    tool_ids = agent.attached_tool_ids or []
    if not tool_ids:
        return []

    attached_tool_docs = await db.tools.find(
        {
            "workspace_id": agent.workspace_id,
            "_id": {"$in": [str(tid) for tid in tool_ids]},
            "is_enabled": True,
        }
    ).to_list(length=None)
    attached_tools = [t for t in (tool_from_doc(doc) for doc in attached_tool_docs) if t is not None]
    tools_by_id = {tool.id: tool for tool in attached_tools}

    mcp_server_ids = [t.id for t in attached_tools if t.type.value == "MCP_SERVER"]
    expanded_child_tools: list[Tool] = []
    if mcp_server_ids:
        child_docs = await db.tools.find(
            {
                "workspace_id": agent.workspace_id,
                "parent_id": {"$in": mcp_server_ids},
                "is_enabled": True,
            }
        ).to_list(length=None)
        expanded_child_tools = [t for t in (tool_from_doc(doc) for doc in child_docs) if t is not None]

    ordered_tools: list[Tool] = []
    seen_ids: set[str] = set()

    for tid in tool_ids:
        attached = tools_by_id.get(str(tid))
        if not attached:
            continue
        if attached.type.value == "MCP_SERVER":
            for child in expanded_child_tools:
                if child.parent_id == attached.id and child.id not in seen_ids:
                    ordered_tools.append(child)
                    seen_ids.add(child.id)
            continue
        if attached.id not in seen_ids:
            ordered_tools.append(attached)
            seen_ids.add(attached.id)

    return ordered_tools


async def load_collaborator_agents(
    db: AsyncIOMotorDatabase, agent: Agent
) -> list[Agent]:
    """Load all collaborator agents for an agent."""
    collaborator_ids = agent.collaborator_agent_ids or []
    if not collaborator_ids:
        return []

    collaborator_docs = await db.agents.find(
        {
            "workspace_id": agent.workspace_id,
            "_id": {"$in": [str(cid) for cid in collaborator_ids]},
        }
    ).to_list(length=None)
    collaborators_by_id = {
        c.id: c
        for c in (agent_from_doc(doc) for doc in collaborator_docs)
        if c is not None
    }
    return [
        collaborators_by_id[cid]
        for cid in collaborator_ids
        if cid in collaborators_by_id
    ]


# ---------------------------------------------------------------------------
# Tool helpers
# ---------------------------------------------------------------------------

def mask_tool_secrets(tool: Tool) -> Tool:
    """Mask sensitive env vars in Tool responses."""
    masked = tool.model_copy(deep=True)
    if masked.env:
        masked.env = {k: "***" for k in masked.env.keys()}
    return masked


def summarize_llm_config(config: LLMConfig | None) -> dict | None:
    """Return a compact summary dict for an LLMConfig."""
    if config is None:
        return None
    return {
        "id": str(config.id),
        "name": config.name,
        "provider": config.provider.value,
        "model_name": config.model_name,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }


def resolve_provider_model(config: LLMConfig | None) -> tuple[str | None, str | None]:
    """Return (provider_name, model_name) ready for LiteLLM."""
    if config is None:
        return None, None
    provider = config.provider.value
    if provider == "ibm_watsonx":
        provider = "watsonx"
    return provider, config.model_name


def apply_llm_credentials(config: LLMConfig | None) -> None:
    """Inject LLM credentials into environment variables."""
    if config is None or not config.credentials:
        return

    provider = config.provider.value
    credentials = config.credentials or {}

    if provider == "ibm_watsonx":
        api_key = credentials.get("api_key") or credentials.get("apikey")
        project_id = credentials.get("project_id")
        region = credentials.get("region", "us-south")
        if api_key:
            os.environ["WATSONX_APIKEY"] = api_key
            os.environ["WATSONX_API_KEY"] = api_key
        if project_id:
            os.environ["WATSONX_PROJECT_ID"] = project_id
        if region:
            os.environ["WATSONX_REGION"] = region
            os.environ["WATSONX_URL"] = (
                region if str(region).startswith("http") else f"https://{region}.ml.cloud.ibm.com"
            )
    elif provider == "openai":
        api_key = credentials.get("api_key") or credentials.get("apikey")
        api_base = credentials.get("api_base") or credentials.get("url")
        if api_key:
            os.environ["OPENAI_API_KEY"] = api_key
        if api_base:
            os.environ["OPENAI_API_BASE"] = api_base
    elif provider == "ollama":
        api_base = credentials.get("api_base") or credentials.get("url")
        if api_base:
            os.environ["OLLAMA_API_BASE"] = api_base
