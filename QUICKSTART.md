# Neural ToolRouter - Quick Start Guide

Get up and running with NeuralToolRouter in 5 minutes!

## Prerequisites

- Python 3.10+ (Recommended, minimum 3.8)
- pip package manager
- CUDA-capable GPU (optional, for faster training)
- API keys for LLM providers (OpenAI, Anthropic, or Google)
- MCP servers configured (optional, framework falls back to predefined tools)

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/neural-tool-router.git
cd neural-tool-router
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure API Keys

Copy the example environment file and add your API keys:

```bash
cp .env.example .env
```

Edit `.env` and add your API key(s):

```bash
# At minimum, add one of these or you can also use local models running on Ollama:
OPENAI_API_KEY=sk-your-key-here
# ANTHROPIC_API_KEY=sk-ant-your-key-here
# GOOGLE_API_KEY=your-key-here
```

## Quick Test Run

### Option 1: Using Predefined Tools (Recommended for First Run)

The framework includes predefined tools for testing without MCP server setup:

```bash
# Phase 1: Generate synthetic training data
python main.py generate 

# Phase 2: Train the model (after Phase 1 completes)
python main.py train 

# Phase 3: Run the agentic loop
python main.py run 

# Archive all artifacts
python main.py archive

```

### Option 2: Using MCP Servers

If you want to use actual MCP servers:

1. Install Node.js (for MCP filesystem server)
2. Update `config.py` to enable MCP servers
3. Run the phases as above

## What Each Phase Does

### Phase 1: Synthetic Data Generation
- Connects to tool sources (MCP servers or predefined tools)
- Uses Teacher LLM to generate diverse queries
- Creates training dataset with hard negatives
- **Output**: `data/synthetic_queries.jsonl`
- **Time**: ~5-10 minutes (depends on number of tools)

### Phase 2: Model Training
- Loads synthetic dataset
- Fine-tunes embedding model using contrastive learning
- Implements hybrid retrieval (BM25 + Dense)
- **Output**: `models/fine_tuned_tool_router/`
- **Time**: ~10-30 minutes (depends on dataset size and hardware)

### Phase 3: Runtime Execution
- Loads fine-tuned model
- Accepts user queries
- Routes to appropriate tools
- Executes tool calls
- **Interactive**: Runs until you exit

## Example Applications

The repository includes two full multi-agent example applications that demonstrate `NeuralToolRouter` in action. Both examples use hybrid search to dynamically inject only the relevant tools into each specialized agent.

### 1. LangGraph UHNW Private Banking Example

A LangGraph Supervisor agent coordinates 4 specialized LangChain agents (Portfolio, Tax, Market, Concierge) for a banking scenario.

**To run:**
```bash
# 1. Update config.py to use the banking MCP server
# Un-comment the 'uhnwc_banking' server configuration in config.mcp.servers

# 2. Run the orchestrator
cd examples/langgraph_UHNW_banking
python multi_agent_orchestrator.py --llm ollama --model granite4.1:8b
# Or using OpenAI: python multi_agent_orchestrator.py --llm openai --model gpt-4o
```

### 2. IBM BeeAI Mediclaim Processing Example

An orchestrator coordinates 3 specialized IBM BeeAgents (Policy, Billing, Claim) to process medical insurance claims.

**To run:**
```bash
# 1. Update config.py to use the mediclaim MCP server
# Un-comment the 'mediclaim' server configuration in config.mcp.servers

# 2. Run the orchestrator
cd examples/beeai_mediclaim_processing
python multi_agent_orchestrator.py --llm ollama --model llama3
# Or using OpenAI: python multi_agent_orchestrator.py --llm openai --model gpt-4o
```

### Langfuse Observability Configuration

Both example applications are fully instrumented with Langfuse for end-to-end trace observability. To enable Langfuse telemetry:

