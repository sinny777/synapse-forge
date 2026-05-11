"""
Event types and data structures for agent execution.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class EventType(str, Enum):
    """Agent execution event types"""
    SCENARIO_START = "scenario_start"
    AGENT_ACTIVATED = "agent_activated"
    AGENT_REASONING = "agent_reasoning"
    TOOL_RETRIEVAL = "tool_retrieval"
    TOOL_EXECUTION = "tool_execution"
    AGENT_RESPONSE = "agent_response"
    SUPERVISOR_ROUTING = "supervisor_routing"
    SCENARIO_COMPLETE = "scenario_complete"
    ERROR = "error"


@dataclass
class ToolCall:
    """Represents a tool call with its arguments and result"""
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    execution_time: float
    success: bool
    error: Optional[str] = None


@dataclass
class AgentEvent:
    """Event emitted during agent execution"""
    type: EventType
    timestamp: float
    data: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "type": self.type.value,
            "timestamp": self.timestamp,
            "data": self.data
        }

# Made with Bob
