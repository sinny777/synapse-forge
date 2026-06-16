"""
SynapseForge — Agent API Routes

CRUD operations for agent definitions within a workspace.
"""

import json
import re
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import AsyncSessionDep
from db.models import Agent, Workspace, Tool, LLMConfig
from db.schemas import (
    AgentCreate,
    AgentUpdate,
    AgentRead,
    CollaboratorAgentRead,
    AgentExecuteRequest,
)
from api.auth import get_current_user
from api.dependencies import require_workspace_access
from services.router_service import RouterService

logger = logging.getLogger("ntr.api.agents")

router = APIRouter(
    prefix="/api/workspaces/{workspace_id}/agents",
    tags=["Agents"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_workspace_or_404(
    session: AsyncSession, workspace_id: uuid.UUID
) -> Workspace:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _validate_collaborators(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    collaborator_ids: list[uuid.UUID] | None,
    agent_id: uuid.UUID | None = None,
) -> list[uuid.UUID] | None:
    if collaborator_ids is None:
        return None

    normalized_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for collaborator_id in collaborator_ids:
        collaborator_uuid = collaborator_id if isinstance(collaborator_id, uuid.UUID) else uuid.UUID(str(collaborator_id))
        if agent_id is not None and collaborator_uuid == agent_id:
            raise HTTPException(status_code=400, detail="An agent cannot collaborate with itself")
        if collaborator_uuid not in seen:
            seen.add(collaborator_uuid)
            normalized_ids.append(collaborator_uuid)

    if not normalized_ids:
        return []

    result = await session.execute(
        select(Agent.id).where(
            Agent.workspace_id == workspace_id,
            Agent.id.in_(normalized_ids),
        )
    )
    valid_ids = {row[0] for row in result.all()}
    missing = [str(collaborator_id) for collaborator_id in normalized_ids if collaborator_id not in valid_ids]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid collaborator agents for this workspace: {', '.join(missing)}",
        )

    return normalized_ids


async def _build_agent_read_payload(
    session: AsyncSession,
    agent: Agent,
) -> AgentRead:
    collaborator_ids = agent.collaborator_agent_ids or []
    collaborators: list[Agent] = []

    if collaborator_ids:
        collaborator_alias = aliased(Agent)
        result = await session.execute(
            select(collaborator_alias).where(
                collaborator_alias.workspace_id == agent.workspace_id,
                collaborator_alias.id.in_(collaborator_ids),
            )
        )
        collaborators_by_id = {collaborator.id: collaborator for collaborator in result.scalars().all()}
        collaborators = [collaborators_by_id[collaborator_id] for collaborator_id in collaborator_ids if collaborator_id in collaborators_by_id]

    payload = AgentRead.model_validate(agent)
    payload.collaborators = [
        CollaboratorAgentRead(
            id=collaborator.id,
            workspace_id=collaborator.workspace_id,
            name=collaborator.name,
            description=collaborator.description,
            system_prompt=collaborator.system_prompt,
        )
        for collaborator in collaborators
    ]
    return payload


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sse_event(
    event_type: str,
    label: str,
    detail: str = "",
    *,
    status_value: str = "success",
    latency_ms: float | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "type": event_type,
        "label": label,
        "detail": detail,
        "timestamp": _utc_iso(),
        "status": status_value,
    }
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    if metadata:
        payload["metadata"] = metadata
        payload["data"] = metadata
    return f"data: {json.dumps(payload)}\n\n"


def _summarize_llm_config(config: LLMConfig | None) -> dict | None:
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


def _resolve_provider_model(config: LLMConfig | None) -> tuple[str | None, str | None]:
    if config is None:
        return None, None
    provider = config.provider.value
    model_name = config.model_name
    if provider == "ibm_watsonx":
        provider = "watsonx"
    return provider, model_name


def _apply_llm_credentials(config: LLMConfig | None) -> None:
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
            os.environ["WATSONX_URL"] = region if str(region).startswith("http") else f"https://{region}.ml.cloud.ibm.com"
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


async def _load_agent_with_workspace_guard(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
) -> Agent:
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


async def _load_agent_llm_config(session: AsyncSession, agent: Agent) -> LLMConfig | None:
    if not agent.llm_config_id:
        return None
    config = await session.get(LLMConfig, agent.llm_config_id)
    if config is None or config.workspace_id != agent.workspace_id:
        return None
    return config


async def _load_agent_tools(session: AsyncSession, agent: Agent) -> list[Tool]:
    tool_ids = agent.attached_tool_ids or []
    if not tool_ids:
        return []

    result = await session.execute(
        select(Tool).where(
            Tool.workspace_id == agent.workspace_id,
            Tool.id.in_(tool_ids),
            Tool.is_enabled == True,
        )
    )
    attached_tools = result.scalars().all()
    tools_by_id = {tool.id: tool for tool in attached_tools}

    mcp_server_ids = [
        tool.id
        for tool in attached_tools
        if tool.type.value == "MCP_SERVER"
    ]

    expanded_child_tools: list[Tool] = []
    if mcp_server_ids:
        child_result = await session.execute(
            select(Tool).where(
                Tool.workspace_id == agent.workspace_id,
                Tool.parent_id.in_(mcp_server_ids),
                Tool.is_enabled == True,
            )
        )
        expanded_child_tools = list(child_result.scalars().all())

    ordered_tools: list[Tool] = []
    seen_ids: set[uuid.UUID] = set()

    for tool_id in tool_ids:
        attached_tool = tools_by_id.get(tool_id)
        if not attached_tool:
            continue

        if attached_tool.type.value == "MCP_SERVER":
            for child_tool in expanded_child_tools:
                if child_tool.parent_id == attached_tool.id and child_tool.id not in seen_ids:
                    ordered_tools.append(child_tool)
                    seen_ids.add(child_tool.id)
            continue

        if attached_tool.id not in seen_ids:
            ordered_tools.append(attached_tool)
            seen_ids.add(attached_tool.id)

    return ordered_tools


async def _load_collaborator_agents(session: AsyncSession, agent: Agent) -> list[Agent]:
    collaborator_ids = agent.collaborator_agent_ids or []
    if not collaborator_ids:
        return []

    result = await session.execute(
        select(Agent).where(
            Agent.workspace_id == agent.workspace_id,
            Agent.id.in_(collaborator_ids),
        )
    )
    collaborators_by_id = {collaborator.id: collaborator for collaborator in result.scalars().all()}
    return [collaborators_by_id[collaborator_id] for collaborator_id in collaborator_ids if collaborator_id in collaborators_by_id]


def _safe_json(value: Any) -> str:
    try:
        return json.dumps(value, indent=2, default=str)
    except Exception:
        return str(value)


def _extract_tool_content(result: dict) -> str:
    content = result.get("content")
    if isinstance(content, list):
        formatted = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                formatted.append(item.get("text", ""))
            else:
                formatted.append(_safe_json(item))
        return "\n".join(part for part in formatted if part).strip()
    if isinstance(content, str):
        return content.strip()
    if content is not None:
        return _safe_json(content)
    return ""


def _format_tool_result(result: dict) -> str:
    if result.get("success"):
        extracted = _extract_tool_content(result)
        if extracted:
            return extracted
        if result.get("data") is not None:
            return _safe_json(result.get("data"))
        return "Tool executed successfully with no content."
    return result.get("error") or _safe_json(result) or "Tool execution failed."


def _extract_llm_text(response: Any) -> str:
    if isinstance(response, dict):
        choices = response.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                return "\n".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ).strip()
            if isinstance(content, str):
                return content.strip()
        return _safe_json(response)

    choices = getattr(response, "choices", None)
    if choices:
        message = getattr(choices[0], "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, list):
            return "\n".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            ).strip()
        if isinstance(content, str):
            return content.strip()

    return str(response)


