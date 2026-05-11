"""
MCP Server Manager for starting and stopping FastMCP servers.
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class MCPServerManager:
    """Manages FastMCP server lifecycle for agent scenarios"""
    
    def __init__(self, examples_dir: Path):
        """
        Initialize MCP server manager.
        
        Args:
            examples_dir: Path to examples directory containing scenario folders
        """
        self.examples_dir = examples_dir
        self.process: Optional[subprocess.Popen] = None
        self.scenario_id: Optional[str] = None
    
    async def start_server(self, scenario_id: str) -> bool:
        """
        Start MCP server for a specific scenario.
        
        Args:
            scenario_id: ID of the scenario (e.g., 'langgraph_banking', 'beeai_mediclaim')
        
        Returns:
            True if server started successfully, False otherwise
        """
        if self.process is not None:
            logger.warning(f"MCP server already running for scenario: {self.scenario_id}")
            if self.scenario_id == scenario_id:
                return True
            else:
                logger.info("Stopping existing server to start new one")
                await self.stop_server()
        
        # Map scenario IDs to example directories
        scenario_map = {
            "langgraph_banking": "langgraph_UHNW_banking",
            "mediclaim_processing": "beeai_mediclaim_processing",
            "beeai_mediclaim": "beeai_mediclaim_processing"  # Legacy support
        }
        
        example_dir = scenario_map.get(scenario_id)
        if not example_dir:
            logger.error(f"Unknown scenario ID: {scenario_id}")
            return False
        
        server_path = self.examples_dir / example_dir / "mock_fastmcp_server.py"
        
        if not server_path.exists():
            logger.error(f"MCP server script not found: {server_path}")
            return False
        
        try:
            logger.info(f"Starting FastMCP server for {scenario_id}...")
            
            # Start server in background
            self.process = subprocess.Popen(
                [sys.executable, str(server_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Wait for server to initialize
            time.sleep(3)
            
            # Check if process is still running
            if self.process.poll() is not None:
                stdout, stderr = self.process.communicate()
                logger.error(f"MCP server failed to start:\n{stderr}")
                self.process = None
                return False
            
            self.scenario_id = scenario_id
            logger.info(f"✓ FastMCP server started for {scenario_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error starting MCP server: {e}")
            self.process = None
            return False
    
    async def stop_server(self):
        """Stop the running MCP server"""
        if self.process:
            try:
                logger.info(f"Stopping FastMCP server for {self.scenario_id}...")
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.info("✓ MCP server stopped")
            except subprocess.TimeoutExpired:
                logger.warning("MCP server did not stop gracefully, killing...")
                self.process.kill()
                self.process.wait()
            except Exception as e:
                logger.error(f"Error stopping MCP server: {e}")
            finally:
                self.process = None
                self.scenario_id = None
    
    def is_running(self) -> bool:
        """Check if MCP server is currently running"""
        return self.process is not None and self.process.poll() is None

# Made with Bob
