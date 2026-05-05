# Context and Role
You are an Expert AI Architect and Python Backend Developer specializing in Compound AI Systems, PyTorch, and the Model Context Protocol (MCP). Your task is to build an end-to-end Python framework called "ToolRouter". 

# Project Overview
Most Agentic AI architectures suffer from context window bloat and high latency because they pass all available tool schemas into the LLM's context for every call. We are building a framework that solves this by separating *Tool Retrieval* (using a fast, fine-tuned PyTorch embedding model) from *Parameter Extraction and Execution* (using a heavy LLM). 

# Reference Architecture Requirement
Before generating the code, please generate a detailed End-to-End Reference Architecture document (using a Mermaid.js diagram and a text explanation). The architecture must clearly show the flow between the 3 main phases (Data Generation, Model Fine-Tuning, and Runtime Execution), the vector store, the MCP servers, and the LLMs.

# Architectural Principles & Enhancements
The framework MUST implement the following specific architectural patterns:
1. **"RAG for Tools" (Not a static classifier):** Do not build a fixed-class multi-label classifier. Instead, use PyTorch (`sentence-transformers`) to fine-tune an embedding model. Tools are embedded into a Vector DB. At runtime, the user's query is embedded and we do a cosine similarity search to fetch the Top-K tools.
2. **LLM-Assisted Query Expansion ("Think First"):** At runtime, intercept the user query and pass it to a fast/cheap LLM (e.g., Llama-3-8B or GPT-4o-mini) to expand the query into a list of required logical steps before passing it to the embedding model.
3. **Tool-Fetch Fallback:** Always inject a default, permanent tool called `search_available_tools` into the Heavy LLM's context. If the Heavy LLM determines the retrieved Top-K tools are incorrect, it can call this tool to search the registry directly.
4. **MCP Abstraction Layer:** The system should dynamically fetch tool definitions from connected MCP (Model Context Protocol) servers using the `tools/list` protocol upon initialization.

# Technical Stack
- **Language:** Python 3.10+
- **ML Frameworks:** PyTorch, `sentence-transformers` (for MultipleNegativesRankingLoss fine-tuning)
- **Vector Store:** FAISS or ChromaDB
- **LLM Integration:** `litellm` (to easily swap between Google, OpenAI, Anthropic) or raw SDKs.
- **Protocol:** `mcp` (Model Context Protocol Python SDK)

# Step-by-Step Implementation Tasks

Please implement this project by generating the required folder structure and python files for the following 3 phases:

## Phase 1: Synthetic Data Generation (`phase1_generator.py`)
- Create a script that connects to specified MCP servers, pulls all tool schemas (name, description, parameters).
- Use a "Teacher LLM" to generate synthetic user queries that map to these tools. 
- It should generate direct queries, implicit queries, and multi-tool queries.
- Save the output as a JSONL dataset: `{"query": "expanded user query", "positive_tool_id": "tool_name", "hard_negative_tool_ids": ["..."]}` to be used for contrastive learning.

## Phase 2: PyTorch Model Training/Fine-Tuning (`phase2_trainer.py`)
- Write a script that loads a lightweight pre-trained model (e.g., `all-MiniLM-L6-v2`).
- Load the synthetic JSONL dataset.
- Use `sentence-transformers` to fine-tune the model using a contrastive loss function (e.g., `MultipleNegativesRankingLoss`).
- Save the fine-tuned weights to a local `./models/fine_tuned_tool_router/` directory.
- Create an embedding index (FAISS/Chroma) of all current MCP tool descriptions using this fine-tuned model.

## Phase 3: Runtime Agentic Loop (`phase3_runtime.py`)
Implement the main application entry point that processes a user request:
1. **Query Expansion:** Take the user input and use a fast LLM to generate step-by-step required actions.
2. **Semantic Routing:** Pass the expanded query through our fine-tuned local PyTorch embedding model.
3. **Vector Retrieval:** Search the FAISS index to get the Top-K (e.g., K=3) most relevant MCP tool IDs.
4. **Context Assembly:** Fetch the *full* JSON/XML MCP schemas ONLY for those Top-K tools + the permanent `search_available_tools` fallback schema.
5. **Heavy LLM Execution:** Send the original user query + the reduced tool schemas to the main LLM.
6. **Execution:** Parse the LLM's tool-call response and execute the corresponding MCP tool.

## Utilities & Configuration
- Include a `config.py` for easily changing LLM models, Top-K limits, and embedding model paths.
- Include a `mcp_client.py` utility that handles standard MCP connections (Stdio or SSE).
- Provide a `requirements.txt`.

Please begin by outputting the Project Structure and the Mermaid Reference Architecture, followed immediately by the implementation of the Python files. Write robust, production-like code with typing and docstrings.