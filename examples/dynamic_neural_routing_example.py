"""
Dynamic Neural Tool Routing Example

This script demonstrates how to use the new DynamicLangGraphAgentExecutor
with pre-LLM neural tool routing for intelligent, per-query tool selection.

Usage:
    python examples/dynamic_neural_routing_example.py
"""

import asyncio
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Agent, Tool, LLMConfig, Workspace
from services.langgraph_dynamic_agent_executor import DynamicLangGraphAgentExecutor


async def create_example_agent(session: AsyncSession, workspace_id) -> Agent:
    """Create an example agent with neural routing enabled"""
    
    # Create LLM config
    llm_config = LLMConfig(
        workspace_id=workspace_id,
        name="GPT-4o Config",
        provider="openai",
        model_name="gpt-4o",
        temperature=0.7,
        max_tokens=2000,
        credentials={
            "api_key": "your-openai-api-key"  # Replace with actual key
        }
    )
    session.add(llm_config)
    await session.flush()
    
    # Create example agent
    agent = Agent(
        workspace_id=workspace_id,
        name="Dynamic Portfolio Advisor",
        description="AI agent that uses neural routing to select the best tools for portfolio analysis",
        system_prompt="""You are an expert financial advisor specializing in portfolio management.
        Use the available tools to gather information and provide comprehensive advice.""",
        llm_config_id=llm_config.id,
        use_neural_router=True,  # Enable neural routing
        router_top_k=3,  # Select top 3 tools per query
        memory_type="buffer",
        memory_window=10,
        max_iterations=5,
    )
    session.add(agent)
    await session.commit()
    
    return agent


async def demonstrate_dynamic_routing():
    """Demonstrate the dynamic neural routing architecture"""
    
    print("=" * 80)
    print("Dynamic Neural Tool Routing Example")
    print("=" * 80)
    print()
    
    # Create async engine (replace with your database URL)
    engine = create_async_engine(
        "postgresql+asyncpg://user:password@localhost/synapse_forge",
        echo=False
    )
    
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        # Get or create workspace
        workspace = Workspace(
            name="Example Workspace",
            embedding_model="sentence-transformers/all-MiniLM-L6-v2"
        )
        session.add(workspace)
        await session.commit()
        
        # Create example agent
        print("Creating example agent with neural routing enabled...")
        agent = await create_example_agent(session, workspace.id)
        print(f"✓ Agent created: {agent.name} (ID: {agent.id})")
        print(f"  - Neural Router: {'Enabled' if agent.use_neural_router else 'Disabled'}")
        print(f"  - Top-K: {agent.router_top_k}")
        print()
        
        # Initialize executor
        executor = DynamicLangGraphAgentExecutor(session)
        
        # Example queries demonstrating dynamic routing
        queries = [
            "What's my current portfolio performance?",
            "Show me the latest market trends for tech stocks",
            "Calculate my tax liability for this year",
            "Recommend a diversification strategy",
        ]
        
        for i, query in enumerate(queries, 1):
            print(f"\n{'=' * 80}")
            print(f"Query {i}: {query}")
            print('=' * 80)
            
            # Execute agent with dynamic routing
            async for event in executor.execute_agent(
                agent=agent,
                user_prompt=query,
                router_top_k_override=None,  # Use agent's default
            ):
                try:
                    # Parse SSE event
                    event_data = json.loads(event.removeprefix("data: ").strip())
                    event_type = event_data.get("type")
                    label = event_data.get("label")
                    detail = event_data.get("detail")
                    
                    # Print formatted event
                    if event_type == "router":
                        print(f"\n🔍 {label}")
                        metadata = event_data.get("metadata", {})
                        strategy = metadata.get("strategy", "unknown")
                        selected_tools = metadata.get("selected_tools", [])
                        print(f"   Strategy: {strategy}")
                        print(f"   Selected Tools ({len(selected_tools)}):")
                        for tool in selected_tools:
                            print(f"     - {tool['name']} ({tool['type']})")
                        if "latency_ms" in metadata:
                            print(f"   Latency: {metadata['latency_ms']:.2f}ms")
                    
                    elif event_type == "thought":
                        print(f"\n💭 {label}")
                        if detail and len(detail) < 200:
                            print(f"   {detail}")
                    
                    elif event_type == "tool_call":
                        print(f"\n🔧 {label}")
                        try:
                            tool_data = json.loads(detail)
                            print(f"   Arguments: {json.dumps(tool_data.get('arguments', {}), indent=2)}")
                        except:
                            pass
                    
                    elif event_type == "tool_result":
                        print(f"\n✓ {label}")
                        if detail and len(detail) < 300:
                            print(f"   {detail[:300]}...")
                    
                    elif event_type == "assistant":
                        print(f"\n🤖 {label}")
                        print(f"\n{detail}\n")
                    
                    elif event_type == "error":
                        print(f"\n❌ {label}: {detail}")
                
                except json.JSONDecodeError:
                    continue
            
            print("\n" + "=" * 80)
            
            # Wait between queries
            if i < len(queries):
                await asyncio.sleep(2)
        
        print("\n✓ Example completed successfully!")
        print("\nKey Observations:")
        print("1. Different tools were selected for each query based on semantic relevance")
        print("2. The neural router ran BEFORE the LLM was invoked")
        print("3. Only the top-k most relevant tools were bound to the LLM")
        print("4. This approach scales efficiently with large tool registries")


async def compare_static_vs_dynamic():
    """Compare static vs dynamic routing performance"""
    
    print("\n" + "=" * 80)
    print("Static vs Dynamic Routing Comparison")
    print("=" * 80)
    print()
    
    print("Static Routing (Original):")
    print("  - Loads ALL tools at initialization")
    print("  - Binds ALL tools to LLM for every query")
    print("  - LLM must choose from entire tool set")
    print("  - Performance degrades with large tool registries")
    print()
    
    print("Dynamic Routing (New):")
    print("  - Loads tools on-demand per query")
    print("  - Uses NeuralToolRouter to select top-k relevant tools")
    print("  - Binds ONLY selected tools to LLM")
    print("  - Scales efficiently regardless of registry size")
    print()
    
    print("Benefits:")
    print("  ✓ Reduced LLM context size")
    print("  ✓ Faster tool selection")
    print("  ✓ Better tool choice accuracy")
    print("  ✓ Lower API costs")
    print("  ✓ Improved scalability")


async def main():
    """Main entry point"""
    try:
        print("\n🚀 Starting Dynamic Neural Tool Routing Example\n")
        
        # Run comparison
        await compare_static_vs_dynamic()
        
        # Run demonstration
        # Uncomment to run full demo (requires database setup)
        # await demonstrate_dynamic_routing()
        
        print("\n" + "=" * 80)
        print("Example completed! Check the documentation for more details:")
        print("  backend/services/DYNAMIC_LANGGRAPH_ARCHITECTURE.md")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
