"""
LangGraph Multi-Agent UHNW Banking Orchestrator

This script demonstrates how to use ToolRouter to dynamically inject
different subsets of FastMCP tools into multiple specialized LangChain agents
orchestrated by LangGraph to serve a Private Banking Concierge use case.
"""

import asyncio
import sys
import os
import subprocess
import time
import argparse
import base64
import uuid
import json
from pathlib import Path
from typing import List, Dict, Any, Tuple, TypedDict, Annotated, Sequence, Literal
from dotenv import load_dotenv
import operator

# Load environment variables
load_dotenv()

# Add parent directory to path to import ToolRouter
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sentence_transformers import SentenceTransformer
from pydantic import BaseModel, create_model, Field

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, START, END

from tool_router.config import config
from tool_router.mcp_client import MCPClient, ToolSchema
from tool_router.runtime import SemanticRouter

class ToolRouterForLangChain:
    """
    Adapter that wraps ToolRouter for use with LangChain and LangGraph.
    Provides Top-K tool retrieval for dynamic tool injection.
    """
    
    def __init__(self, model_path: str = None):
        self.embedding_model: SentenceTransformer = None
        self.semantic_router: SemanticRouter = None
        self.mcp_client: MCPClient = None
        self.all_tools: Dict[str, ToolSchema] = {}
        self._model_path = model_path
    
    async def initialize(self):
        print("Initializing ToolRouter...")
        
        # Resolve embedding model path:
        #   1. Explicit model_path from UI selection
        #   2. Default fine_tuned_model_dir from config
        #   3. Fallback to base model name
        if self._model_path:
            resolved_path = Path(self._model_path)
            if not resolved_path.is_absolute():
                resolved_path = Path(__file__).parent.parent.parent / "backend" / "models" / self._model_path
            if resolved_path.exists():
                model_to_load = str(resolved_path)
                print(f"  Using UI-selected model: {model_to_load}")
            else:
                print(f"  ⚠ UI-selected model not found at {resolved_path}, falling back to base model")
                model_to_load = config.embedding.base_model_name
        else:
            fine_tuned_path = config.embedding.fine_tuned_model_dir
            if fine_tuned_path.exists():
                model_to_load = str(fine_tuned_path)
                print(f"  Using fine-tuned model: {model_to_load}")
            else:
                print(f"  ⚠ Fine-tuned model not found at {fine_tuned_path}, using base model")
                model_to_load = config.embedding.base_model_name
        
        self.embedding_model = SentenceTransformer(
            model_to_load,
            device=config.embedding.device
        )
        self.semantic_router = SemanticRouter(self.embedding_model, config.vector_store)
        
        if config.vector_store.store_type == "faiss":
            self.semantic_router.load_faiss_index()
            
        try:
            self.semantic_router.load_bm25_index()
            print("  ✓ Hybrid retrieval enabled (Dense + BM25)")
        except FileNotFoundError:
            print("  ⚠ BM25 index not found, using dense-only retrieval")
            
        print("  Connecting to FastMCP server...")
        self.mcp_client = MCPClient(config.mcp)
        await self.mcp_client.connect_all()
        tools = await self.mcp_client.list_tools()
        
        for tool in tools:
            self.all_tools[tool.id] = tool
            
        print(f"  ✓ Connected to MCP server with {len(self.all_tools)} tools")
    
    async def get_top_k_tools(self, query: str, k: int = 2) -> List[ToolSchema]:
        print(f"  Retrieving Top-{k} tools for: '{query[:60]}...'")
        results = self.semantic_router.retrieve_tools(query, top_k=k, use_hybrid=True)
        tools = []
        for tool_id, score in results:
            if tool_id in self.all_tools:
                tools.append(self.all_tools[tool_id])
                print(f"    ✓ {tool_id} (score: {score:.3f})")
        return tools
    
    async def close(self):
        if self.mcp_client:
            await self.mcp_client.close_all()


