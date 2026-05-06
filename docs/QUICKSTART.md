# ToolRouter - 🚀 Quick Start Guide

Get up and running with ToolRouter in 5 minutes!

## Prerequisites

- Python 3.10+
- pip
- API keys (OpenAI, Anthropic, or Google)

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd neural-tool-router

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Create a `.env` file with your API keys:

```bash
# .env
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
GOOGLE_API_KEY=your_google_key_here
```

Configure MCP servers in [`config.py`](config.py):

```python
servers: Dict[str, Dict[str, Any]] = {
    "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        "transport": "stdio"
    },
    # Add more servers...
}
```

### 3. Three-Phase Execution

#### Phase 1: Generate Synthetic Training Data

```bash
python main.py generate
```

This will:
- Connect to your MCP servers
- Fetch all tool schemas
- Use a Teacher LLM to generate diverse queries
- Create `data/synthetic_queries.jsonl`

**Output**: `data/synthetic_queries.jsonl`, `data/tool_cache.json`

#### Phase 2: Fine-Tune Embedding Model

```bash
python main.py train
```

This will:
- Load the synthetic dataset
- Fine-tune `all-MiniLM-L6-v2` using contrastive learning
- Save the model to `models/fine_tuned_tool_router/`
- Build a FAISS/ChromaDB vector index

**Output**: `models/fine_tuned_tool_router/`, `data/faiss_index.bin`

#### Phase 3: Run the Agentic System

```bash
python main.py run
```

This starts an interactive session where you can query the system:

```
Query: List all files in the /tmp directory

RESULTS:
Retrieved Tools (3):
  - filesystem.list_directory (score: 0.892)
  - filesystem.read_file (score: 0.654)
  - filesystem.get_file_info (score: 0.543)

LLM Reasoning:
The user wants to see the contents of the /tmp directory. I'll use the filesystem.list_directory tool to retrieve this information.

Tool Executions (1):
  ✓ list_directory
    Result: [{"name": "test.txt", "type": "file"}, {"name": "cache", "type": "directory"}...]
```

#### Phase 4: Archive Results

```bash
python main.py archive
```

This cleans up the workspace by archiving the `data/`, `models/`, and `logs/` output into a timestamped folder inside `results/`, allowing you to run all phases again with fresh configurations.

## 📁 Project Structure

```
ToolRouter/
├── ARCHITECTURE.md          # Detailed architecture documentation
├── README.md                # This file
├── requirements.txt         # Python dependencies
├── main.py                  # CLI Entry point
├── tool_router/      # Core package
│   ├── __init__.py
│   ├── config.py            # Configuration module
│   ├── mcp_client.py        # MCP client utility
│   ├── mock_mcp_server.py   # Mock MCP server for testing
│   ├── generator.py         # Synthetic data generation (Phase 1)
│   ├── trainer.py           # Model fine-tuning (Phase 2)
│   ├── runtime.py           # Runtime execution (Phase 3)
│   └── utils/
│       └── archive.py       # Utility to archive results
├── data/                    # Generated data
│   ├── synthetic_queries.jsonl
│   ├── tool_cache.json
│   └── faiss_index.bin
├── models/                  # Trained models
│   └── fine_tuned_tool_router/
├── results/                 # Archived run outputs
└── logs/                    # Execution logs
```

## 🔧 Configuration Options

All configuration is centralized in [`config.py`](config.py). Key settings:

### LLM Configuration

```python
# Teacher LLM (Phase 1)
teacher_model: str = "gpt-4o"
teacher_temperature: float = 0.7

# Query Expansion LLM (Phase 3)
expansion_model: str = "gpt-4o-mini"

# Heavy LLM (Phase 3)
heavy_model: str = "gpt-4o"
```

### Embedding Configuration

```python
# Base model to fine-tune
base_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

# Device
device: str = "cpu"  # or "cuda", "mps"
```

### Vector Store Configuration

```python
# Store type
store_type: str = "faiss"  # or "chromadb"

# Retrieval settings
top_k: int = 3
similarity_threshold: float = 0.5
```

### Training Configuration

```python
batch_size: int = 16
num_epochs: int = 3
learning_rate: float = 2e-5
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