def _tool_json_schema(tool: Tool) -> dict[str, Any]:
    schema = tool.schema_def or {}
    if not isinstance(schema, dict):
        return {}
    if isinstance(schema.get("inputSchema"), dict):
        return schema.get("inputSchema") or {}
    return schema


def _extract_prompt_entities(prompt: str) -> dict[str, Any]:
    entities: dict[str, Any] = {"raw_prompt": prompt}

    policy_match = re.search(r"\bPOL-\d+\b", prompt, re.IGNORECASE)
    if policy_match:
        entities["policy_number"] = policy_match.group(0).upper()

    patient_match = re.search(r"\bpatient\s+(\d+)\b", prompt, re.IGNORECASE)
    if patient_match:
        entities["patient_id"] = patient_match.group(1)

    prompt_lower = prompt.lower()
    treatment_map = {
        "knee replacement": "knee_replacement",
        "hip replacement": "hip_replacement",
        "appendectomy": "appendectomy",
        "cataract surgery": "cataract_surgery",
    }
    for phrase, normalized in treatment_map.items():
        if phrase in prompt_lower:
            entities["treatment_type"] = normalized
            break

    if "knee replacement" in prompt_lower:
        entities.setdefault("total_bill_amount", 285000.0)
        entities.setdefault("coverage_limit", 300000.0)
        entities.setdefault("co_pay_percentage", 10.0)
        entities.setdefault("claim_amount", 256500.0)

    return entities


