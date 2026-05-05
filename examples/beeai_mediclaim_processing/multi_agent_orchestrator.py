"""
IBM BeeAI Multi-Agent Mediclaim Processing Orchestrator

This script demonstrates how to use NeuralToolRouter to dynamically inject
different subsets of FastMCP tools into multiple specialized IBM BeeAgents
working together to process a medical insurance claim.
"""

import asyncio
import sys
import os
import subprocess
import time
from pathlib import Path
from typing import List, Dict, Any, Tuple

# Add parent directory to path to import NeuralToolRouter
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sentence_transformers import SentenceTransformer
from bee_agent_framework.agents.bee import BeeAgent
from bee_agent_framework.memory import TokenMemory
from bee_agent_framework.llms import ChatLLM
from litellm import completion

from config import config
from mcp_client import MCPClient, ToolSchema
from phase3_runtime import SemanticRouter


class ToolRouterForBeeAI:
    """
    Adapter that wraps NeuralToolRouter for use with IBM BeeAI agents.
    Provides Top-K tool retrieval for dynamic tool injection.
    """
    
    def __init__(self):
        """Initialize the tool router."""
        self.embedding_model: SentenceTransformer = None
        self.semantic_router: SemanticRouter = None
        self.mcp_client: MCPClient = None
        self.all_tools: Dict[str, ToolSchema] = {}
    
    async def initialize(self):
        """Initialize all components."""
        print("Initializing NeuralToolRouter...")
        
        # Load embedding model
        print("  Loading fine-tuned embedding model...")
        self.embedding_model = SentenceTransformer(
            str(config.embedding.fine_tuned_model_dir),
            device=config.embedding.device
        )
        
        # Initialize semantic router
        print("  Initializing semantic router...")
        self.semantic_router = SemanticRouter(self.embedding_model, config.vector_store)
        
        if config.vector_store.store_type == "faiss":
            self.semantic_router.load_faiss_index()
        
        # Load BM25 for hybrid retrieval
        try:
            self.semantic_router.load_bm25_index()
            print("  ✓ Hybrid retrieval enabled (Dense + BM25)")
        except FileNotFoundError:
            print("  ⚠ BM25 index not found, using dense-only retrieval")
        
        # Connect to MCP server
        print("  Connecting to FastMCP server...")
        self.mcp_client = MCPClient(config.mcp)
        await self.mcp_client.connect_all()
        tools = await self.mcp_client.list_tools()
        
        # Store tools
        for tool in tools:
            self.all_tools[tool.id] = tool
        
        print(f"  ✓ Connected to MCP server with {len(self.all_tools)} tools")
        print("✓ NeuralToolRouter initialized\n")
    
    async def get_top_k_tools(self, query: str, k: int = 2) -> List[ToolSchema]:
        """
        Retrieve Top-K most relevant tools for a query.
        
        Args:
            query: User query or sub-task description
            k: Number of tools to retrieve
        
        Returns:
            List of ToolSchema objects
        """
        print(f"  Retrieving Top-{k} tools for: '{query[:60]}...'")
        
        # Use semantic router to get top-k
        results = self.semantic_router.retrieve_tools(query, top_k=k, use_hybrid=True)
        
        # Convert to ToolSchema objects
        tools = []
        for tool_id, score in results:
            if tool_id in self.all_tools:
                tools.append(self.all_tools[tool_id])
                print(f"    ✓ {tool_id} (score: {score:.3f})")
        
        return tools
    
    async def close(self):
        """Clean up resources."""
        if self.mcp_client:
            await self.mcp_client.close_all()


class BeeAIToolAdapter:
    """
    Adapter to convert MCP tools to BeeAI-compatible tool format.
    """
    
    @staticmethod
    def convert_mcp_to_beeai_tool(tool_schema: ToolSchema, mcp_client: MCPClient):
        """
        Convert an MCP ToolSchema to a BeeAI-compatible tool function.
        
        Args:
            tool_schema: MCP tool schema
            mcp_client: MCP client for execution
        
        Returns:
            BeeAI-compatible tool function
        """
        async def tool_function(**kwargs):
            """Dynamically generated tool function."""
            result = await mcp_client.call_tool(tool_schema.id, kwargs)
            
            if result.get("success"):
                # Extract text content
                content_text = ""
                for content_item in result.get("content", []):
                    if content_item.get("type") == "text":
                        content_text += content_item.get("text", "")
                return content_text
            else:
                return f"Error: {result.get('error', 'Unknown error')}"
        
        # Set function metadata for BeeAI
        tool_function.__name__ = tool_schema.name
        tool_function.__doc__ = tool_schema.description
        
        return tool_function