1. Create a free account at [Langfuse](https://langfuse.com/) or run it locally.
2. Add your Langfuse credentials to your `.env` file (in the project root or the example directories):
```bash
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_HOST="https://cloud.langfuse.com" # or your local endpoint
```
3. When you run the example applications, a `Langfuse Session ID` will be printed to the console, and you can view the full multi-agent interactions, tool calls, latencies, and LLM reasoning steps in the Langfuse dashboard.

## Configuration

### Basic Configuration

Edit `.env` to customize:

```python
# LLM Models
# TEACHER_MODEL = "gpt-4o"          # For data generation
# EXPANSION_MODEL = "gpt-4o-mini"   # For query expansion
# HEAVY_MODEL = "gpt-4o"            # For tool execution
## I tested the following models locally and they worked well:
TEACHER_MODEL=ollama/granite4.1:8b
EXPANSION_MODEL=ollama/granite4.1:8b
HEAVY_MODEL=ollama/granite4.1:8b

# Data Generation
queries_per_tool = 10             # Queries to generate per tool
num_hard_negatives = 3            # Hard negatives per query

# Training
batch_size = 16                   # Training batch size
num_epochs = 3                    # Training epochs
learning_rate = 2e-5              # Learning rate
```

### Advanced Configuration

For advanced options, see the full documentation in `README.md`.

## Troubleshooting

### Issue: "No MCP servers connected" / MCP Connection Hangs

**Solution**: 
- Check your MCP server configurations in `config.py`
- Ensure MCP server commands are installed (e.g., `npx` for Node.js servers)
- Verify server paths and permissions
- Alternatively, use predefined tools instead. The framework automatically falls back to `data/predefined_tools.json` if available.

### Issue: "Training data not found"

**Solution**: 
- Run Phase 1 first: `python main.py generate` (or `python phase1_generator.py`)
- Check that `data/synthetic_queries.jsonl` exists

### Issue: "Fine-tuned model not found"

**Solution**: 
- Run Phase 2 first: `python main.py train` (or `python phase2_trainer.py`)
- Check that `models/fine_tuned_tool_router/` exists

### Issue: "CUDA out of memory" / Out of Memory During Training

**Solution**: 
- Reduce batch size in `config.py`:
  ```python
  batch_size = 8  # or even 4
  ```
- Use CPU instead: `device: str = "cpu"`
- Use `faiss-cpu` instead of `faiss-gpu`

### Issue: "LLM API errors" / API Rate Limits

**Solution**: 
- Verify API keys in `.env`
- Reduce `queries_per_tool` in `config.py`
- Add delays between API calls
- Try a different model in `config.py` (e.g., use a different provider or a smaller model)

### Issue: Import Errors

**Solution**: Ensure virtual environment is activated and dependencies are installed:
```bash
source venv/bin/activate
pip install -r requirements.txt
```

## Next Steps

1. **Customize Tools**: Add your own tools to `data/predefined_tools.json`
2. **Tune Parameters**: Adjust configuration in `config.py`
3. **Add MCP Servers**: Connect to real MCP servers for production use
4. **Integrate**: Use the framework in your own applications

## Project Structure

```
tool-router/
├── config.py              # Configuration
├── mcp_client.py          # MCP integration
├── phase1_generator.py    # Data generation
├── phase2_trainer.py      # Model training
├── phase3_runtime.py      # Runtime execution
├── data/
│   ├── predefined_tools.json      # Example tools
│   └── synthetic_queries.jsonl    # Generated dataset
├── models/                # Trained models
└── logs/                  # Log files
```

## Getting Help

- **Documentation**: See `README.md` for detailed documentation
- **Examples**: Check `examples/` directory
- **Issues**: Report bugs on GitHub Issues
- **Contributing**: See `CONTRIBUTING.md`

## Resources

- [Full Documentation](README.md)
- [Architecture Overview](docs/ARCHITECTURE.md)
- [API Reference](docs/API.md)
- [Examples](examples/)

---

**Ready to dive deeper?** Check out the [full README](README.md) for comprehensive documentation!