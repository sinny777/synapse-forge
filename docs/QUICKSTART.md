# ToolRouter - Quick Start Guide

Get up and running with ToolRouter in 5 minutes!

## Prerequisites

- Python 3.10+
- pip
- API keys (OpenAI, Anthropic, or Google)

## Installation

```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env and add your API keys
```

## Configuration

Edit [`config.py`](config.py) to configure your MCP servers:

```python
servers: Dict[str, Dict[str, Any]] = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "transport": "stdio"
    },
    # Add your MCP servers here
}
```

## Run All Phases

### Option 1: Automated (Recommended)

```bash
./run_all.sh
```

This runs all three phases sequentially.

### Option 2: Manual

```bash
# Phase 1: Generate training data
python phase1_generator.py

# Phase 2: Train the model
python phase2_trainer.py

# Phase 3: Run the system
python phase3_runtime.py
```

## Test It Out

Once Phase 3 is running, try these queries:

```
Query: What files are in the /tmp directory?
Query: Create a new file called test.txt
Query: What's the weather in San Francisco?
```

## What's Happening?

1. **Phase 1** connects to your MCP servers and generates synthetic training data
2. **Phase 2** fine-tunes an embedding model and builds a vector index
3. **Phase 3** runs the interactive system where you can query tools

## Next Steps

- Read [`README.md`](README.md) for detailed documentation
- Check [`ARCHITECTURE.md`](ARCHITECTURE.md) for system design
- Customize [`config.py`](config.py) for your use case

## Troubleshooting

### "No MCP servers connected"
- Verify MCP server commands in [`config.py`](config.py)
- Check that required tools are installed (e.g., `npx` for Node.js servers)

### "API key not found"
- Make sure you've created `.env` from `.env.example`
- Add your API keys to `.env`

### "Module not found"
- Activate your virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install -r requirements.txt`

## Example Output

```
Phase 1: Synthetic Data Generation
✓ Connected to 2/2 servers
✓ Generated 100 queries
✓ Saved to data/synthetic_queries.jsonl

Phase 2: Model Training
✓ Loaded 100 training examples
✓ Fine-tuned model saved to models/fine_tuned_tool_router/
✓ Built FAISS index with 10 tools

Phase 3: Runtime
Query: List files in /tmp

Retrieved Tools (3):
  - filesystem.list_directory (score: 0.892)
  - filesystem.read_file (score: 0.654)
  - filesystem.write_file (score: 0.543)

Tool Executions (1):
  ✓ list_directory
    Result: ["file1.txt", "file2.txt", ...]
```

## Performance Tips

- **First run**: Takes 5-10 minutes (data generation + training)
- **Subsequent runs**: Instant (uses cached model and index)
- **To update tools**: Re-run Phase 1 and Phase 2

## Support

- Issues: [GitHub Issues]
- Documentation: [`README.md`](README.md)
- Architecture: [`ARCHITECTURE.md`](ARCHITECTURE.md)

Happy routing! 🚀