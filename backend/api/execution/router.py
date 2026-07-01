"""
SynapseForge — Execution domain: route handlers.

Routes:
  POST /api/router/predict                          — semantic tool retrieval
  POST /api/orchestrator/{orchestration_id}/execute — SSE streaming execution
"""

import json
import uuid
import logging

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from api.auth import get_current_user
from api.common.utils import sse_event
from db.engine import get_db, normalize_mongo_document
from db.models import Orchestration, Tool, Workspace, Agent
from db.schemas import RouterPredictRequest
from services.router_service import RouterService

from .helpers import _get_redis_or_none
from .schemas import ExecuteRequest

logger = logging.getLogger("ntr.api.execution")

# ---------------------------------------------------------------------------
# Router instances
# ---------------------------------------------------------------------------

router_predict = APIRouter(prefix="/api/router", tags=["Neural Router"])
orchestrator_router = APIRouter(prefix="/api/orchestrator", tags=["Orchestrator"])


# ---------------------------------------------------------------------------
# POST /api/router/predict
# ---------------------------------------------------------------------------

@router_predict.post("/predict")
async def predict(
    body: RouterPredictRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """
    Semantic tool retrieval for a user prompt.

    Accepts a natural-language prompt and workspace_id, and returns
    the top-K most relevant tools from the workspace's current embedding index.
    """
    redis = await _get_redis_or_none()

    try:
        result = await RouterService.predict(
            db=db,
            workspace_id=body.workspace_id,
            user_prompt=body.user_prompt,
            top_k=body.top_k,
            redis=redis,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error("Router predict failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal router error")

    return result


# ---------------------------------------------------------------------------
# POST /api/orchestrator/{orchestration_id}/execute
# ---------------------------------------------------------------------------

@orchestrator_router.post("/{orchestration_id}/execute")
async def execute_orchestration(
    orchestration_id: uuid.UUID,
    body: ExecuteRequest,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    """
    Execute an orchestration graph with real-time SSE trace events.

    The response is a Server-Sent Event stream. Each event is a JSON object
    with fields: type, label, detail, timestamp, latency_ms, status.

    Event types:
      - router: SynapseForge semantic search results
      - llm_call: LLM invocation with bound tools
      - tool_call: Tool function execution
      - tool_result: Result from tool execution
      - assistant: Final assistant response
      - error: Error during execution
      - complete: Execution finished
    """
    # 1. Load orchestration
    logger.info(f"Loading orchestration: {orchestration_id}")
    orch_doc = await db.orchestrations.find_one({"_id": str(orchestration_id)})
    orch_data = normalize_mongo_document(orch_doc)
    orch = Orchestration(**orch_data) if orch_data else None
    if orch is None:
        logger.error(f"Orchestration not found: {orchestration_id}")
        raise HTTPException(status_code=404, detail="Orchestration not found")
    logger.info(f"Orchestration loaded: {orch.name}")

    # 2. Load workspace
    logger.info(f"Loading workspace: {orch.workspace_id}")
    ws_doc = await db.workspaces.find_one({"_id": orch.workspace_id})
    ws_data = normalize_mongo_document(ws_doc)
    ws = Workspace(**ws_data) if ws_data else None
    if ws is None:
        logger.error(f"Workspace not found: {orch.workspace_id}")
        raise HTTPException(status_code=404, detail="Workspace not found")
    logger.info(f"Workspace loaded: {ws.name}")

    # 3. Load the primary agent from orchestration config
    # Support both 'agent_id' and 'supervisor_agent_id' for different orchestration patterns
    agent_id = None
    if orch.config:
        agent_id = orch.config.get("agent_id") or orch.config.get("supervisor_agent_id")

    if not agent_id:
        logger.error(f"No agent_id found in orchestration config: {orch.config}")
        raise HTTPException(
            status_code=400,
            detail="Orchestration must have an 'agent_id' or 'supervisor_agent_id' in config"
        )

    logger.info(f"Loading agent: {agent_id} from workspace: {ws.id}")
    agent_doc = await db.agents.find_one({"_id": agent_id, "workspace_id": str(ws.id)})
    logger.info(f"Agent doc found: {agent_doc is not None}")
    agent_data = normalize_mongo_document(agent_doc)
    agent = Agent(**agent_data) if agent_data else None
    if agent is None:
        logger.error(f"Agent {agent_id} not found in workspace {ws.id}")
        raise HTTPException(
            status_code=404,
            detail=f"Agent {agent_id} not found in workspace"
        )
    logger.info(f"Agent loaded: {agent.name}")

    # 4. Setup session management
    session_id = body.thread_id or str(uuid.uuid4())

    from db.redis_pool import get_redis_pool
    import redis.asyncio as aioredis

    redis_pool = get_redis_pool()
    redis_client = aioredis.Redis(connection_pool=redis_pool)

    async def event_stream():
        """Generate SSE trace events using real agent execution."""
        try:
            from services.conversation_service import ConversationService
            from services.langgraph_dynamic_agent_executor import DynamicLangGraphAgentExecutor

            # Initialize conversation service
            conv_service = ConversationService(redis_client)
            await conv_service.get_or_create_session(session_id, uuid.UUID(str(agent.id)))

            # Get conversation history
            history = await conv_service.get_history(
                session_id=session_id,
                limit=agent.memory_window or 10,
                memory_type=agent.memory_type or "buffer",
            )

            # Emit initial event
            yield sse_event(
                "thought",
                "User Prompt Received",
                body.user_prompt,
                status_value="success",
            )

            # Execute agent with DynamicLangGraphAgentExecutor
            executor = DynamicLangGraphAgentExecutor(db)
            assistant_response = ""

            async for event in executor.execute_agent(
                agent=agent,
                user_prompt=body.user_prompt,
                conversation_history=history,
                depth=0,
                router_top_k_override=body.top_k,
            ):
                yield event

                # Track assistant response for conversation history
                try:
                    event_data = json.loads(event.replace("data: ", "").strip())
                    if event_data.get("type") == "assistant":
                        assistant_response = event_data.get("detail", "")
                except Exception:
                    pass

            # Save conversation to history
            await conv_service.add_message(
                session_id=session_id,
                role="user",
                content=body.user_prompt,
            )

            if assistant_response:
                await conv_service.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_response,
                )

            # Emit completion event
            yield sse_event(
                "complete",
                "Execution Complete",
                f"Session: {session_id}",
                status_value="success",
            )

        except Exception as e:
            logger.error("Execution error: %s", e, exc_info=True)
            yield sse_event("error", "Execution Failed", str(e), status_value="error")
            yield sse_event("complete", "Execution Complete", "Completed with errors", status_value="error")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