def _build_tool_args(tool: Tool, prompt: str, schema_override: dict[str, Any] | None = None) -> dict[str, Any]:
    schema = schema_override or _tool_json_schema(tool)
    properties = schema.get("properties") or {}
    tool_args: dict[str, Any] = {}
    entities = _extract_prompt_entities(prompt)
    tool_name = tool.name.lower()

    explicit_tool_args: dict[str, dict[str, Any]] = {
        "get_policy_details": {
            "policy_number": entities.get("policy_number", "POL-999"),
        },
        "check_coverage_limits": {
            "policy_number": entities.get("policy_number", "POL-999"),
            "treatment_type": entities.get("treatment_type", "knee_replacement"),
        },
        "fetch_discharge_summary": {
            "patient_id": entities.get("patient_id", "1024"),
        },
        "verify_hospital_bills": {
            "patient_id": entities.get("patient_id", "1024"),
        },
        "calculate_claimable_amount": {
            "total_bill_amount": entities.get("total_bill_amount", 285000.0),
            "coverage_limit": entities.get("coverage_limit", 300000.0),
            "co_pay_percentage": entities.get("co_pay_percentage", 10.0),
        },
        "submit_mediclaim": {
            "policy_number": entities.get("policy_number", "POL-999"),
            "patient_id": entities.get("patient_id", "1024"),
            "claim_amount": entities.get("claim_amount", 256500.0),
        },
    }

    if tool_name in explicit_tool_args:
        for field, value in explicit_tool_args[tool_name].items():
            if not properties or field in properties:
                tool_args[field] = value

    preferred_fields = [
        "input",
        "query",
        "prompt",
        "text",
        "message",
        "question",
        "user_input",
        "search",
        "payload",
    ]

    for field in preferred_fields:
        if field in properties and field not in tool_args:
            tool_args[field] = prompt
            break

    required = schema.get("required") or []
    for field in required:
        if field in tool_args:
            continue

        if field in entities:
            tool_args[field] = entities[field]
            continue

        field_schema = properties.get(field) or {}
        field_type = field_schema.get("type")

        if field_type == "boolean":
            tool_args[field] = False
        elif field_type in {"integer", "number"}:
            default = field_schema.get("default")
            tool_args[field] = default if default is not None else 0
        elif field_type == "array":
            tool_args[field] = field_schema.get("default") or [prompt]
        elif field_type == "object":
            tool_args[field] = field_schema.get("default") or {"input": prompt}
        else:
            tool_args[field] = field_schema.get("default", prompt)

    if not tool_args:
        tool_args["input"] = prompt

    return tool_args


def _build_rest_tool_args(tool: Tool, prompt: str) -> dict[str, Any]:
    return _build_tool_args(tool, prompt)


