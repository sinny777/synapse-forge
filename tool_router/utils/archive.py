#!/usr/bin/env python3
"""
Archive Results Script

This script moves all created artifacts (data, models, logs) from the 3 phases
into a separate versioned folder under "results/". This allows running the 
phases again with a clean state and fresh input.
"""

import os
import shutil
from datetime import datetime
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    # Base directories
    base_dir = Path(".")
    data_dir = base_dir / "data"
    models_dir = base_dir / "models"
    logs_dir = base_dir / "logs"
    
    # Results directory with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = base_dir / "results" / f"run_{timestamp}"
    
    # Artifacts to move
    artifacts_to_move = [
        # Phase 1 Data
        data_dir / "synthetic_queries.jsonl",
        data_dir / "tool_cache.json",
        # Phase 2 Models and Indexes
        models_dir / "fine_tuned_tool_router",
        data_dir / "faiss_index.bin",
        data_dir / "faiss_index.json",
        data_dir / "bm25_index.pkl",
        # Logs
        logs_dir
    ]
    
    # Create results dir
    moved_anything = False
    
    for item in artifacts_to_move:
        if item.exists():
            if not moved_anything:
                results_dir.mkdir(parents=True, exist_ok=True)
                moved_anything = True
                
            dest = results_dir / item.name
            
            try:
                if item.is_dir():
                    shutil.copytree(item, dest)
                    shutil.rmtree(item)
                else:
                    shutil.copy2(item, dest)
                    item.unlink()
                logger.info(f"Moved: {item} -> {dest}")
            except Exception as e:
                logger.error(f"Failed to move {item}: {e}")
                
    if moved_anything:
        logger.info(f"All artifacts successfully archived to: {results_dir}")
        logger.info("You can now run each phase again with a clean slate.")
    else:
        logger.info("No artifacts found to archive.")

if __name__ == "__main__":
    main()
