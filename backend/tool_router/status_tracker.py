from pydantic import BaseModel
from typing import Dict, Any, Optional, List, Callable
import asyncio
import json

class ProgressStatus(BaseModel):
    phase: str = ""
    status: str = "idle" # idle, running, completed, error
    progress: float = 0.0 # 0.0 to 1.0
    message: str = ""
    details: Dict[str, Any] = {}

global_status = ProgressStatus()
status_listeners: List[Callable] = []

def add_listener(callback: Callable):
    """Add a callback to be notified of status updates."""
    status_listeners.append(callback)

def remove_listener(callback: Callable):
    """Remove a status update callback."""
    if callback in status_listeners:
        status_listeners.remove(callback)

def update_status(phase: Optional[str] = None, status: Optional[str] = None, progress: Optional[float] = None, message: Optional[str] = None, details: Optional[Dict[str, Any]] = None):
    if phase is not None: global_status.phase = phase
    if status is not None: global_status.status = status
    if progress is not None: global_status.progress = max(0.0, min(1.0, progress))
    if message is not None: global_status.message = message
    if details is not None: global_status.details.update(details)
    
    # Notify all listeners
    for listener in status_listeners:
        try:
            listener(global_status.model_dump())
        except Exception as e:
            print(f"Error notifying listener: {e}")

def get_status() -> ProgressStatus:
    return global_status

def reset_status():
    global global_status
    global_status = ProgressStatus()