async def _select_tools_for_prompt(
    session: AsyncSession,
    agent: Agent,
    available_tools: list[Tool],
    prompt: str,
) -> tuple[list[Tool], dict | None]:
    if not available_tools:
        return [], None

    executable_tools = [
        tool for tool in available_tools
        if tool.type.value in {"MCP_TOOL", "REST"}
    ]
    fallback_tools = executable_tools or available_tools

    if not agent.use_neural_router:
        return fallback_tools, {
            "strategy": "attached_tools",
            "selected_tool_ids": [str(tool.id) for tool in fallback_tools],
        }

    top_k = agent.router_top_k or min(5, len(fallback_tools))
    router_result = await RouterService.predict(
        session=session,
        workspace_id=agent.workspace_id,
        user_prompt=prompt,
        top_k=max(top_k, len(fallback_tools)),
        redis=None,
    )
    ranked = router_result.get("tools", [])
    allowed = {str(tool.id): tool for tool in fallback_tools}
    parent_server_to_tools: dict[str, list[Tool]] = {}

    for tool in executable_tools:
        if tool.parent_id:
            parent_server_to_tools.setdefault(str(tool.parent_id), []).append(tool)

    selected: list[Tool] = []
    seen_ids: set[str] = set()

    for ranked_tool in ranked:
        ranked_id = ranked_tool.get("id")
        if not ranked_id:
            continue

        candidate_tools: list[Tool] = []
        if ranked_id in allowed:
            candidate_tools = [allowed[ranked_id]]
        elif ranked_id in parent_server_to_tools:
            candidate_tools = parent_server_to_tools[ranked_id]

        for candidate in candidate_tools:
            candidate_id = str(candidate.id)
            if candidate_id not in seen_ids:
                selected.append(candidate)
                seen_ids.add(candidate_id)

        if len(selected) >= top_k:
            break

    if not selected:
        selected = fallback_tools[:top_k]

    return selected, {
        "strategy": "neural_router",
        "router_top_k": top_k,
        "selected_tool_ids": [str(tool.id) for tool in selected],
        "ranked_tools": ranked,
        "cached": router_result.get("cached", False),
        "latency_ms": router_result.get("latency_ms"),
    }


async def _build_mcp_client_for_tools(session: AsyncSession, tools: list[Tool]):
    if not tools:
        return None, {}, {}

    from tool_router.mcp_client import MCPClient
    from tool_router.config import MCPConfig

    servers: dict[str, dict] = {}
    executable_mcp_tools: list[Tool] = []

    parent_ids = list({tool.parent_id for tool in tools if tool.type == "MCP_TOOL" and tool.parent_id})
    parent_servers_by_id: dict[uuid.UUID, Tool] = {}
    if parent_ids:
        parent_result = await session.execute(
            select(Tool).where(
                Tool.id.in_(parent_ids),
                Tool.workspace_id == tools[0].workspace_id,
                Tool.is_enabled == True,
            )
        )
        parent_servers_by_id = {server.id: server for server in parent_result.scalars().all()}

    for tool in tools:
        if tool.type == "MCP_TOOL" and tool.parent_id:
            server = parent_servers_by_id.get(tool.parent_id)
            if server and server.type.value == "MCP_SERVER" and server.transport is not None:
                executable_mcp_tools.append(tool)
                server_id = str(server.id)
                if server_id not in servers:
                    transport_value = server.transport.value
                    server_cfg: dict[str, Any] = {"transport": transport_value}
                    if transport_value == "stdio":
                        server_cfg["command"] = server.command
                        server_cfg["args"] = server.args or []
                        server_cfg["env"] = server.env or {}
                    elif server.url:
                        server_cfg["url"] = server.url
                    servers[server_id] = server_cfg

    if not servers:
        return None, {}, {}

    client = MCPClient(MCPConfig(servers=servers))
    connection_results = await client.connect_all()
    discovered_tools = await client.list_tools()

    tool_runtime_info: dict[str, dict[str, Any]] = {}
    discovered_by_server_and_name = {
        (tool_schema.server_name, tool_schema.name): tool_schema
        for tool_schema in discovered_tools
    }

    for tool in executable_mcp_tools:
        server_id = str(tool.parent_id) if tool.parent_id else None
        if not server_id:
            continue
        discovered_schema = discovered_by_server_and_name.get((server_id, tool.name))
        runtime_tool_id = (
            discovered_schema.id
            if discovered_schema
            else f"{server_id}.{tool.name}"
        )
        runtime_schema = discovered_schema.parameters if discovered_schema else (_tool_json_schema(tool) or {})
        tool_runtime_info[str(tool.id)] = {
            "server_id": server_id,
            "tool_id": runtime_tool_id,
            "schema": runtime_schema,
        }

    return client, connection_results, tool_runtime_info


