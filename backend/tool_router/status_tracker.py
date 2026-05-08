from pydantic import BaseModel
from typing import Dict, Any, Optional

class ProgressStatus(BaseModel):
    phase: str = ""
    status: str = "idle" # idle, running, completed, error
    progress: float = 0.0 # 0.0 to 1.0
    message: str = ""
    details: Dict[str, Any] = {}

global_status = ProgressStatus()

def update_status(phase: str = None, status: str = None, progress: float = None, message: str = None, details: Dict[str, Any] = None):
    if phase is not None: global_status.phase = phase
    if status is not None: global_status.status = status
    if progress is not None: global_status.progress = max(0.0, min(1.0, progress))
    if message is not None: global_status.message = message
    if details is not None: global_status.details.update(details)

def get_status() -> ProgressStatus:
    return global_status

def reset_status():
    global global_status
    global_status = ProgressStatus()
