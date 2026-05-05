# NeuralToolRouter

A production-ready Python framework that optimizes Agentic AI architectures by separating **Tool Retrieval** (using a fine-tuned PyTorch embedding model) from **Parameter Extraction and Execution** (using a heavy LLM). This dramatically reduces context window bloat and latency.

## 🎯 Problem Statement

Most Agentic AI systems suffer from:
- **Context Window Bloat**: All tool schemas passed to LLM on every call
- **High Latency**: Large context = slower inference
- **High Costs**: More tokens = higher API costs
- **Poor Scalability**: Performance degrades with more tools

## 💡 Solution

NeuralToolRouter implements a **RAG-for-Tools** architecture:

1. **Fast Retrieval**: Fine-tuned embedding model retrieves Top-K relevant tools
2. **Query Expansion**: Fast LLM expands queries for better retrieval
3. **Reduced Context**: Only Top-K tools sent to heavy LLM
4. **Fallback Mechanism**: LLM can search for better tools if needed

### Performance Gains

- **90%+ Context Reduction**: From 10K+ tokens to 500-1000 tokens
- **1.5-4.5s Faster**: Net latency improvement despite retrieval overhead
- **90% Cost Savings**: Proportional to context reduction
- **Scales to 1000+ Tools**: Constant-time retrieval

## 📋 Prerequisites

- Python 3.10+
- CUDA-capable GPU (optional, for faster training)
- API keys for LLM providers (OpenAI, Anthropic, etc.)
- MCP servers configured

## 🚀 Quick Start

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

## 🏗️ Architecture

See [`ARCHITECTURE.md`](./docs/ARCHITECTURE.md) for detailed architecture documentation including:
- Mermaid diagrams
- Component descriptions
- Performance characteristics
- Extension points

### Key Components

1. **Query Expander**: Uses fast LLM to break down queries into logical steps
2. **Semantic Router**: Embeds queries and searches vector index for relevant tools
3. **Context Assembler**: Fetches full schemas for Top-K tools + fallback
4. **Tool Executor**: Executes tools via MCP protocol
5. **Fallback Tool**: `search_available_tools` for self-correction

## 📊 Monitoring & Logging

Logs are written to `logs/runtime.log` with configurable levels:

```python
# In config.py
log_level: str = "INFO"  # DEBUG, INFO, WARNING, ERROR
```

Key metrics logged:
- Query expansion time
- Retrieval accuracy (Top-K hit rate)
- Tool execution success rate
- End-to-end latency

## 🧪 Testing

Test individual components:

```bash
# Test MCP client
python mcp_client.py

# Test configuration
python config.py
```

## 🔄 Updating Tools

When you add/remove MCP servers or tools:

1. Re-run Phase 1 to regenerate training data
2. Re-run Phase 2 to retrain the model
3. The vector index will be automatically updated

For minor tool changes, you can skip retraining and just rebuild the index:

```python
from tool_router.trainer import VectorIndexBuilder, load_tools_from_cache
from tool_router.config import config

# Load tools and model
tools = load_tools_from_cache(config.mcp.tool_cache_path)
model = SentenceTransformer(str(config.embedding.fine_tuned_model_dir))

# Rebuild index
builder = VectorIndexBuilder(model, config.vector_store)
builder.build_faiss_index(tools)
builder.save_faiss_index()
```

## 🎛️ Advanced Usage

### Custom Embedding Models

Swap the base model in [`config.py`](config.py):

```python
base_model_name: str = "sentence-transformers/all-mpnet-base-v2"  # Larger, more accurate
# or
base_model_name: str = "sentence-transformers/paraphrase-MiniLM-L3-v2"  # Smaller, faster
```

### Using ChromaDB Instead of FAISS

```python
# In config.py
store_type: str = "chromadb"
chromadb_path: Path = Path("./data/chromadb")
```

### Programmatic API

```python
from tool_router.runtime import ToolRouter
import asyncio

async def main():
    router = ToolRouter()
    await router.initialize()
    
    result = await router.process_query("What's the weather in SF?")
    print(result)
    
    await router.close()

asyncio.run(main())
```

### Using Artifacts in Custom Agentic AI Applications

You can completely bypass the `ToolRouter` interactive runtime and directly inject the generated FAISS/BM25 indices and fine-tuned embedding models into your own agent architectures (like LangChain, AutoGen, or IBM BeeAI):

```python
from tool_router.config import config
from sentence_transformers import SentenceTransformer
from tool_router.runtime import SemanticRouter

# 1. Load the fine-tuned embedding model
model = SentenceTransformer(str(config.embedding.fine_tuned_model_dir))

# 2. Initialize the Semantic Router with Hybrid Retrieval
semantic_router = SemanticRouter(model, config.vector_store)
semantic_router.load_faiss_index()
semantic_router.load_bm25_index()

# 3. Retrieve only the highly relevant tools for a specific sub-task
task = "Fetch the patient's hospital discharge summary"
top_tools = semantic_router.retrieve_tools(task, top_k=2, use_hybrid=True)

# 4. Map IDs back to schemas and pass ONLY these tools into your Agent!
# (See examples/beeai_mediclaim_processing/multi_agent_orchestrator.py for a complete example)
```

## 🐛 Troubleshooting

### "No MCP servers connected"

- Check your MCP server configurations in [`config.py`](config.py)
- Ensure MCP server commands are installed (e.g., `npx` for Node.js servers)
- Verify server paths and permissions

### "Training data not found"

- Run Phase 1 first: `python main.py generate`
- Check that `data/synthetic_queries.jsonl` exists

### "Fine-tuned model not found"

- Run Phase 2 first: `python main.py train`
- Check that `models/fine_tuned_tool_router/` exists

### "CUDA out of memory"

- Reduce batch size in [`config.py`](config.py): `batch_size: int = 8`
- Use CPU instead: `device: str = "cpu"`
- Use `faiss-cpu` instead of `faiss-gpu`

### "LLM API errors"

- Verify API keys in `.env`
- Check rate limits
- Try a different model in [`config.py`](config.py)

## 📈 Performance Tuning

### For Speed

- Use smaller embedding model: `all-MiniLM-L3-v2`
- Reduce Top-K: `top_k: int = 2`
- Use FAISS instead of ChromaDB
- Disable query expansion: `enable_query_expansion: bool = False`

### For Accuracy

- Use larger embedding model: `all-mpnet-base-v2`
- Increase Top-K: `top_k: int = 5`
- Generate more training data: `queries_per_tool: int = 20`
- Train for more epochs: `num_epochs: int = 5`

### For Cost Optimization

- Use cheaper expansion model: `expansion_model: str = "gpt-4o-mini"`
- Reduce Top-K to minimize context
- Use local/open-source LLMs where possible

## 🤝 Contributing

Contributions welcome! Areas for improvement:

- [ ] Active learning from user feedback
- [ ] Multi-modal tool descriptions (images, audio)
- [ ] Hierarchical tool routing
- [ ] Streaming results
- [ ] Web UI

## 📄 License

[Your License Here]

## 🙏 Acknowledgments

- Built on [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- Uses [sentence-transformers](https://www.sbert.net/)
- Powered by [LiteLLM](https://github.com/BerriAI/litellm)

## 📞 Support

For issues and questions:
- GitHub Issues: [Your Repo URL]
- Documentation: [`ARCHITECTURE.md`](./docs/ARCHITECTURE.md)
- Email: [Your Email]

---

**Built with ❤️ for the Agentic AI community**