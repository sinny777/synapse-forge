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
            async for event in agent_orchestrator.execute_scenario(
                scenario_id=request.scenario_id,
                workspace_id=request.workspace_id,
                llm_config=request.llm_config,
                runtime_config=request.runtime_config,
            ):
                event_data = json.dumps(event.to_dict())
                yield f"data: {event_data}\n\n"
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