async def start_fastmcp_server():
    """Start the FastMCP server as a subprocess."""
    print("=" * 70)
    print("Starting FastMCP Server...")
    print("=" * 70)
    
    server_path = Path(__file__).parent / "mock_fastmcp_server.py"
    
    # Start server in background
    process = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Wait for server to start
    print("Waiting for server to initialize...")
    time.sleep(3)
    
    if process.poll() is not None:
        stdout, stderr = process.communicate()
        print(f"Server failed to start:\n{stderr}")
        return None
    
    print("✓ FastMCP server started\n")
    return process


async def run_policy_agent(
    tools: List[ToolSchema],
    mcp_client: MCPClient,
    user_query: str
) -> str:
    """
    Run the Policy Agent to fetch policy details and check coverage.
    
    Args:
        tools: List of tools for this agent
        mcp_client: MCP client for tool execution
        user_query: User query
    
    Returns:
        Agent response
    """
    print("\n" + "=" * 70)
    print("POLICY AGENT - Checking Insurance Coverage")
    print("=" * 70)
    
    # Convert tools to BeeAI format
    beeai_tools = []
    for tool in tools:
        tool_func = BeeAIToolAdapter.convert_mcp_to_beeai_tool(tool, mcp_client)
        beeai_tools.append(tool_func)
    
    # Create BeeAI agent
    memory = TokenMemory()
    
    # Create a simple LLM wrapper for BeeAI
    class SimpleLLM(ChatLLM):
        async def generate(self, messages, **kwargs):
            # Use litellm for generation
            response = completion(
                model=config.llm.heavy_model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=0.0
            )
            return response.choices[0].message.content
    
    llm = SimpleLLM()
    
    agent = BeeAgent(
        llm=llm,
        memory=memory,
        tools=beeai_tools
    )
    
    # Run agent
    print(f"\nQuery: {user_query}")
    print("\nAgent working...")
    
    response = await agent.run(user_query)
    
    print(f"\nPolicy Agent Response:\n{response}")
    print("=" * 70)
    
    return response


async def run_billing_agent(
    tools: List[ToolSchema],
    mcp_client: MCPClient,
    user_query: str
) -> str:
    """
    Run the Billing Agent to fetch discharge summary and verify bills.
    
    Args:
        tools: List of tools for this agent
        mcp_client: MCP client for tool execution
        user_query: User query
    
    Returns:
        Agent response
    """
    print("\n" + "=" * 70)
    print("BILLING AGENT - Verifying Hospital Bills")
    print("=" * 70)
    
    # Convert tools to BeeAI format
    beeai_tools = []
    for tool in tools:
        tool_func = BeeAIToolAdapter.convert_mcp_to_beeai_tool(tool, mcp_client)
        beeai_tools.append(tool_func)
    
    # Create BeeAI agent
    memory = TokenMemory()
    
    class SimpleLLM(ChatLLM):
        async def generate(self, messages, **kwargs):
            response = completion(
                model=config.llm.heavy_model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=0.0
            )
            return response.choices[0].message.content
    
    llm = SimpleLLM()
    
    agent = BeeAgent(
        llm=llm,
        memory=memory,
        tools=beeai_tools
    )
    
    # Run agent
    print(f"\nQuery: {user_query}")
    print("\nAgent working...")
    
    response = await agent.run(user_query)
    
    print(f"\nBilling Agent Response:\n{response}")
    print("=" * 70)
    
    return response


