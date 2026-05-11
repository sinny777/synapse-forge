"""
Abstract base class for agent executors.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, Optional
from pathlib import Path
import logging

from ..common.events import AgentEvent
from ..common.models import AgentScenario
from ..common.mcp_manager import MCPServerManager

logger = logging.getLogger(__name__)


class BaseAgentExecutor(ABC):
    """
    Abstract base class for agent executors.
    
    Each framework (BeeAI, LangGraph) implements this interface to provide
    real agent execution with proper event streaming.
    """
    
    def __init__(self, scenario: AgentScenario, examples_dir: Path):
        """
        Initialize the executor.
        
        Args:
            scenario: The agent scenario to execute
            examples_dir: Path to examples directory
        """
        self.scenario = scenario
        self.examples_dir = examples_dir
        self.mcp_manager: Optional[MCPServerManager] = None
        self.initialized = False
    
    @abstractmethod
    async def initialize(self):
        """
        Initialize executor resources (MCP server, tool router, etc.).
        
        This method should:
        1. Start MCP server for the scenario
        2. Initialize tool router
        3. Set up any framework-specific components
        """
        pass
    
    @abstractmethod
    async def execute(
        self,
        user_query: str,
        llm_config: Optional[Dict[str, Any]] = None,
        runtime_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[AgentEvent, None]:
        """
        Execute the agent scenario and stream events.
        
        Args:
            user_query: The user's query to process
            llm_config: LLM configuration (model name, temperature, etc.)
            runtime_config: Runtime configuration options
        
        Yields:
            AgentEvent objects representing execution progress
        """
        pass
    
    @abstractmethod
    async def cleanup(self):
        """
        Cleanup executor resources.
        
        This method should:
        1. Stop MCP server
        2. Close tool router connections
        3. Clean up any framework-specific resources
        """
        pass
    
    async def _start_mcp_server(self) -> bool:
        """
        Start MCP server for this scenario.
        
        Returns:
            True if server started successfully
        """
        if not self.mcp_manager:
            self.mcp_manager = MCPServerManager(self.examples_dir)
        
        return await self.mcp_manager.start_server(self.scenario.id)
    
    async def _stop_mcp_server(self):
        """Stop MCP server if running"""
        if self.mcp_manager:
            await self.mcp_manager.stop_server()

# Made with Bob
