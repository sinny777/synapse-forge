# NeuralToolRouter - Quick Start Guide

Get up and running with NeuralToolRouter in 5 minutes!

## Prerequisites

- Python 3.8 or higher
- pip package manager
- API key for at least one LLM provider (OpenAI, Anthropic, or Google)

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
# At minimum, add one of these:
OPENAI_API_KEY=sk-your-key-here
# ANTHROPIC_API_KEY=sk-ant-your-key-here
# GOOGLE_API_KEY=your-key-here
```

## Quick Test Run

### Option 1: Using Predefined Tools (Recommended for First Run)

The framework includes predefined tools for testing without MCP server setup:

```bash
# Phase 1: Generate synthetic training data
python phase1_generator.py

# Phase 2: Train the model (after Phase 1 completes)
python phase2_trainer.py

# Phase 3: Run the agentic loop
python phase3_runtime.py
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

## Example Usage

After completing all phases, you can test the system:

```bash
python phase3_runtime.py
```

Example queries to try:
```
> Show me the contents of config.py
> List all Python files in the current directory
> Search for the word "neural" in all files
> Create a new directory called "test"
```

## Configuration

### Basic Configuration

Edit `config.py` to customize:

```python
# LLM Models
teacher_model = "gpt-4o"          # For data generation
expansion_model = "gpt-4o-mini"   # For query expansion
heavy_model = "gpt-4o"            # For tool execution

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

### Issue: MCP Connection Hangs

**Solution**: Use predefined tools instead. The framework automatically falls back to `data/predefined_tools.json` if available.

### Issue: Out of Memory During Training

**Solution**: Reduce batch size in `config.py`:
```python
batch_size = 8  # or even 4
```

### Issue: API Rate Limits

**Solution**: 
1. Reduce `queries_per_tool` in `config.py`
2. Add delays between API calls
3. Use a different LLM provider

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
neural-tool-router/
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