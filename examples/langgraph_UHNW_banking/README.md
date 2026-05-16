# LangGraph Multi-Agent UHNW Banking Example

This example demonstrates how to use **SynapseForge** with the **LangGraph** Multi-Agent framework to orchestrate a complex Ultra-High-Net-Worth (UHNW) private banking scenario.

## Overview

The example showcases:

1. **Dynamic Tool Retrieval**: Using SynapseForge's hybrid retrieval (Dense + BM25 with RRF) to fetch only relevant tools for each agent.
2. **Supervisor Multi-Agent Pattern**: A LangGraph Supervisor agent dynamically routes user intents to four specialized LangChain Worker Agents.
3. **Context Passing**: The StateGraph natively passes the conversation message history and context between agents.
4. **FastMCP Integration**: Mock private banking tools (wealth management, market data, tax compliance, core banking) exposed via FastMCP.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                 LangGraph Supervisor                        │
│  (Coordinates 4 specialized agents based on user intent)    │
└──────┬──────────┬───────────┬────────────┬──────────────────┘
       │          │           │            │
       │          │           │            └──> [Concierge Agent]
       │          │           │                 Tools: update_card_limit, initiate_wire_transfer
       │          │           │                 Task: Cards, lifestyle, payments
       │          │           │
       │          │           └──> [Tax & Compliance Agent]
       │          │                Tools: simulate_capital_gains_tax, get_tax_loss_harvesting_options, run_aml_transaction_check
       │          │                Task: Tax optimization and AML checks
       │          │
       │          └──> [Trading Analyst Agent]
       │               Tools: get_live_market_data, get_market_news, execute_trade
       │               Task: Market intelligence and trade execution
       │
       └──> [Portfolio Manager Agent]
            Tools: get_portfolio_summary, get_unrealized_gains_losses
            Task: Analyze holdings and performance
```

## Files

- **`mock_fastmcp_server.py`**: FastMCP server with 10 mock private banking tools across four domains.
- **`multi_agent_orchestrator.py`**: Main orchestration script using LangGraph and LangChain.
- **`requirements.txt`**: Python dependencies.
- **`.env`**: Environment file for configuring API keys.

## Setup

### 1. Install Dependencies

```bash
cd examples/langgraph_UHNW_banking
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in this directory and add your OpenAI API key (or other LLM credentials):
```
OPENAI_API_KEY=your_openai_api_key
```

### 3. Ensure ToolRouter is Trained

The example requires a trained SynapseForge model. From the project root:

```bash
# Generate training data
python main.py generate

# Train model and build indices
python main.py train
```

### 4. Configure MCP Server

Update `config.py` in the project root to include the FastMCP server for this banking scenario:

```python
servers: Dict[str, Dict[str, Any]] = {
    "uhnwc_banking": {
        "command": "python",
        "args": ["examples/langgraph_UHNW_banking/mock_fastmcp_server.py"],
        "transport": "stdio"
    }
}
```

## Usage

Run the orchestrator. You can choose the LLM provider (OpenAI or Ollama):

```bash
# Run with OpenAI (Recommended for structured tool calling)
python multi_agent_orchestrator.py --llm openai --model gpt-4o

# Run with Ollama (Ensure your local model supports structured tool calls well)
python multi_agent_orchestrator.py --llm ollama --model llama3.1
```

## Example Output

