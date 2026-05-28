"""
SynapseForge — Agent Scenario API Routes

Endpoints for the standalone agent orchestration scenarios:
  • GET  /api/agents/scenarios              — list available scenarios
  • GET  /api/agents/scenarios/{id}         — get scenario details
  • POST /api/agents/execute                — execute a scenario (SSE stream)

NOTE: These are the *standalone* agent scenarios (from tool_router/agent_service).
      The platform CRUD agents are in api/agents.py under /api/workspaces/{id}/agents.
"""

import json
import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("ntr.api.scenarios")

router = APIRouter(prefix="/api/agents", tags=["Agent Scenarios"])


class AgentExecuteRequest(BaseModel):
    scenario_id: str
    workspace_id: Optional[str] = None
    user_prompt: Optional[str] = None
    llm_config: Optional[Dict[str, Any]] = None
    runtime_config: Optional[Dict[str, Any]] = None


@router.get("/scenarios")
async def list_agent_scenarios():
    """Get list of available agent scenarios."""
    try:
        from tool_router.agent_service import agent_orchestrator
        scenarios = agent_orchestrator.list_scenarios()
        return {"status": "success", "scenarios": scenarios}
    except Exception as e:
        logger.error(f"Error listing agent scenarios: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scenarios/{scenario_id}")
async def get_agent_scenario(scenario_id: str):
    """Get detailed information about a specific agent scenario."""
    try:
        from tool_router.agent_service import agent_orchestrator
        scenario = agent_orchestrator.get_scenario(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
        return {"status": "success", "scenario": scenario}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/execute")
async def execute_agent_scenario(request: AgentExecuteRequest):
    """Execute an agent scenario and stream events (SSE)."""

    async def event_generator():
        try:
            from tool_router.agent_service import agent_orchestrator
            if request.user_prompt:
                prompt_event = {
                    "type": "thought",
                    "label": "User Prompt Received",
                    "detail": request.user_prompt,
                    "timestamp": time.time(),
                    "status": "success",
                }
                yield f"data: {json.dumps(prompt_event)}\n\n"

                reasoning_event = {
                    "type": "reasoning",
                    "label": "Preparing Agent Execution",
                    "detail": f"Executing selected agent {request.scenario_id}",
                    "timestamp": time.time(),
                    "status": "running",
                }
                yield f"data: {json.dumps(reasoning_event)}\n\n"

            async for event in agent_orchestrator.execute_scenario(
                scenario_id=request.scenario_id,
                workspace_id=request.workspace_id,
                llm_config=request.llm_config,
                runtime_config=request.runtime_config,
            ):
                event_dict = event.to_dict()
                event_type = event_dict.get("type")

                if event_type == "assistant_response":
                    event_dict["type"] = "assistant"
                    event_dict["label"] = event_dict.get("label") or "Agent Response"
                    event_dict["detail"] = event_dict.get("detail") or event_dict.get("message") or ""
                elif event_type == "thinking":
                    event_dict["type"] = "thought"
                    event_dict["label"] = event_dict.get("label") or "LLM Thought"
                elif event_type == "reasoning":
                    event_dict["type"] = "reasoning"
                    event_dict["label"] = event_dict.get("label") or "Reasoning"
                elif event_type == "tool_start":
                    event_dict["type"] = "tool_call"
                    event_dict["label"] = event_dict.get("label") or "Tool Call"
                elif event_type == "tool_end":
                    event_dict["type"] = "tool_result"
                    event_dict["label"] = event_dict.get("label") or "Tool Result"

                event_data = json.dumps(event_dict)
                yield f"data: {event_data}\n\n"

            complete_event = {
                "type": "complete",
                "label": "Agent Execution Complete",
                "detail": "Streaming finished",
                "timestamp": time.time(),
                "status": "success",
            }
            yield f"data: {json.dumps(complete_event)}\n\n"
        except Exception as e:
            logger.error(f"Error in agent execution stream: {e}")
            error_event = {
                "type": "error",
                "timestamp": time.time(),
                "data": {"error": str(e), "error_type": type(e).__name__},
            }
            yield f"data: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
