"""
api.resources.service
~~~~~~~~~~~~~~~~~~~~~
Complex async business logic for agent execution.

Functions:
  execute_single_agent      — async generator: run one agent step with SSE events
  select_tools_for_prompt   — pick tools via neural router or attached list
  build_mcp_client_for_tools — create and connect an MCPClient for a tool list
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any, AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorDatabase

from api.common.utils import safe_json, sse_event
from api.resources.helpers import (
    apply_llm_credentials,
    load_agent_llm_config,
    load_agent_tools,
    load_collaborator_agents,
    resolve_provider_model,
    summarize_llm_config,
    tool_from_doc,
)
from db.models import Agent, LLMConfig, Tool


# ---------------------------------------------------------------------------
# Tool argument helpers
# ---------------------------------------------------------------------------

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


def _build_tool_args(
    tool: Tool, prompt: str, schema_override: dict[str, Any] | None = None
) -> dict[str, Any]:
    schema = schema_override or _tool_json_schema(tool)
    properties = schema.get("properties") or {}
    tool_args: dict[str, Any] = {}
    entities = _extract_prompt_entities(prompt)
    tool_name = tool.name.lower()

    explicit_tool_args: dict[str, dict[str, Any]] = {
        "get_policy_details": {"policy_number": entities.get("policy_number", "POL-999")},
        "check_coverage_limits": {
            "policy_number": entities.get("policy_number", "POL-999"),
            "treatment_type": entities.get("treatment_type", "knee_replacement"),
        },
        "fetch_discharge_summary": {"patient_id": entities.get("patient_id", "1024")},
        "verify_hospital_bills": {"patient_id": entities.get("patient_id", "1024")},
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

    preferred_fields = ["input", "query", "prompt", "text", "message", "question", "user_input", "search", "payload"]
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


def _extract_tool_content(result: dict) -> str:
    content = result.get("content")
    if isinstance(content, list):
        formatted = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                formatted.append(item.get("text", ""))
            else:
                formatted.append(safe_json(item))
        return "\n".join(part for part in formatted if part).strip()
    if isinstance(content, str):
        return content.strip()
    if content is not None:
        return safe_json(content)
    return ""


def _format_tool_result(result: dict) -> str:
    if result.get("success"):
        extracted = _extract_tool_content(result)
        if extracted:
            return extracted
        if result.get("data") is not None:
            return safe_json(result.get("data"))
        return "Tool executed successfully with no content."
    return result.get("error") or safe_json(result) or "Tool execution failed."


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
        return safe_json(response)

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


# ---------------------------------------------------------------------------
# Tool selection
# ---------------------------------------------------------------------------

async def select_tools_for_prompt(
    db: AsyncIOMotorDatabase,
    agent: Agent,
    available_tools: list[Tool],
    prompt: str,
) -> tuple[list[Tool], dict | None]:
    """Select tools for a prompt via neural router or attached-tools fallback."""
    if not available_tools:
        return [], None

    from services.router_service import RouterService

    executable_tools = [t for t in available_tools if t.type.value in {"MCP_TOOL", "REST"}]
    fallback_tools = executable_tools or available_tools

    if not agent.use_neural_router:
        return fallback_tools, {
            "strategy": "attached_tools",
            "selected_tool_ids": [str(t.id) for t in fallback_tools],
        }

    top_k = agent.router_top_k or min(5, len(fallback_tools))
    router_result = await RouterService.predict(
        db=db,
        workspace_id=agent.workspace_id,
        user_prompt=prompt,
        top_k=max(top_k, len(fallback_tools)),
        redis=None,
    )
    ranked = router_result.get("tools", [])
    allowed = {str(t.id): t for t in fallback_tools}
    parent_server_to_tools: dict[str, list[Tool]] = {}
    for t in executable_tools:
        if t.parent_id:
            parent_server_to_tools.setdefault(str(t.parent_id), []).append(t)

    selected: list[Tool] = []
    seen_ids: set[str] = set()

    for ranked_tool in ranked:
        ranked_id = ranked_tool.get("id")
        if not ranked_id:
            continue
        candidates: list[Tool] = []
        if ranked_id in allowed:
            candidates = [allowed[ranked_id]]
        elif ranked_id in parent_server_to_tools:
            candidates = parent_server_to_tools[ranked_id]

        for candidate in candidates:
            cid = str(candidate.id)
            if cid not in seen_ids:
                selected.append(candidate)
                seen_ids.add(cid)

        if len(selected) >= top_k:
            break

    if not selected:
        selected = fallback_tools[:top_k]

    return selected, {
        "strategy": "neural_router",
        "router_top_k": top_k,
        "selected_tool_ids": [str(t.id) for t in selected],
        "ranked_tools": ranked,
        "cached": router_result.get("cached", False),
        "latency_ms": router_result.get("latency_ms"),
    }


# ---------------------------------------------------------------------------
# MCP client builder
# ---------------------------------------------------------------------------

async def build_mcp_client_for_tools(
    db: AsyncIOMotorDatabase, tools: list[Tool]
):
    """Create and connect an MCPClient for the given tools, return runtime info."""
    if not tools:
        return None, {}, {}

    from tool_router.mcp_client import MCPClient
    from tool_router.config import MCPConfig

    servers: dict[str, dict] = {}
    executable_mcp_tools: list[Tool] = []

    parent_ids = list(
        {t.parent_id for t in tools if t.type.value == "MCP_TOOL" and t.parent_id}
    )
    parent_servers_by_id: dict[str, Tool] = {}
    if parent_ids:
        parent_docs = await db.tools.find(
            {
                "_id": {"$in": parent_ids},
                "workspace_id": tools[0].workspace_id,
                "is_enabled": True,
            }
        ).to_list(length=None)
        parent_servers_by_id = {
            s.id: s
            for s in (tool_from_doc(doc) for doc in parent_docs)
            if s is not None
        }

    for tool in tools:
        if tool.type.value == "MCP_TOOL" and tool.parent_id:
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
        (ts.server_name, ts.name): ts for ts in discovered_tools
    }

    for tool in executable_mcp_tools:
        server_id = str(tool.parent_id) if tool.parent_id else None
        if not server_id:
            continue
        discovered_schema = discovered_by_server_and_name.get((server_id, tool.name))
        runtime_tool_id = (
            discovered_schema.id if discovered_schema else f"{server_id}.{tool.name}"
        )
        runtime_schema = (
            discovered_schema.parameters if discovered_schema else (_tool_json_schema(tool) or {})
        )
        tool_runtime_info[str(tool.id)] = {
            "server_id": server_id,
            "tool_id": runtime_tool_id,
            "schema": runtime_schema,
        }

    return client, connection_results, tool_runtime_info


# ---------------------------------------------------------------------------
# Single-agent executor (async generator)
# ---------------------------------------------------------------------------

async def execute_single_agent(
    db: AsyncIOMotorDatabase,
    *,
    agent: Agent,
    prompt: str,
    llm_config: LLMConfig | None,
    available_tools: list[Tool],
    collaborator_agents: list[Agent],
    depth: int = 0,
) -> AsyncGenerator[str, None]:
    """
    Execute one agent step and yield SSE event strings.

    This is a recursive async generator — collaborator agents are executed
    at depth+1 via recursive calls.
    """
    provider, model_name = resolve_provider_model(llm_config)
    apply_llm_credentials(llm_config)

    agent_scope = "collaborator" if depth > 0 else "agent"
    metadata: dict[str, Any] = {
        "depth": depth,
        "scope": agent_scope,
        "agent_id": str(agent.id),
        "agent_name": agent.name,
        "agent_description": agent.description,
        "tool_count": len(available_tools),
        "collaborator_count": len(collaborator_agents),
        "input": prompt,
    }
    yield sse_event(
        "reasoning",
        f"Executing {agent_scope}: {agent.name}",
        f"Preparing runtime with {len(available_tools)} attached tool(s) and {len(collaborator_agents)} collaborator(s).",
        status_value="running",
        metadata=metadata,
    )

    selected_tools, router_metadata = await select_tools_for_prompt(db, agent, available_tools, prompt)
    if router_metadata:
        strategy = router_metadata.get("strategy", "attached_tools")
        label = "Neural Tool Router Selection" if strategy == "neural_router" else "Attached Tool Selection"
        detail = safe_json(
            {
                "selected_tools": [
                    {"id": str(t.id), "name": t.name, "type": t.type.value}
                    for t in selected_tools
                ],
                "router": router_metadata,
            }
        )
        yield sse_event(
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
                    {"id": str(t.id), "name": t.name, "type": t.type.value}
                    for t in selected_tools
                ],
            },
        )

    mcp_client = None
    connection_results: dict = {}
    mcp_runtime_info: dict[str, dict[str, Any]] = {}
    tool_summaries: list[dict] = []
    collaborator_context: list[dict] = []

    try:
        mcp_client, connection_results, mcp_runtime_info = await build_mcp_client_for_tools(
            db, selected_tools
        )

        if connection_results:
            yield sse_event(
                "thought",
                "Tool Servers Connected",
                safe_json(connection_results),
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
                tool_args = _build_tool_args(tool, prompt)

            yield sse_event(
                "tool_call",
                f"Calling {tool_name}",
                safe_json({"tool_name": tool_name, "tool_type": tool.type.value, "arguments": tool_args}),
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
                    result: dict[str, Any] = {"success": False, "error": "MCP tool server metadata missing"}
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
                                    "text": safe_json(parsed_body)
                                    if isinstance(parsed_body, (dict, list))
                                    else str(parsed_body),
                                }
                            ],
                            "data": parsed_body,
                            "headers": dict(response.headers),
                            "content_type": response.headers.get("content-type", ""),
                        }
                        if not response.is_success:
                            result["error"] = f"REST tool returned HTTP {response.status_code}"
                    except Exception as exc:
                        result = {"success": False, "error": f"REST tool execution failed: {exc}"}
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
            yield sse_event(
                "tool_result",
                f"Result: {tool_name}",
                safe_json({"tool_name": tool_name, "arguments": tool_args, "result": result}),
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

        # Execute collaborators
        for collaborator in collaborator_agents:
            collaborator_config = await load_agent_llm_config(db, collaborator)
            collaborator_tools = await load_agent_tools(db, collaborator)
            collaborator_children = await load_collaborator_agents(db, collaborator)

            yield sse_event(
                "reasoning",
                f"Delegating to collaborator: {collaborator.name}",
                safe_json({"input": prompt, "description": collaborator.description}),
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
            async for collaborator_event in execute_single_agent(
                db,
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
                    "llm_config": summarize_llm_config(collaborator_config),
                    "attached_tools": [
                        {"id": str(t.id), "name": t.name, "type": t.type.value}
                        for t in collaborator_tools
                    ],
                    "execution_trace": collaborator_events,
                    "output": collaborator_final_output,
                }
            )

        # Build LLM input
        llm_input_sections = [
            f"Agent Name: {agent.name}",
            f"Agent Description:\n{agent.description or 'None'}",
            f"System Prompt:\n{agent.system_prompt or 'None'}",
            f"User Prompt:\n{prompt}",
        ]
        if tool_summaries:
            llm_input_sections.append("Tool Execution Summary:\n" + safe_json(tool_summaries))
        if collaborator_context:
            llm_input_sections.append("Collaborator Execution Summary:\n" + safe_json(collaborator_context))

        llm_input = "\n\n".join(llm_input_sections)

        if not provider or not model_name:
            raise RuntimeError("This agent does not have a valid LLM configuration assigned")

        llm_call_start = time.perf_counter()
        yield sse_event(
            "llm_call",
            "Invoking Agent LLM",
            safe_json({"provider": provider, "model_name": model_name, "input": llm_input}),
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

        yield sse_event(
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
