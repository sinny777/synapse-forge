import asyncio
import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
        
        total_time = time.time() - t0
        
        return {
            "status": "success",
            "message": "Evaluation completed.",
            "data": {
                "query": config_data.query,
                "retrieved_tools": [{"id": tid, "score": score} for tid, score in retrieved_tools],
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
