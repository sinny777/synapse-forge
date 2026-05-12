import asyncio
import logging
import time
from typing import Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)
print(f"[Main] Loaded environment from: {env_path}")

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("fastapi_app")

app = FastAPI(title="Neural Tool Router API")

# Add CORS middleware for Angular dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for configuration
class GenerateConfig(BaseModel):
    queries_per_tool: Optional[int] = 10
    teacher_model: Optional[str] = "ollama/granite4.1:8b"
    llm: Optional[dict] = None
    embedding: Optional[dict] = None
    vector_store: Optional[dict] = None
    mcp: Optional[dict] = None
    data_generation: Optional[dict] = None

class TrainConfig(BaseModel):
    batch_size: int = 16
    num_epochs: int = 3
    learning_rate: float = 2e-5

class RunConfig(BaseModel):
    query: str
    enable_query_expansion: bool = True
    max_tool_calls: int = 10
    model_path: Optional[str] = None

class EvaluateConfig(BaseModel):
    query: str
    top_k: int = 5
    model_path: Optional[str] = None

def _apply_dict_to_obj(config_dict, obj):
    from pathlib import Path
    if not config_dict: return
    for k, v in config_dict.items():
        if hasattr(obj, k):
            orig_val = getattr(obj, k)
            if isinstance(orig_val, Path) and isinstance(v, str):
                setattr(obj, k, Path(v))
            else:
                setattr(obj, k, v)

def _update_global_config(config_data, phase):
    from tool_router.config import config
    if phase == "generate":
        if config_data.queries_per_tool:
            config.data_generation.queries_per_tool = config_data.queries_per_tool
        if config_data.teacher_model:
            config.llm.teacher_model = config_data.teacher_model
            
        _apply_dict_to_obj(config_data.llm, config.llm)
        _apply_dict_to_obj(config_data.embedding, config.embedding)
        _apply_dict_to_obj(config_data.vector_store, config.vector_store)
        _apply_dict_to_obj(config_data.data_generation, config.data_generation)
        
        if config_data.mcp:
            _apply_dict_to_obj({k: v for k, v in config_data.mcp.items() if k != 'servers'}, config.mcp)
            if 'servers' in config_data.mcp:
                config.mcp.servers = config_data.mcp['servers']
    elif phase == "train":
        config.training.batch_size = config_data.batch_size
        config.training.num_epochs = config_data.num_epochs
        config.training.learning_rate = config_data.learning_rate
    elif phase == "run":
        config.runtime.enable_query_expansion = config_data.enable_query_expansion
        config.runtime.max_tool_calls = config_data.max_tool_calls

@app.get("/api/status")
async def get_status():
    from tool_router.status_tracker import get_status
    return get_status()

@app.post("/api/generate")
async def generate_phase(config_data: GenerateConfig):
    from tool_router.status_tracker import update_status, reset_status
    reset_status()
    update_status(phase="generate", status="running", progress=0.0, message="Initializing generation phase...")
    try:
        _update_global_config(config_data, "generate")
        from tool_router.generator import main as phase1_main
        # Run generation phase directly
        await phase1_main()
        update_status(status="completed", progress=1.0, message="Generation phase completed successfully.")
        return {"status": "success", "message": "Generation phase completed."}
    except Exception as e:
        update_status(status="error", message=f"Generation failed: {str(e)}")
        logger.error(f"Generate phase failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/train")
def train_phase(config_data: TrainConfig):
    from tool_router.status_tracker import update_status, reset_status
    reset_status()
    update_status(phase="train", status="running", progress=0.0, message="Initializing training phase...")
    try:
        _update_global_config(config_data, "train")
        from tool_router.trainer import main as phase2_main
        # Run training phase directly
        phase2_main()
        update_status(status="completed", progress=1.0, message="Training phase completed successfully.")
        return {"status": "success", "message": "Training phase completed."}
    except Exception as e:
        update_status(status="error", message=f"Training failed: {str(e)}")
        logger.error(f"Train phase failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/run")
async def run_phase(config_data: RunConfig):
    try:
        _update_global_config(config_data, "run")
        if config_data.model_path:
            from tool_router.config import config
            from pathlib import Path
            config.embedding.fine_tuned_model_dir = Path(config_data.model_path)
            
        from tool_router.runtime import ToolRouter
        from fastapi.responses import StreamingResponse
        
        async def event_generator():
            router = ToolRouter()
            try:
                await router.initialize()
                async for event in router.process_query_stream(config_data.query):
                    yield event
            except Exception as e:
                logger.error(f"Error in stream: {e}")
                yield json.dumps({"event": "error", "data": {"message": str(e)}}) + "\n"
            finally:
                await router.close()
                
        return StreamingResponse(event_generator(), media_type="application/x-ndjson")
            
    except Exception as e:
        logger.error(f"Run phase failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/evaluate")
