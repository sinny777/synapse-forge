"""
api.workspaces.service
~~~~~~~~~~~~~~~~~~~~~~
Business logic for cloning tools and agents between workspaces.
"""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from api.common.utils import generate_embedding, model_from_doc
from db.engine import prepare_document
from db.models import Agent, LLMConfig, MCPServerStatus, Tool, ToolType, Workspace

logger = logging.getLogger("ntr.api.workspaces")


async def clone_tool(
    db: AsyncIOMotorDatabase,
    source_tool: Tool,
    target_ws: Workspace,
    email: str | None,
    old_to_new_id: dict[str, str] | None = None,
) -> Tool | None:
    """Deep-copy a single Tool document into the target workspace."""
    exists = await db.tools.find_one({"workspace_id": target_ws.id, "name": source_tool.name})
    if exists:
        return None

    vec = None
    if source_tool.type != ToolType.MCP_SERVER:
        try:
            vec = generate_embedding(target_ws, source_tool.name, source_tool.description, source_tool.schema_def)
        except Exception as exc:
            logger.warning("Embedding generation failed for '%s': %s", source_tool.name, exc)

    new_parent_id = None
    if source_tool.parent_id and old_to_new_id:
        new_parent_id = old_to_new_id.get(str(source_tool.parent_id))

    cloned = Tool(
        workspace_id=target_ws.id,
        name=source_tool.name,
        description=source_tool.description,
        type=source_tool.type,
        is_enabled=source_tool.is_enabled,
        connection_config=source_tool.connection_config,
        schema_def=source_tool.schema_def,
        transport=source_tool.transport,
        command=source_tool.command,
        args=list(source_tool.args) if source_tool.args else None,
        env=dict(source_tool.env) if source_tool.env else None,
        url=source_tool.url,
        status=source_tool.status or MCPServerStatus.DISABLED,
        parent_id=new_parent_id,
        embedding=vec,
        created_by=email,
        updated_by=email,
    )
    await db.tools.insert_one(prepare_document(cloned.model_dump()))

    if old_to_new_id is not None:
        old_to_new_id[str(source_tool.id)] = str(cloned.id)

    return cloned


async def clone_agent(
    db: AsyncIOMotorDatabase,
    source_agent: Agent,
    target_ws: Workspace,
    email: str | None,
    tool_id_mapping: dict[str, str] | None = None,
) -> Agent | None:
    """Deep-copy a single Agent document into the target workspace."""
    exists = await db.agents.find_one({"workspace_id": target_ws.id, "name": source_agent.name})
    if exists:
        return None

    new_tool_ids = None
    if source_agent.attached_tool_ids:
        new_tool_ids = []
        for old_tid in source_agent.attached_tool_ids:
            old_id = str(old_tid)
            if tool_id_mapping and old_id in tool_id_mapping:
                new_tool_ids.append(tool_id_mapping[old_id])
            else:
                logger.warning(
                    "Agent '%s': attached tool %s not found in ID mapping, skipping attachment",
                    source_agent.name,
                    old_tid,
                )

    cloned = Agent(
        workspace_id=target_ws.id,
        name=source_agent.name,
        description=source_agent.description,
        system_prompt=source_agent.system_prompt,
        use_neural_router=source_agent.use_neural_router,
        router_top_k=source_agent.router_top_k,
        memory_type=source_agent.memory_type,
        memory_window=source_agent.memory_window,
        max_iterations=source_agent.max_iterations,
        timeout_seconds=source_agent.timeout_seconds,
        attached_tool_ids=new_tool_ids if new_tool_ids else None,
        collaborator_agent_ids=source_agent.collaborator_agent_ids,
        created_by=email,
        updated_by=email,
    )
    await db.agents.insert_one(prepare_document(cloned.model_dump()))
    return cloned