class LangChainToolAdapter:
    """Adapter to convert MCP tools to LangChain StructuredTool format."""
    
    @staticmethod
    def convert_mcp_to_langchain_tool(tool_schema: ToolSchema, mcp_client: MCPClient):
        fields = {}
        schema = tool_schema.parameters
        for k, v in schema.get("properties", {}).items():
            t_str = v.get("type", "string")
            if t_str == "string": t = str
            elif t_str == "integer": t = int
            elif t_str == "number": t = float
            elif t_str == "boolean": t = bool
            elif t_str == "array": t = list
            elif t_str == "object": t = dict
            else: t = Any
            
            req = k in schema.get("required", [])
            fields[k] = (t, Field(default=... if req else None, description=v.get("description", "")))
            
        model_name = "".join(x.capitalize() for x in tool_schema.name.split("_")) + "Input"
        input_model = create_model(model_name, **fields)

        async def tool_function(**kwargs) -> str:
            start_time = time.time()
            print(f"\n  [Tool Execution] Executing '{tool_schema.name}' with args: {kwargs}")
            
            result = await mcp_client.call_tool(tool_schema.id, kwargs)
            
            latency = time.time() - start_time
            print(f"  [Tool Execution] ✓ '{tool_schema.name}' completed in {latency:.2f} seconds")
            
            if result.get("success") or "success" not in result:
                content_text = ""
                if "content" in result:
                    for content_item in result.get("content", []):
                        if content_item.get("type") == "text":
                            content_text += content_item.get("text", "")
                else:
                    content_text = json.dumps(result)
                return content_text
            else:
                return f"Error: {result.get('error', 'Unknown error')}"

        return StructuredTool.from_function(
            func=None,
            coroutine=tool_function,
            name=tool_schema.name,
            description=tool_schema.description,
            args_schema=input_model
        )


async def start_fastmcp_server():
    print("=" * 70)
    print("Starting FastMCP Server...")
    print("=" * 70)
    
    server_path = Path(__file__).parent / "mock_fastmcp_server.py"
    process = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    print("Waiting for server to initialize...")
    time.sleep(3)
    
    if process.poll() is not None:
        stdout, stderr = process.communicate()
        print(f"Server failed to start:\n{stderr}")
        return None
    
    print("✓ FastMCP server started\n")
    return process