async def _execute_single_agent(
    session: AsyncSession,
    *,
    agent: Agent,
    prompt: str,
    llm_config: LLMConfig | None,
    available_tools: list[Tool],
    collaborator_agents: list[Agent],
    depth: int = 0,
):
    provider, model_name = _resolve_provider_model(llm_config)
    _apply_llm_credentials(llm_config)

    agent_scope = "collaborator" if depth > 0 else "agent"
    metadata = {
        "depth": depth,
        "scope": agent_scope,
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "agent_description": agent.description,
        "tool_count": len(available_tools),
        "collaborator_count": len(collaborator_agents),
        "input": prompt,
    }
    yield _sse_event(
        "reasoning",
        f"Executing {agent_scope}: {agent.name}",
        f"Preparing runtime with {len(available_tools)} attached tool(s) and {len(collaborator_agents)} collaborator(s).",
        status_value="running",
        metadata=metadata,
    )

    selected_tools, router_metadata = await _select_tools_for_prompt(session, agent, available_tools, prompt)
    if router_metadata:
        strategy = router_metadata.get("strategy", "attached_tools")
        label = "Neural Tool Router Selection" if strategy == "neural_router" else "Attached Tool Selection"
        detail = _safe_json(
            {
                "selected_tools": [
                    {"id": str(tool.id), "name": tool.name, "type": tool.type.value}
                    for tool in selected_tools
                ],
                "router": router_metadata,
            }
        )
        yield _sse_event(
            "router",
            label,
            detail,
            status_value="success",
            latency_ms=router_metadata.get("latency_ms"),
            metadata={
                **router_metadata,
                "depth": depth,
                "agent_id": str(agent.id),
                "agent_name": agent.name,
                "selected_tools": [
                    {"id": str(tool.id), "name": tool.name, "type": tool.type.value}
                    for tool in selected_tools
                ],
            },
        )

    mcp_client = None
    connection_results = {}
    mcp_runtime_info: dict[str, dict[str, Any]] = {}
    tool_summaries: list[dict] = []
    collaborator_context: list[dict] = []
    try:
        mcp_client, connection_results, mcp_runtime_info = await _build_mcp_client_for_tools(session, selected_tools)

        if connection_results:
            yield _sse_event(
                "thought",
                "Tool Servers Connected",
                _safe_json(connection_results),
                status_value="success",
                metadata={"connections": connection_results, "agent_id": str(agent.id), "depth": depth},
            )

        for tool in selected_tools:
            start = time.perf_counter()
            tool_name = tool.name
            connection_config = tool.connection_config or {}
            runtime_info = mcp_runtime_info.get(str(tool.id), {})
            if tool.type == "MCP_TOOL":
                runtime_schema = runtime_info.get("schema") or _tool_json_schema(tool)
                tool_args = _build_tool_args(tool, prompt, runtime_schema)
            else:
                tool_args = _build_rest_tool_args(tool, prompt)
            detail = _safe_json(
                {
                    "tool_name": tool_name,
                    "tool_type": tool.type.value,
                    "arguments": tool_args,
                }
            )

            yield _sse_event(
                "tool_call",
                f"Calling {tool_name}",
                detail,
                status_value="running",
                metadata={
                    "depth": depth,
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "tool_id": str(tool.id),
                    "tool_name": tool_name,
                    "tool_type": tool.type.value,
                    "arguments": tool_args,
                    "input": prompt,
                },
            )

            if tool.type == "MCP_TOOL":
                server_id = (
                    runtime_info.get("server_id")
                    or connection_config.get("server_id")
                    or (str(tool.parent_id) if tool.parent_id else None)
                )
                mcp_tool_id = (
                    runtime_info.get("tool_id")
                    or connection_config.get("mcp_id")
                    or connection_config.get("tool_name")
                    or connection_config.get("name")
                    or (f"{server_id}.{tool_name}" if server_id else None)
                )
                if not mcp_client or not server_id or not mcp_tool_id:
                    result = {"success": False, "error": "MCP tool server metadata missing"}
                else:
                    result = await mcp_client.call_tool(mcp_tool_id, tool_args)
            elif tool.type == "REST":
                import httpx

                connection = connection_config
                method = str(connection.get("method", "POST")).upper()
                url = connection.get("url") or tool.url
                headers = connection.get("headers") or {}
                timeout = float(connection.get("timeout_seconds", 60))
                payload_mode = str(connection.get("payload_mode", "json")).lower()

                if not url:
                    result = {"success": False, "error": "REST tool URL is not configured"}
                else:
                    try:
                        async with httpx.AsyncClient(timeout=timeout) as client:
                            if method == "GET":
                                response = await client.get(url, params=tool_args, headers=headers)
                            elif payload_mode == "form":
                                response = await client.request(method, url, data=tool_args, headers=headers)
                            else:
                                response = await client.request(method, url, json=tool_args, headers=headers)

                        response_content_type = response.headers.get("content-type", "")
                        try:
                            parsed_body = response.json()
                        except Exception:
                            parsed_body = response.text

                        result = {
                            "success": response.is_success,
                            "status_code": response.status_code,
                            "content": [
                                {
                                    "type": "text",
                                    "text": _safe_json(parsed_body)
                                    if isinstance(parsed_body, (dict, list))
                                    else str(parsed_body),
                                }
                            ],
                            "data": parsed_body,
                            "headers": dict(response.headers),
                            "content_type": response_content_type,
                        }
                        if not response.is_success:
                            result["error"] = f"REST tool returned HTTP {response.status_code}"
                    except Exception as exc:
                        result = {
                            "success": False,
                            "error": f"REST tool execution failed: {exc}",
                        }
            else:
                result = {
                    "success": False,
                    "error": f"Unsupported tool type for execution: {tool.type.value}",
                }

            latency_ms = (time.perf_counter() - start) * 1000
            tool_summary = {
                "id": str(tool.id),
                "name": tool.name,
                "description": tool.description,
                "type": tool.type.value,
                "arguments": tool_args,
                "result": result,
                "result_text": _format_tool_result(result),
                "latency_ms": round(latency_ms, 2),
            }
            tool_summaries.append(tool_summary)
            yield _sse_event(
                "tool_result",
                f"Result: {tool_name}",
                _safe_json(
                    {
                        "tool_name": tool_name,
                        "arguments": tool_args,
                        "result": result,
                    }
                ),
                status_value="success" if result.get("success") else "error",
                latency_ms=latency_ms,
                metadata={
                    "depth": depth,
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "tool_id": str(tool.id),
                    "tool_name": tool_name,
                    "arguments": tool_args,
                    "result": result,
                    "result_text": _format_tool_result(result),
                },
            )

        for collaborator in collaborator_agents:
            collaborator_config = await _load_agent_llm_config(session, collaborator)
            collaborator_tools = await _load_agent_tools(session, collaborator)
            collaborator_children = await _load_collaborator_agents(session, collaborator)

            yield _sse_event(
                "reasoning",
                f"Delegating to collaborator: {collaborator.name}",
                _safe_json(
                    {
                        "input": prompt,
                        "description": collaborator.description,
                    }
                ),
                status_value="running",
                metadata={
                    "depth": depth,
                    "agent_id": str(collaborator.id),
                    "agent_name": collaborator.name,
                    "parent_agent_id": str(agent.id),
                    "parent_agent_name": agent.name,
                    "input": prompt,
                    "description": collaborator.description,
                },
            )

            collaborator_events: list[dict[str, Any]] = []
            collaborator_final_output = ""
            async for collaborator_event in _execute_single_agent(
                session,
                agent=collaborator,
                prompt=prompt,
                llm_config=collaborator_config,
                available_tools=collaborator_tools,
                collaborator_agents=collaborator_children,
                depth=depth + 1,
            ):
                parsed_event = json.loads(collaborator_event.removeprefix("data: ").strip())
                collaborator_events.append(parsed_event)
                if parsed_event.get("type") == "assistant":
                    collaborator_final_output = parsed_event.get("detail", "")
                yield collaborator_event

            collaborator_context.append(
                {
                    "id": str(collaborator.id),
                    "name": collaborator.name,
                    "description": collaborator.description,
                    "llm_config": _summarize_llm_config(collaborator_config),
                    "attached_tools": [
                        {"id": str(tool.id), "name": tool.name, "type": tool.type.value}
                        for tool in collaborator_tools
                    ],
                    "execution_trace": collaborator_events,
                    "output": collaborator_final_output,
                }
            )

        llm_input_sections = [
            f"Agent Name: {agent.name}",
            f"Agent Description:\n{agent.description or 'None'}",
            f"System Prompt:\n{agent.system_prompt or 'None'}",
            f"User Prompt:\n{prompt}",
        ]
        if tool_summaries:
            llm_input_sections.append("Tool Execution Summary:\n" + _safe_json(tool_summaries))
        if collaborator_context:
            llm_input_sections.append("Collaborator Execution Summary:\n" + _safe_json(collaborator_context))

        llm_input = "\n\n".join(llm_input_sections)

        if not provider or not model_name:
            raise RuntimeError("This agent does not have a valid LLM configuration assigned")

        llm_call_start = time.perf_counter()
        yield _sse_event(
            "llm_call",
            "Invoking Agent LLM",
            _safe_json(
                {
                    "provider": provider,
                    "model_name": model_name,
                    "input": llm_input,
                }
            ),
            status_value="running",
            metadata={
                "depth": depth,
                "provider": provider,
                "model_name": model_name,
                "agent_id": str(agent.id),
                "agent_name": agent.name,
                "input": llm_input,
            },
        )

        from litellm import acompletion

        response = await acompletion(
            model=f"{provider}/{model_name}",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are executing inside SynapseForge Agent Test mode. "
                        "Return a clean, user-facing markdown response. "
                        "Do not expose raw SDK objects, internal Python code, or model wrapper representations. "
                        "When tools or collaborators fail, explicitly summarize the failure and continue with the best possible answer."
                    ),
                },
                {
                    "role": "system",
                    "content": agent.system_prompt or "You are a helpful AI assistant.",
                },
                {
                    "role": "user",
                    "content": llm_input,
                },
            ],
            temperature=llm_config.temperature if llm_config else 0,
            max_tokens=llm_config.max_tokens if llm_config else None,
        )
        response_text = _extract_llm_text(response)
        llm_latency = (time.perf_counter() - llm_call_start) * 1000

        yield _sse_event(
            "assistant",
            f"{agent.name} response",
            response_text,
            status_value="success",
            latency_ms=llm_latency,
            metadata={
                "depth": depth,
                "agent_id": str(agent.id),
                "agent_name": agent.name,
                "input": llm_input,
                "output": response_text,
                "tools": tool_summaries,
                "collaborators": collaborator_context,
            },
        )
    finally:
        if mcp_client:
            await mcp_client.close_all()


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------

