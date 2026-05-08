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
        from tool_router.runtime import ToolRouter
        
        # Initialize and process single query rather than running interactive loop
        router = ToolRouter()
        await router.initialize()
        
        try:
            result = await router.process_query(config_data.query)
            return {
                "status": "success", 
                "message": "Run phase completed.", 
                "data": result
            }
        finally:
            await router.close()
            
    except Exception as e:
        logger.error(f"Run phase failed: {e}")
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