def setup_observability():
    """Set up Langfuse observability if configured via environment variables."""
    # Check if Langfuse or OTEL is configured
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY")
    otel_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_traces_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")
    
    if not ((public_key and secret_key) or otel_endpoint or otel_traces_endpoint):
        return None
        
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor
        from opentelemetry import trace as trace_api
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk import trace as trace_sdk
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace import SpanProcessor
        
        class LangfuseSessionProcessor(SpanProcessor):
            """OpenTelemetry SpanProcessor to inject Langfuse session ID into all spans."""
            def __init__(self, session_id: str):
                self.session_id = session_id
                
            def on_start(self, span, parent_context=None):
                span.set_attribute("langfuse.session.id", self.session_id)
                
            def on_end(self, span):
                pass
        
        # If OTEL env vars are not set but LANGFUSE vars are, set the OTEL vars dynamically
        if not otel_endpoint and not otel_traces_endpoint and public_key and secret_key:
            host = os.environ.get("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
            endpoint = f"{host.rstrip('/')}/api/public/otel/v1/traces"
            
            auth_string = f"{public_key}:{secret_key}"
            auth_base64 = base64.b64encode(auth_string.encode()).decode()
            headers = f"Authorization=Basic {auth_base64},x-langfuse-ingestion-version=4"
            
            os.environ["OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"] = endpoint
            os.environ["OTEL_EXPORTER_OTLP_TRACES_HEADERS"] = headers
            
            exporter = OTLPSpanExporter(
                endpoint=endpoint,
                headers={
                    "Authorization": f"Basic {auth_base64}",
                    "x-langfuse-ingestion-version": "4"
                }
            )
        else:
            exporter = OTLPSpanExporter()

        resource = Resource(attributes={})
        tracer_provider = trace_sdk.TracerProvider(resource=resource)
        
        session_id = str(uuid.uuid4())
        tracer_provider.add_span_processor(LangfuseSessionProcessor(session_id))
        tracer_provider.add_span_processor(SimpleSpanProcessor(exporter))
        trace_api.set_tracer_provider(tracer_provider)
        
        LangChainInstrumentor().instrument()
        print(f"✓ Langfuse observability enabled via OpenTelemetry (Session: {session_id})\n")
        return session_id
    except ImportError as e:
        print(f"⚠ Langfuse observability skipped: Missing dependencies ({e}).")
        print("  To enable, run: pip install openinference-instrumentation-langchain opentelemetry-sdk opentelemetry-exporter-otlp\n")
        return None

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    next: str


def create_agent(llm, tools, system_prompt):
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm
    return prompt | llm_with_tools


async def main():
    parser = argparse.ArgumentParser(description="LangGraph Multi-Agent UHNW Banking Orchestrator")
    parser.add_argument("--llm", type=str, choices=["openai", "ollama"], default="openai",
                        help="Choose LLM provider (openai or ollama)")
    parser.add_argument("--model", type=str, default="", 
                        help="Specific model name (default: gpt-4o for openai)")
    args = parser.parse_args()

    if args.llm == "openai":
        model_name = args.model if args.model else "gpt-4o"
        # We need an LLM that supports bind_tools robustly. OpenAI is standard.
        llm = ChatOpenAI(model=model_name, temperature=0)
    else:
        print("Note: Ollama needs to support tool calling for this setup.")
        model_name = args.model if args.model else "llama3.1"
        llm = ChatOpenAI(base_url="http://localhost:11434/v1", api_key="ollama", model=model_name, temperature=0)

    print(f"Using LLM: {model_name}")
    print("\n" + "=" * 70)
    print("UHNW Private Banking Multi-Agent Orchestrator")
    print("=" * 70)

    # Setup observability
    session_id = setup_observability()

    server_process = await start_fastmcp_server()
    if server_process is None:
        return
        
    try:
        router = ToolRouterForLangChain()
        await router.initialize()

        # Build tools for each specialized agent dynamically
        # Let's say we define standard tasks for them to fetch the right tools from the router
        
        print("\nRetrieving tools for specialized agents...")
        
        # Portfolio Manager Tools
        pm_query = "retrieve portfolio summary, unrealized gains losses, asset allocation holdings performance"
        pm_mcp_tools = await router.get_top_k_tools(pm_query, k=2)
        pm_tools = [LangChainToolAdapter.convert_mcp_to_langchain_tool(t, router.mcp_client) for t in pm_mcp_tools]
        
        # Market Analyst Tools
        ma_query = "live market data, execute trade buy sell, stock market news sentiment"
        ma_mcp_tools = await router.get_top_k_tools(ma_query, k=3)
        ma_tools = [LangChainToolAdapter.convert_mcp_to_langchain_tool(t, router.mcp_client) for t in ma_mcp_tools]
        
        # Tax & Compliance Tools
        tc_query = "simulate capital gains tax, tax loss harvesting options, run AML transaction check"
        tc_mcp_tools = await router.get_top_k_tools(tc_query, k=3)
        tc_tools = [LangChainToolAdapter.convert_mcp_to_langchain_tool(t, router.mcp_client) for t in tc_mcp_tools]
        
        # Concierge Tools
        c_query = "update card limit temporarily raise, initiate wire transfer external"
        c_mcp_tools = await router.get_top_k_tools(c_query, k=2)
        c_tools = [LangChainToolAdapter.convert_mcp_to_langchain_tool(t, router.mcp_client) for t in c_mcp_tools]
        
        print("✓ All tools retrieved and wrapped for LangChain")

        # Create Agents
        portfolio_agent = create_agent(llm, pm_tools, "You are the Portfolio Manager Agent. You analyze the client's holdings and performance. You must output the result directly to the user or indicate the information discovered. When using tools, invoke them then provide the final answer.")
        market_agent = create_agent(llm, ma_tools, "You are the Trading & Market Analyst Agent. You fetch market data, news, and execute trades. Use tools to fetch information or perform actions.")
        tax_agent = create_agent(llm, tc_tools, "You are the Tax & Compliance Officer Agent. You handle capital gains simulation, tax loss harvesting, and AML checks.")
        concierge_agent = create_agent(llm, c_tools, "You are the Premium Concierge Agent. You handle lifestyle banking, updating card limits, and initiating wire transfers.")

        # Agent node functions
        async def call_portfolio_agent(state: AgentState):
            print("\n[Portfolio Agent processing...]")
            response = await portfolio_agent.ainvoke(state)
            return {"messages": [response]}
            
        async def call_market_agent(state: AgentState):
            print("\n[Market Agent processing...]")
            response = await market_agent.ainvoke(state)
            return {"messages": [response]}
            
        async def call_tax_agent(state: AgentState):
            print("\n[Tax & Compliance Agent processing...]")
            response = await tax_agent.ainvoke(state)
            return {"messages": [response]}
            
        async def call_concierge_agent(state: AgentState):
            print("\n[Concierge Agent processing...]")
            response = await concierge_agent.ainvoke(state)
            return {"messages": [response]}

        # Create Supervisor
        class routeResponse(BaseModel):
            next: Literal["FINISH", "PortfolioManager", "TradingAnalyst", "TaxCompliance", "Concierge"]
            
        supervisor_prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Supervisor for a UHNW Private Banking Concierge.
Given the conversation, decide who should act next.
Options:
- PortfolioManager: For portfolio queries, holdings, performance.
- TradingAnalyst: For executing trades, fetching market data or news.
- TaxCompliance: For tax simulations, harvesting, or AML compliance checks on large wires.
- Concierge: For credit card limits, wire transfers, lifestyle.
- FINISH: When the user's request has been fully resolved by the agents and a final response is ready.

IMPORTANT: If the user's core question has been fully answered by previous agents in the conversation history, you MUST output FINISH. Do not route to other agents unnecessarily.
"""),
            MessagesPlaceholder(variable_name="messages"),
            ("system", "Given the conversation above, who should act next? Select FINISH if the user's request has been completely answered. Ensure you output FINISH if the user's intent is fully satisfied.")
        ])
        
        supervisor_chain = supervisor_prompt | llm.with_structured_output(routeResponse)

        async def supervisor_node(state: AgentState):
            print("\n[Supervisor routing...]")
            decision = await supervisor_chain.ainvoke(state)
            print(f" -> Routing to: {decision.next}")
            return {"next": decision.next}

        # Build Graph
        workflow = StateGraph(AgentState)
        
        workflow.add_node("PortfolioManager", call_portfolio_agent)
        workflow.add_node("TradingAnalyst", call_market_agent)
        workflow.add_node("TaxCompliance", call_tax_agent)
        workflow.add_node("Concierge", call_concierge_agent)
        workflow.add_node("supervisor", supervisor_node)
        
        # To handle tool execution within the graph seamlessly for Langchain (since we are not using pre-built ToolNode for agents doing multiple tool calls, we keep it simple for the example where the agent LLM returns tool_calls, we execute them, and pass back)
        # Actually, LangGraph's standard create_react_agent would be cleaner for worker nodes. 
        # But since we defined custom call functions, we need a small executor.
        
        from langgraph.prebuilt import ToolNode
        
        pm_tool_node = ToolNode(pm_tools)
        ma_tool_node = ToolNode(ma_tools)
        tc_tool_node = ToolNode(tc_tools)
        c_tool_node = ToolNode(c_tools)
        
        workflow.add_node("pm_tools", pm_tool_node)
        workflow.add_node("ma_tools", ma_tool_node)
        workflow.add_node("tc_tools", tc_tool_node)
        workflow.add_node("c_tools", c_tool_node)
        
        # Define routing edges for tool execution
        def pm_router(state):
            last = state["messages"][-1]
            if last.tool_calls: return "pm_tools"
            return "supervisor"
            
        def ma_router(state):
            last = state["messages"][-1]
            if last.tool_calls: return "ma_tools"
            return "supervisor"
            
        def tc_router(state):
            last = state["messages"][-1]
            if last.tool_calls: return "tc_tools"
            return "supervisor"
            
        def c_router(state):
            last = state["messages"][-1]
            if last.tool_calls: return "c_tools"
            return "supervisor"

        workflow.add_conditional_edges("PortfolioManager", pm_router, {"pm_tools": "pm_tools", "supervisor": "supervisor"})
        workflow.add_edge("pm_tools", "PortfolioManager")
        
        workflow.add_conditional_edges("TradingAnalyst", ma_router, {"ma_tools": "ma_tools", "supervisor": "supervisor"})
        workflow.add_edge("ma_tools", "TradingAnalyst")
        
        workflow.add_conditional_edges("TaxCompliance", tc_router, {"tc_tools": "tc_tools", "supervisor": "supervisor"})
        workflow.add_edge("tc_tools", "TaxCompliance")
        
        workflow.add_conditional_edges("Concierge", c_router, {"c_tools": "c_tools", "supervisor": "supervisor"})
        workflow.add_edge("c_tools", "Concierge")

        workflow.add_edge(START, "supervisor")
        workflow.add_conditional_edges(
            "supervisor",
            lambda state: state["next"],
            {
                "PortfolioManager": "PortfolioManager",
                "TradingAnalyst": "TradingAnalyst",
                "TaxCompliance": "TaxCompliance",
                "Concierge": "Concierge",
                "FINISH": END
            }
        )

        app = workflow.compile()
        
        # Test Flow 1
        print("\n" + "="*70)
        print("RUNNING FLOW 1: Tax-Optimized Trading")
        print("="*70)
        user_message = "Nvidia's earnings just came out. How is my tech portfolio doing? Can you sell 1000 shares of NVDA, but tell me the tax hit first and check if there's any tax loss harvesting I can do to offset it? I am client UHNW-123."
        
        config_params = {"recursion_limit": 15}
        async for event in app.astream({"messages": [HumanMessage(content=user_message)]}, config=config_params):
            for node_name, state in event.items():
                if "messages" in state:
                    last_msg = state["messages"][-1]
                    if isinstance(last_msg, AIMessage) and not last_msg.tool_calls:
                        print(f"\n[{node_name}] {last_msg.content}")

        print("\n" + "=" * 70)
        print("ORCHESTRATION COMPLETE")
        if session_id:
            print(f"Langfuse Session ID: {session_id}")
        print("=" * 70)

        # Cleanup
        await router.close()

    finally:
        if server_process:
            print("\nStopping FastMCP server...")
            server_process.terminate()
            server_process.wait()
            print("✓ Server stopped")

if __name__ == "__main__":
    asyncio.run(main())