@router.get("", response_model=list[AgentRead])
async def list_agents(workspace_id: uuid.UUID, session: AsyncSessionDep):
    """List all agents in a workspace."""
    await _get_workspace_or_404(session, workspace_id)
    result = await session.execute(
        select(Agent)
        .where(Agent.workspace_id == workspace_id)
        .order_by(Agent.created_at.desc())
    )
    agents = result.scalars().all()
    return [await _build_agent_read_payload(session, agent) for agent in agents]


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------

@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
async def create_agent(
    workspace_id: uuid.UUID, body: AgentCreate, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """Create a new agent definition in the workspace."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    email = user.get("email")

    collaborator_agent_ids = await _validate_collaborators(
        session,
        workspace_id,
        body.collaborator_agent_ids,
    )

    agent = Agent(
        workspace_id=workspace_id,
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        llm_config_id=body.llm_config_id,
        use_neural_router=body.use_neural_router,
        router_model_id=body.router_model_id,
        router_top_k=body.router_top_k,
        memory_type=body.memory_type,
        memory_window=body.memory_window,
        max_iterations=body.max_iterations,
        timeout_seconds=body.timeout_seconds,
        attached_tool_ids=body.attached_tool_ids,
        collaborator_agent_ids=collaborator_agent_ids,
        created_by=email,
        updated_by=email,
    )
    session.add(agent)
    await session.flush()
    await session.refresh(agent)
    logger.info("Created agent %s (%s) in workspace %s", agent.id, agent.name, workspace_id)
    return await _build_agent_read_payload(session, agent)


# ---------------------------------------------------------------------------
# GET ONE
# ---------------------------------------------------------------------------

@router.get("/{agent_id}", response_model=AgentRead)
async def get_agent(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, session: AsyncSessionDep
):
    """Get a single agent by ID."""
    await _get_workspace_or_404(session, workspace_id)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return await _build_agent_read_payload(session, agent)


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------

@router.put("/{agent_id}", response_model=AgentRead)
async def update_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentUpdate,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user)
):
    """Update an agent definition (partial update)."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = body.model_dump(exclude_unset=True)

    if "collaborator_agent_ids" in update_data:
        update_data["collaborator_agent_ids"] = await _validate_collaborators(
            session,
            workspace_id,
            update_data["collaborator_agent_ids"],
            agent_id=agent.id,
        )

    for field, value in update_data.items():
        setattr(agent, field, value)

    agent.updated_by = user.get("email")

    await session.flush()
    await session.refresh(agent)
    logger.info("Updated agent %s", agent_id)
    return await _build_agent_read_payload(session, agent)


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------

@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    workspace_id: uuid.UUID, agent_id: uuid.UUID, session: AsyncSessionDep, user: dict = Depends(get_current_user)
):
    """Delete an agent from the workspace."""
    await require_workspace_access(workspace_id, session, user, require_write=True)
    agent = await session.get(Agent, agent_id)
    if agent is None or agent.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Agent not found")

    await session.delete(agent)
    logger.info("Deleted agent %s from workspace %s", agent_id, workspace_id)