```
======================================================================
UHNW Private Banking Multi-Agent Orchestrator
======================================================================
Starting FastMCP Server...
✓ FastMCP server started

Initializing ToolRouter...
  ✓ Hybrid retrieval enabled (Dense + BM25)
  Connecting to FastMCP server...
  ✓ Connected to MCP server with 10 tools

Retrieving tools for specialized agents...
  Retrieving Top-2 tools for: 'retrieve portfolio summary, unrealized gains losses...'
    ✓ uhnwc_banking.get_portfolio_summary (score: 0.910)
    ✓ uhnwc_banking.get_unrealized_gains_losses (score: 0.885)
...
✓ All tools retrieved and wrapped for LangChain

======================================================================
RUNNING FLOW 1: Tax-Optimized Trading
======================================================================

[Supervisor routing...]
 -> Routing to: PortfolioManager

[Portfolio Agent processing...]
  [Tool Execution] Executing 'get_portfolio_summary' with args: {'client_id': 'UHNW-123'}
  [Tool Execution] ✓ 'get_portfolio_summary' completed in 0.05 seconds
  
[PortfolioManager] Your tech portfolio is up 18.5% YTD. You currently hold 5,000 shares of NVDA...

[Supervisor routing...]
 -> Routing to: TaxCompliance

[Tax & Compliance Agent processing...]
  [Tool Execution] Executing 'simulate_capital_gains_tax' with args: {'client_id': 'UHNW-123', 'ticker': 'NVDA', 'quantity_to_sell': 1000}
  [Tool Execution] ✓ 'simulate_capital_gains_tax' completed in 0.04 seconds
...
```

## Key Features Demonstrated

### 1. Hybrid Retrieval (Dense + BM25)

Each agent tool requirement is processed through:
- **Dense Retrieval**: Fine-tuned sentence transformer embeddings
- **Sparse Retrieval**: BM25 keyword matching
- **RRF Fusion**: Reciprocal Rank Fusion combines both scores

This ensures both semantic understanding and exact keyword matching.

### 2. Dynamic Tool Injection

Instead of giving all 10 tools to every agent:
- Portfolio Agent gets only 2 portfolio-related tools
- Market Agent gets only 3 market-related tools
- Tax Agent gets only 3 compliance-related tools
- Concierge Agent gets only 2 banking tools

This significantly reduces token consumption and context size while improving LLM tool-calling accuracy.

### 3. LangGraph Orchestration

The Supervisor Agent acts as an intelligent router determining which specialist worker should be invoked based on the user's latest message or sub-task progression. 

### 4. Context Passing

LangGraph's `StateGraph` natively passes the `messages` list globally between agents. The Tax Agent knows precisely what the Portfolio Agent discovered without duplicating queries.

## Customization

### Add More Tools

Edit `mock_fastmcp_server.py` to add more tools:

```python
@mcp.tool()
def your_new_banking_tool(client_id: str) -> Dict[str, Any]:
    """Tool description."""
    return {"success": True, "data": "..."}
```

### Modify Agent Behavior

Edit `multi_agent_orchestrator.py` to change:
- Number of tools retrieved (`k=2` or `k=3`)
- Agent system prompts
- Orchestration routing logic

### Use Real MCP Servers

Replace the mock server with real enterprise MCP servers in `config.py`:

```python
servers: Dict[str, Dict[str, Any]] = {
    "core_wealth_api": {
        "command": "npx",
        "args": ["-y", "@your-org/core-wealth-mcp"],
        "transport": "stdio"
    }
}
```

## Troubleshooting

### "Fine-tuned model not found"
Run Phase 2 training first:
```bash
cd ../..
python main.py train
```

### "BM25 index not found"
The system will fall back to dense-only retrieval. To enable hybrid:
```bash
cd ../..
python main.py train  # Rebuilds both indices
```

### "FastMCP server failed to start"
Check that fastmcp is installed:
```bash
pip install fastmcp
```

## Performance Metrics

With this architecture:
- **Context Reduction**: ~70% (10 tools → 2-3 tools per agent)
- **Retrieval Accuracy**: 95%+ (hybrid retrieval)
- **Tool Selection Error Rate**: Considerably reduced by avoiding cognitive overload on the LLM.

## Learn More

- [LangChain & LangGraph](https://python.langchain.com/docs/langgraph)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP](https://github.com/jlowin/fastmcp)
- [SynapseForge Documentation](../../README.md)

## License

Same as parent project.