async def evaluate_phase(config_data: EvaluateConfig):
    import time
    from tool_router.runtime import SemanticRouter
    from tool_router.config import config
    from tool_router.mcp_client import MCPClient
    from sentence_transformers import SentenceTransformer
    
    try:
        t0 = time.time()
        
        # Load embedding model
        model_dir = config_data.model_path if config_data.model_path else str(config.embedding.fine_tuned_model_dir)
        model = SentenceTransformer(
            model_dir,
            device=config.embedding.device
        )
        
        # Initialize semantic router
        semantic_router = SemanticRouter(model, config.vector_store)
        
        if config.vector_store.store_type == "faiss":
            semantic_router.load_faiss_index()
        elif config.vector_store.store_type == "chromadb":
            semantic_router.load_chromadb_collection()
            
        try:
            semantic_router.load_bm25_index()
        except FileNotFoundError:
            pass
            
        retrieved_tools = semantic_router.retrieve_tools(
            config_data.query,
            top_k=config_data.top_k,
            use_hybrid=False,
            apply_threshold=False
        )
        
        # Load tool cache to get metadata
        mcp_client = MCPClient(config.mcp)
        mcp_client.load_tool_cache(config.mcp.tool_cache_path)
        
        # Enrich retrieved tools with complete metadata
        enriched_tools = []
        for tid, score in retrieved_tools:
            tool_schema = mcp_client.tools.get(tid)
            if tool_schema:
                enriched_tools.append({
                    "id": tid,
                    "score": score,
                    "name": tool_schema.name,
                    "description": tool_schema.description,
                    "server_name": tool_schema.server_name,
                    "parameters": tool_schema.parameters,
                    "input_schema": tool_schema.raw_schema.get("inputSchema", {}),
                    "output_format": tool_schema.raw_schema.get("outputFormat", "Tool execution result")
                })
            else:
                enriched_tools.append({
                    "id": tid,
                    "score": score,
                    "name": tid.split('.')[-1] if '.' in tid else tid,
                    "description": "Tool metadata not available",
                    "server_name": "unknown",
                    "parameters": {},
                    "input_schema": {},
                    "output_format": "Tool execution result"
                })
        
        total_time = time.time() - t0
        
        return {
            "status": "success",
            "message": "Evaluation completed.",
            "data": {
                "query": config_data.query,
                "retrieved_tools": enriched_tools,
                "time_taken": total_time
            }
        }
    except Exception as e:
        logger.error(f"Evaluate phase failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class SyntheticDataUpdate(BaseModel):
    data: list

@app.get("/api/data/synthetic")
async def get_synthetic_data():
    from tool_router.config import config
    import json
    import os
    
    path = config.data_generation.output_path
    if not os.path.exists(path):
        return {"data": []}
        
    try:
        data = []
        with open(path, 'r') as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
        return {"data": data}
    except Exception as e:
        logger.error(f"Error reading synthetic data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/data/tools")
async def get_cached_tools():
    from tool_router.config import config
    import json
    import os
    
    path = config.mcp.tool_cache_path
    if not os.path.exists(path):
        return {"tools": []}
        
    try:
        with open(path, 'r') as f:
            data = json.load(f)
            # data["tools"] is a list of ToolSchema dicts, we just need their 'id's and maybe names
            tools = [{"id": t["id"], "name": t.get("name", t["id"])} for t in data.get("tools", [])]
            return {"tools": tools}
    except Exception as e:
        logger.error(f"Error reading tool cache: {e}")
        return {"tools": []}
@app.get("/api/env/llm-credentials")
async def get_llm_credentials():
    """
    Fetch LLM credentials from environment variables for all supported providers.
    Returns actual credentials (not masked) so they can be used in the UI.
    """
    import os
    
    credentials = {
        # Model configurations
        "teacher_model": os.getenv("TEACHER_MODEL", ""),
        "expansion_model": os.getenv("EXPANSION_MODEL", ""),
        "heavy_model": os.getenv("HEAVY_MODEL", ""),
        
        # Ollama
        "ollama_api_base": os.getenv("OLLAMA_API_BASE", ""),
        
        # OpenAI
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "openai_api_base": os.getenv("OPENAI_API_BASE", ""),
        "openai_organization": os.getenv("OPENAI_ORGANIZATION", ""),
        
        # Anthropic
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "anthropic_api_base": os.getenv("ANTHROPIC_API_BASE", ""),
        
        # Google
        "google_api_key": os.getenv("GOOGLE_API_KEY", ""),
        "google_application_credentials": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
        "vertexai_project": os.getenv("VERTEXAI_PROJECT", ""),
        "vertexai_location": os.getenv("VERTEXAI_LOCATION", ""),
        
        # IBM Watsonx.ai
        "watsonx_api_key": os.getenv("WATSONX_API_KEY", ""),
        "watsonx_project_id": os.getenv("WATSONX_PROJECT_ID", ""),
        "watsonx_url": os.getenv("WATSONX_URL", ""),
        "watsonx_region": os.getenv("WATSONX_REGION", ""),
        
        # Groq
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        
        # Azure OpenAI
        "azure_api_key": os.getenv("AZURE_API_KEY", ""),
        "azure_api_base": os.getenv("AZURE_API_BASE", ""),
        "azure_api_version": os.getenv("AZURE_API_VERSION", ""),
        "azure_ad_token": os.getenv("AZURE_AD_TOKEN", ""),
        
        # Cohere
        "cohere_api_key": os.getenv("COHERE_API_KEY", ""),
        
        # Hugging Face
        "huggingface_api_key": os.getenv("HUGGINGFACE_API_KEY", ""),
        "huggingface_api_base": os.getenv("HUGGINGFACE_API_BASE", ""),
        
        # Replicate
        "replicate_api_key": os.getenv("REPLICATE_API_KEY", ""),
    }
    
    return credentials


@app.post("/api/data/synthetic")
async def save_synthetic_data(update: SyntheticDataUpdate):
    from tool_router.config import config
    import json
    
    path = config.data_generation.output_path
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            for item in update.data:
                f.write(json.dumps(item) + '\n')
        return {"status": "success", "message": "Synthetic data saved."}
    except Exception as e:
        logger.error(f"Error saving synthetic data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ArchiveModelRequest(BaseModel):
    name: str
    version: str
    source_dir: str

@app.get("/api/models")
async def list_models():
    from tool_router.config import config
    models_dir = config.models_dir
    models = []
    if models_dir.exists():
        for item in models_dir.iterdir():
            if item.is_dir():
                models.append({"name": item.name, "path": str(item)})
    return {"status": "success", "models": models}

@app.post("/api/models/archive")
async def archive_model(req: ArchiveModelRequest):
    from tool_router.config import config
    import shutil
    from pathlib import Path
    
    models_dir = config.models_dir
    source_path = Path(req.source_dir)
    if not source_path.is_absolute():
        source_path = config.project_root / req.source_dir
    
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source model directory not found")
        
    target_name = f"{req.name}_v{req.version}"
    target_path = models_dir / target_name
    
    try:
        if target_path.exists():
            shutil.rmtree(target_path)
        shutil.copytree(source_path, target_path)
        return {"status": "success", "message": f"Model archived as {target_name}", "model_name": target_name}
    except Exception as e:
        logger.error(f"Error archiving model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/models/{model_name}")
async def delete_model(model_name: str):
    from tool_router.config import config
    import shutil
    
    models_dir = config.models_dir
    target_path = models_dir / model_name
    
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Model not found")
        
    try:
        shutil.rmtree(target_path)
        return {"status": "success", "message": f"Model {model_name} deleted"}
    except Exception as e:
        logger.error(f"Error deleting model: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class ArchiveDatasetRequest(BaseModel):
    name: str
    version: str
    source_file: str

class LoadDatasetRequest(BaseModel):
    dataset_path: str

@app.get("/api/datasets")
async def list_datasets():
    """List all archived datasets in the datasets directory."""
    from tool_router.config import config
    datasets_dir = config.datasets_dir
    datasets = []
    if datasets_dir.exists():
        for item in datasets_dir.iterdir():
            if item.is_file() and item.suffix == '.jsonl':
                # Parse name and version from filename (e.g., banking-queries_v1.0.jsonl)
                name_parts = item.stem.split('_v')
                if len(name_parts) == 2:
                    name, version = name_parts[0], name_parts[1]
                else:
                    name, version = item.stem, "1.0"
                datasets.append({
                    "name": name,
                    "version": version,
                    "path": str(item)
                })
    return {"status": "success", "datasets": datasets}

@app.post("/api/datasets/archive")
async def archive_dataset(req: ArchiveDatasetRequest):
    """Archive a dataset by copying it to the datasets directory with versioned name."""
    from tool_router.config import config
    import shutil
    from pathlib import Path
    
    datasets_dir = config.datasets_dir
    datasets_dir.mkdir(parents=True, exist_ok=True)
    
    source_path = Path(req.source_file)
    if not source_path.is_absolute():
        source_path = config.project_root / req.source_file
    
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="Source dataset file not found")
        
    target_name = f"{req.name}_v{req.version}.jsonl"
    target_path = datasets_dir / target_name
    
    try:
        shutil.copy2(source_path, target_path)
        return {
            "status": "success",
            "message": f"Dataset archived as {target_name}",
            "dataset_name": req.name,
            "dataset_path": str(target_path)
        }
    except Exception as e:
        logger.error(f"Error archiving dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/datasets/load")
async def load_dataset(req: LoadDatasetRequest):
    """Load a specific dataset file."""
    from pathlib import Path
    import json
    
    path = Path(req.dataset_path)
    if not path.is_absolute():
        from tool_router.config import config
        path = config.project_root / req.dataset_path
    
    if not path.exists():
        raise HTTPException(status_code=404, detail="Dataset file not found")
        
    try:
        data = []
        with open(path, 'r') as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
        return {"status": "success", "data": data}
    except Exception as e:
        logger.error(f"Error loading dataset: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/datasets/{dataset_name}")
async def delete_dataset(dataset_name: str):
    """Delete an archived dataset."""
    from tool_router.config import config
    import os
    
    datasets_dir = config.datasets_dir
    
    # Find the dataset file (it might have version suffix)
    deleted = False
    for item in datasets_dir.iterdir():
        if item.is_file() and item.stem.startswith(dataset_name):
            try:
                os.remove(item)
                deleted = True
            except Exception as e:
                logger.error(f"Error deleting dataset {item}: {e}")
                raise HTTPException(status_code=500, detail=str(e))
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Dataset not found")
        
    return {"status": "success", "message": f"Dataset {dataset_name} deleted"}

# ============================================================================
# Agent Orchestration Endpoints
# ============================================================================

class AgentExecuteRequest(BaseModel):
    scenario_id: str
    llm_config: Optional[Dict[str, Any]] = None
    runtime_config: Optional[Dict[str, Any]] = None

@app.get("/api/agents/scenarios")
async def list_agent_scenarios():
    """
    Get list of available agent scenarios.
    
    Returns:
        List of scenario metadata including agents, tools, and benefits
    """
    try:
        from tool_router.agent_service import agent_orchestrator
        scenarios = agent_orchestrator.list_scenarios()
        return {
            "status": "success",
            "scenarios": scenarios
        }
    except Exception as e:
        logger.error(f"Error listing agent scenarios: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agents/scenarios/{scenario_id}")
async def get_agent_scenario(scenario_id: str):
    """
    Get detailed information about a specific agent scenario.
    
    Args:
        scenario_id: ID of the scenario
        
    Returns:
        Detailed scenario information
    """
    try:
        from tool_router.agent_service import agent_orchestrator
        scenario = agent_orchestrator.get_scenario(scenario_id)
        
        if not scenario:
            raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")
        
        return {
            "status": "success",
            "scenario": scenario
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent scenario: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/agents/execute")
async def execute_agent_scenario(request: AgentExecuteRequest):
    """
    Execute an agent scenario and stream events.
    
    This endpoint uses Server-Sent Events (SSE) to stream real-time
    execution events including agent activations, tool retrievals,
    tool executions, and agent responses.
    
    Args:
        request: Agent execution request with scenario_id and configs
        
    Returns:
        StreamingResponse with SSE events
    """
    from fastapi.responses import StreamingResponse
    import json
    
    async def event_generator():
        """Generate SSE events from agent execution"""
        try:
            from tool_router.agent_service import agent_orchestrator
            
            async for event in agent_orchestrator.execute_scenario(
                scenario_id=request.scenario_id,
                llm_config=request.llm_config,
                runtime_config=request.runtime_config
            ):
                # Format as SSE event
                event_data = json.dumps(event.to_dict())
                yield f"data: {event_data}\n\n"
                
        except Exception as e:
            logger.error(f"Error in agent execution stream: {e}")
            error_event = {
                "type": "error",
                "timestamp": time.time(),
                "data": {
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            }
            yield f"data: {json.dumps(error_event)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