async def run_claim_processing_agent(
    tools: List[ToolSchema],
    mcp_client: MCPClient,
    user_query: str,
    policy_info: str,
    billing_info: str
) -> str:
    """
    Run the Claim Processing Agent to calculate and submit the claim.
    
    Args:
        tools: List of tools for this agent
        mcp_client: MCP client for tool execution
        user_query: User query
        policy_info: Information from Policy Agent
        billing_info: Information from Billing Agent
    
    Returns:
        Agent response
    """
    print("\n" + "=" * 70)
    print("CLAIM PROCESSING AGENT - Calculating and Submitting Claim")
    print("=" * 70)
    
    # Convert tools to BeeAI format
    beeai_tools = []
    for tool in tools:
        tool_func = BeeAIToolAdapter.convert_mcp_to_beeai_tool(tool, mcp_client)
        beeai_tools.append(tool_func)
    
    # Create BeeAI agent
    memory = TokenMemory()
    
    class SimpleLLM(ChatLLM):
        async def generate(self, messages, **kwargs):
            response = completion(
                model=config.llm.heavy_model,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                temperature=0.0
            )
            return response.choices[0].message.content
    
    llm = SimpleLLM()
    
    agent = BeeAgent(
        llm=llm,
        memory=memory,
        tools=beeai_tools
    )
    
    # Construct enriched query with context from previous agents
    enriched_query = f"""{user_query}

Context from Policy Agent:
{policy_info}

Context from Billing Agent:
{billing_info}

Please calculate the final claimable amount and submit the mediclaim."""
    
    # Run agent
    print(f"\nQuery: {user_query}")
    print("\nAgent working...")
    
    response = await agent.run(enriched_query)
    
    print(f"\nClaim Processing Agent Response:\n{response}")
    print("=" * 70)
    
    return response


async def main():
    """Main orchestration function."""
    print("\n" + "=" * 70)
    print("IBM BeeAI Multi-Agent Mediclaim Processing Orchestrator")
    print("=" * 70)
    print("\nThis example demonstrates:")
    print("  1. Dynamic tool retrieval using NeuralToolRouter")
    print("  2. Hybrid retrieval (Dense + BM25 with RRF)")
    print("  3. Multi-agent orchestration with IBM BeeAI")
    print("  4. Context passing between specialized agents")
    print("=" * 70 + "\n")
    
    # Start FastMCP server
    server_process = await start_fastmcp_server()
    if server_process is None:
        print("Failed to start FastMCP server. Exiting.")
        return
    
    try:
        # Initialize NeuralToolRouter
        router = ToolRouterForBeeAI()
        await router.initialize()
        
        # Define the overarching goal
        print("=" * 70)
        print("ORCHESTRATION GOAL")
        print("=" * 70)
        goal = """Process the post-hospitalisation mediclaim for Patient ID 1024 
(Policy #POL-999) who recently had a knee replacement surgery. 
Verify their coverage, analyze the hospital bills, and submit the final claim."""
        print(goal)
        print("=" * 70 + "\n")
        
        # Step 1: Policy Agent
        print("\n[STEP 1/3] Policy Agent - Checking Coverage")
        print("-" * 70)
        policy_query = "Fetch insurance policy details for POL-999 and check coverage limits for knee replacement surgery"
        policy_tools = await router.get_top_k_tools(policy_query, k=2)
        
        policy_response = await run_policy_agent(
            policy_tools,
            router.mcp_client,
            policy_query
        )
        
        # Step 2: Billing Agent
        print("\n[STEP 2/3] Billing Agent - Verifying Bills")
        print("-" * 70)
        billing_query = "Fetch hospital discharge summary for patient 1024 and verify the hospital bills"
        billing_tools = await router.get_top_k_tools(billing_query, k=2)
        
        billing_response = await run_billing_agent(
            billing_tools,
            router.mcp_client,
            billing_query
        )
        
        # Step 3: Claim Processing Agent
        print("\n[STEP 3/3] Claim Processing Agent - Submitting Claim")
        print("-" * 70)
        claim_query = "Calculate the final claimable amount and submit the mediclaim for patient 1024 with policy POL-999"
        claim_tools = await router.get_top_k_tools(claim_query, k=2)
        
        claim_response = await run_claim_processing_agent(
            claim_tools,
            router.mcp_client,
            claim_query,
            policy_response,
            billing_response
        )
        
        # Final Summary
        print("\n" + "=" * 70)
        print("ORCHESTRATION COMPLETE")
        print("=" * 70)
        print("\n✓ Policy verified")
        print("✓ Bills verified")
        print("✓ Claim submitted")
        print("\nFinal Claim Submission:")
        print(claim_response)
        print("\n" + "=" * 70)
        
        # Cleanup
        await router.close()
        
    finally:
        # Stop FastMCP server
        if server_process:
            print("\nStopping FastMCP server...")
            server_process.terminate()
            server_process.wait()
            print("✓ Server stopped")


if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