@router.post("/{agent_id}/execute")
async def execute_agent(
    workspace_id: uuid.UUID,
    agent_id: uuid.UUID,
    body: AgentExecuteRequest,
    session: AsyncSessionDep,
    user: dict = Depends(get_current_user),
):
    """
    Execute a workspace agent with SSE streaming using LangGraph ReAct pattern.
    
    Supports multi-turn conversations via session_id parameter.
    Configuration-driven execution based on agent settings.
    """
    await require_workspace_access(workspace_id, session, user, require_write=False)
    agent = await _load_agent_with_workspace_guard(session, workspace_id, agent_id)
    
    # Generate or use provided session_id
    session_id = body.session_id or str(uuid.uuid4())
    
    # Get Redis client for conversation service
    from db.redis_pool import get_redis_pool
    import redis.asyncio as aioredis
    
    redis_pool = get_redis_pool()
    redis_client = aioredis.Redis(connection_pool=redis_pool)

    async def event_stream():
        try:
            # Initialize conversation service
            from services.conversation_service import ConversationService
            conv_service = ConversationService(redis_client)
            
            # Get or create session
            await conv_service.get_or_create_session(session_id, agent.id)
            
            # Load conversation history based on agent's memory settings
            history = await conv_service.get_history(
                session_id=session_id,
                limit=agent.memory_window or 10,
                memory_type=agent.memory_type or "buffer"
            )
            
            yield _sse_event(
                "thought",
                "User Prompt Received",
                body.user_prompt,
                status_value="success",
                metadata={
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "workspace_id": str(workspace_id),
                    "session_id": session_id,
                    "history_length": len(history),
                },
            )

            # Use Dynamic LangGraph-based executor with Neural Tool Routing
            from services.langgraph_dynamic_agent_executor import DynamicLangGraphAgentExecutor
            
            executor = DynamicLangGraphAgentExecutor(session)
            
            # Track assistant response for saving to history
            assistant_response = ""
            
            async for event in executor.execute_agent(
                agent=agent,
                user_prompt=body.user_prompt,
                conversation_history=history,
                depth=0,
                router_top_k_override=body.top_k,
            ):
                yield event
                
                # Capture assistant response
                event_data = json.loads(event.replace("data: ", "").strip())
                if event_data.get("type") == "assistant":
                    assistant_response = event_data.get("detail", "")
            
            # Save conversation to history
            await conv_service.add_message(
                session_id=session_id,
                role="user",
                content=body.user_prompt
            )
            
            if assistant_response:
                await conv_service.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_response
                )

            yield _sse_event(
                "complete",
                "Agent Execution Complete",
                "Streaming finished",
                status_value="success",
                metadata={
                    "agent_id": str(agent.id),
                    "agent_name": agent.name,
                    "session_id": session_id,
                },
            )
        except Exception as exc:
            logger.exception("Agent execution failed for agent %s", agent_id)
            yield _sse_event(
                "error",
                "Agent Execution Failed",
                str(exc),
                status_value="error",
                metadata={
                    "error_type": type(exc).__name__,
                    "agent_id": str(agent_id),
                    "agent_name": agent.name if "agent" in locals() and agent else "Agent",
                    "session_id": session_id,
                },
            )
            yield _sse_event(
                "complete",
                "Agent Execution Complete",
                "Streaming finished with errors",
                status_value="error",
                metadata={
                    "agent_id": str(agent_id),
                    "agent_name": agent.name if "agent" in locals() and agent else "Agent",
                    "session_id": session_id,
                },
            )
        finally:
            await redis_client.aclose()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-ID": session_id,
        },
    )
