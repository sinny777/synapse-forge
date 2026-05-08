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
    queries_per_tool: int = 10
    teacher_model: str = "ollama/granite4.1:8b"

class TrainConfig(BaseModel):
    batch_size: int = 16
    num_epochs: int = 3
    learning_rate: float = 2e-5

class RunConfig(BaseModel):
    query: str
    enable_query_expansion: bool = True
    max_tool_calls: int = 10

def _update_global_config(config_data, phase):
    from tool_router.config import config
    if phase == "generate":
        config.data_generation.queries_per_tool = config_data.queries_per_tool
        config.llm.teacher_model = config_data.teacher_model
    elif phase == "train":
        config.training.batch_size = config_data.batch_size
        config.training.num_epochs = config_data.num_epochs
        config.training.learning_rate = config_data.learning_rate
    elif phase == "run":
        config.runtime.enable_query_expansion = config_data.enable_query_expansion
        config.runtime.max_tool_calls = config_data.max_tool_calls

@app.post("/api/generate")
async def generate_phase(config_data: GenerateConfig):
    try:
        _update_global_config(config_data, "generate")
        from tool_router.generator import main as phase1_main
        # Run generation phase directly
        await phase1_main()
        return {"status": "success", "message": "Generation phase completed."}
    except Exception as e:
        logger.error(f"Generate phase failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/train")
def train_phase(config_data: TrainConfig):
    try:
        _update_global_config(config_data, "train")
        from tool_router.trainer import main as phase2_main
        # Run training phase directly
        phase2_main()
        return {"status": "success", "message": "Training phase completed."}
    except Exception as e:
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
