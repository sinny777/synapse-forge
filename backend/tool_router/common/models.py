"""
Data models for agent scenarios and configurations.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class AgentFramework(str, Enum):
    """Supported agent frameworks"""
    BEEAI = "beeai"
    LANGGRAPH = "langgraph"


@dataclass
class AgentInfo:
    """Information about an agent in the scenario"""
    name: str
    role: str
    description: str
    tools_count: int


@dataclass
class AgentScenario:
    """Defines an agent scenario configuration"""
    id: str
    name: str
    description: str
    framework: AgentFramework
    agents: List[AgentInfo]
    example_query: str
    estimated_duration: int  # seconds
    total_tools: int
    use_case: str
    benefits: List[str]

# Made with Bob
