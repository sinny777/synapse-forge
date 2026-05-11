"""
Phase 3: Runtime Agentic Loop

This module implements the main runtime execution flow:
1. Query Expansion: Use fast LLM to expand user query
2. Semantic Routing: Embed query and search vector index
3. Context Assembly: Fetch Top-K tool schemas + fallback
4. Heavy LLM Execution: Generate tool calls
5. Tool Execution: Execute via MCP and return results
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import numpy as np

from sentence_transformers import SentenceTransformer
from litellm import completion

from tool_router.config import config, RuntimeConfig, LLMConfig, EmbeddingConfig, VectorStoreConfig
from tool_router.mcp_client import MCPClient, ToolSchema

# Configure logging
logging.basicConfig(
    level=getattr(config.runtime, 'log_level', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class QueryExpander:
    """Expands user queries using a fast LLM to improve retrieval."""
    
    def __init__(self, llm_config: LLMConfig, runtime_config: RuntimeConfig):
        """
        Initialize query expander.
        
        Args:
            llm_config: LLM configuration
            runtime_config: Runtime configuration
        """
        self.llm_config = llm_config
        self.runtime_config = runtime_config
    
    async def expand_query(self, user_query: str) -> str:
        """
        Expand user query into logical steps.
        
        Args:
            user_query: Original user query
        
        Returns:
            Expanded query with logical steps
        """
        if not self.runtime_config.enable_query_expansion:
            return user_query
        
        try:
            from litellm import acompletion
            prompt = self.runtime_config.expansion_prompt_template.format(query=user_query)
            
            response = await acompletion(
                model=self.llm_config.expansion_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.llm_config.expansion_temperature,
                max_tokens=self.llm_config.expansion_max_tokens
            )
            
            expanded = response.choices[0].message.content.strip()
            logger.info(f"Query expanded: {user_query[:50]}... -> {expanded[:100]}...")
            
            # Combine original query with expansion
            return f"{user_query}\n\nLogical steps:\n{expanded}"
            
        except Exception as e:
            logger.error(f"Query expansion failed: {e}")
            return user_query

    async def expand_query_stream(self, user_query: str):
        """
        Expand user query into logical steps, yielding chunks.
        """
        if not self.runtime_config.enable_query_expansion:
            yield user_query
            return
            
        try:
            from litellm import acompletion
            prompt = self.runtime_config.expansion_prompt_template.format(query=user_query)
            
            response = await acompletion(
                model=self.llm_config.expansion_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.llm_config.expansion_temperature,
                max_tokens=self.llm_config.expansion_max_tokens,
                stream=True
            )
            
            yield f"{user_query}\n\nLogical steps:\n"
            
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                yield delta
                
        except Exception as e:
            logger.error(f"Query expansion stream failed: {e}")
            yield user_query



class SemanticRouter:
    """Routes queries to relevant tools using embedding similarity."""
    
    def __init__(
        self,
        model: SentenceTransformer,
        vector_config: VectorStoreConfig
    ):
        """
        Initialize semantic router.
        
        Args:
            model: Fine-tuned embedding model
            vector_config: Vector store configuration
        """
        self.model = model
        self.vector_config = vector_config
        self.index = None
        self.tool_ids: List[str] = []
        self.chromadb_collection = None
        self.bm25_index = None
        self.bm25_tool_ids: List[str] = []
    
    def load_bm25_index(self):
        """Load BM25 index from disk."""
        import pickle
        
        bm25_path = self.vector_config.faiss_index_path.parent / "bm25_index.pkl"
        mapping_path = bm25_path.with_suffix('.json')
        
        logger.info(f"Loading BM25 index from {bm25_path}")
        
        # Load BM25 index
        with open(bm25_path, 'rb') as f:
            self.bm25_index = pickle.load(f)
        
        # Load tool IDs
        with open(mapping_path, 'r') as f:
            data = json.load(f)
            self.bm25_tool_ids = data["tool_ids"]
        
        logger.info(f"Loaded BM25 index with {len(self.bm25_tool_ids)} tools")
    
    def load_faiss_index(self):
        """Load FAISS index from disk."""
        import faiss
        
        index_path = self.vector_config.faiss_index_path
        mapping_path = index_path.with_suffix('.json')
        
        logger.info(f"Loading FAISS index from {index_path}")
        
        self.index = faiss.read_index(str(index_path))
        
        with open(mapping_path, 'r') as f:
            data = json.load(f)
            self.tool_ids = data["tool_ids"]
        
        logger.info(f"Loaded FAISS index with {self.index.ntotal} tools")
    
    def load_chromadb_collection(self):
        """Load ChromaDB collection."""
        import chromadb
        from chromadb.config import Settings
        
        logger.info(f"Loading ChromaDB from {self.vector_config.chromadb_path}")
        
        client = chromadb.PersistentClient(
            path=str(self.vector_config.chromadb_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        self.chromadb_collection = client.get_collection(
            name=self.vector_config.chromadb_collection_name
        )
        
        logger.info(f"Loaded ChromaDB collection: {self.chromadb_collection.name}")
    
    def retrieve_tools_faiss(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """
        Retrieve top-k tools using FAISS.
        
        Args:
            query: Query text
            top_k: Number of tools to retrieve
        
        Returns:
            List of (tool_id, similarity_score) tuples
        """
        import faiss
        
        # Embed query
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        
        # Normalize for cosine similarity
        faiss.normalize_L2(query_embedding)
        
        # Search index
        scores, indices = self.index.search(query_embedding, top_k)
        
        # Get tool IDs and scores
        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < len(self.tool_ids):
                tool_id = self.tool_ids[idx]
                results.append((tool_id, float(score)))
        
        return results
    
    def retrieve_tools_chromadb(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """
        Retrieve top-k tools using ChromaDB.
        
        Args:
            query: Query text
            top_k: Number of tools to retrieve
        
        Returns:
            List of (tool_id, similarity_score) tuples
        """
        # Embed query
        query_embedding = self.model.encode([query], convert_to_numpy=True)
        
        # Query collection
        results = self.chromadb_collection.query(
            query_embeddings=query_embedding.tolist(),
            n_results=top_k
        )
        
        # Extract tool IDs and distances (convert to similarity)
        tool_results = []
        for tool_id, distance in zip(results['ids'][0], results['distances'][0]):
            # Convert distance to similarity (assuming cosine distance)
            similarity = 1 - distance
            tool_results.append((tool_id, similarity))
        
        return tool_results
    
    def retrieve_tools_bm25(self, query: str, top_k: int) -> List[Tuple[str, float]]:
        """
        Retrieve top-k tools using BM25 sparse retrieval.
        
        Args:
            query: Query text
            top_k: Number of tools to retrieve
        
        Returns:
            List of (tool_id, bm25_score) tuples
        """
        if self.bm25_index is None:
            raise ValueError("BM25 index not loaded. Call load_bm25_index() first.")
        
        # Tokenize query
        tokenized_query = query.lower().split()
        
        # Get BM25 scores
        scores = self.bm25_index.get_scores(tokenized_query)
        
        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        
        # Build results
        results = []
        for idx in top_indices:
            if idx < len(self.bm25_tool_ids):
                tool_id = self.bm25_tool_ids[idx]
                score = float(scores[idx])
                results.append((tool_id, score))
        
        return results
    
    def reciprocal_rank_fusion(
        self,
        dense_results: List[Tuple[str, float]],
        sparse_results: List[Tuple[str, float]],
        k: int = 60
    ) -> List[Tuple[str, float]]:
        """
        Combine dense and sparse retrieval results using Reciprocal Rank Fusion (RRF).
        
        RRF formula: score(d) = sum(1 / (k + rank(d)))
        
        Args:
            dense_results: Results from dense retrieval (FAISS/ChromaDB)
            sparse_results: Results from sparse retrieval (BM25)
            k: Constant for RRF (default: 60)
        
        Returns:
            Combined and re-ranked results
        """
        # Build rank dictionaries
        rrf_scores = {}
        
        # Add dense retrieval scores
        for rank, (tool_id, _) in enumerate(dense_results, start=1):
            rrf_scores[tool_id] = rrf_scores.get(tool_id, 0) + (1.0 / (k + rank))
        
        # Add sparse retrieval scores
        for rank, (tool_id, _) in enumerate(sparse_results, start=1):
            rrf_scores[tool_id] = rrf_scores.get(tool_id, 0) + (1.0 / (k + rank))
        
        # Sort by RRF score
        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        return sorted_results
    
    def retrieve_tools_hybrid(self, query: str, top_k: Optional[int] = None) -> List[Tuple[str, float]]:
        """
        Retrieve tools using hybrid search (Dense + BM25 with RRF).
        
        Args:
            query: Query text
            top_k: Number of tools to retrieve (default from config)
        
        Returns:
            List of (tool_id, rrf_score) tuples
        """
        if top_k is None:
            top_k = self.vector_config.top_k
        
        logger.info(f"Hybrid retrieval: Fetching top-{top_k * 2} from each retriever...")
        
        # Retrieve from dense index (fetch more for better fusion)
        if self.vector_config.store_type == "faiss":
            dense_results = self.retrieve_tools_faiss(query, top_k * 2)
        elif self.vector_config.store_type == "chromadb":
            dense_results = self.retrieve_tools_chromadb(query, top_k * 2)
        else:
            raise ValueError(f"Unsupported vector store: {self.vector_config.store_type}")
        
        # Retrieve from BM25 index
        sparse_results = self.retrieve_tools_bm25(query, top_k * 2)
        
        # Combine using RRF
        logger.info("Applying Reciprocal Rank Fusion...")
        fused_results = self.reciprocal_rank_fusion(dense_results, sparse_results)
        
        # Return top-k
        return fused_results[:top_k]
    
    def retrieve_tools(self, query: str, top_k: Optional[int] = None, use_hybrid: bool = True, apply_threshold: bool = True) -> List[Tuple[str, float]]:
        """
        Retrieve top-k relevant tools for a query.
        
        Args:
            query: Query text
            top_k: Number of tools to retrieve (default from config)
            use_hybrid: Whether to use hybrid search
            apply_threshold: Whether to filter by similarity threshold
        
        Returns:
            List of (tool_id, similarity_score) tuples
        """
        if top_k is None:
            top_k = self.vector_config.top_k
        
        logger.info(f"Retrieving top-{top_k} tools for query: {query[:100]}...")
        
        is_hybrid = False
        if use_hybrid and self.bm25_index is not None:
            results = self.retrieve_tools_hybrid(query, top_k)
            is_hybrid = True
        elif self.vector_config.store_type == "faiss":
            results = self.retrieve_tools_faiss(query, top_k)
        elif self.vector_config.store_type == "chromadb":
            results = self.retrieve_tools_chromadb(query, top_k)
        else:
            raise ValueError(f"Unsupported vector store: {self.vector_config.store_type}")
        
        # Don't apply threshold to hybrid results because RRF scores are rank-based (~0.01 to 0.03)
        # and do not match the cosine similarity threshold (e.g., 0.3).
        if apply_threshold and not is_hybrid:
            # Filter by similarity threshold
            filtered_results = [
                (tool_id, score) for tool_id, score in results
                if score >= self.vector_config.similarity_threshold
            ]
            logger.info(f"Retrieved {len(filtered_results)} tools above threshold {self.vector_config.similarity_threshold}")
        else:
            filtered_results = results
            logger.info(f"Retrieved {len(filtered_results)} tools (threshold not applied)")
            
        for tool_id, score in filtered_results:
            logger.debug(f"  {tool_id}: {score:.3f}")
        
        return filtered_results


class ToolExecutor:
    """Executes tool calls via MCP."""
    
    def __init__(self, mcp_client: MCPClient, runtime_config: RuntimeConfig):
        """
        Initialize tool executor.
        
        Args:
            mcp_client: Connected MCP client
            runtime_config: Runtime configuration
        """
        self.mcp_client = mcp_client
        self.runtime_config = runtime_config
    
    async def execute_tool(self, tool_id: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single tool.
        
        Args:
            tool_id: Tool identifier
            arguments: Tool arguments
        
        Returns:
            Execution result
        """
        logger.info(f"Executing tool: {tool_id}")
        
        try:
            result = await asyncio.wait_for(
                self.mcp_client.call_tool(tool_id, arguments),
                timeout=self.runtime_config.tool_call_timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.error(f"Tool execution timeout: {tool_id}")
            return {
                "tool_id": tool_id,
                "success": False,
                "error": "Execution timeout"
            }
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_id} - {e}")
            return {
                "tool_id": tool_id,
                "success": False,
                "error": str(e)
            }


class ToolRouter:
    """
    Main runtime system that orchestrates the entire flow.
    """
    
    def __init__(self):
        """Initialize the ToolRouter system."""
        self.query_expander = QueryExpander(config.llm, config.runtime)
        self.semantic_router: Optional[SemanticRouter] = None
        self.mcp_client: Optional[MCPClient] = None
        self.tool_executor: Optional[ToolExecutor] = None
        self.embedding_model: Optional[SentenceTransformer] = None
    
    async def initialize(self):
        """Initialize all components."""
        logger.info("Initializing ToolRouter...")
        
        # Load embedding model
        logger.info("Loading fine-tuned embedding model...")
        self.embedding_model = SentenceTransformer(
            str(config.embedding.fine_tuned_model_dir),
            device=config.embedding.device
        )
        
        # Initialize semantic router
        logger.info("Initializing semantic router...")
        self.semantic_router = SemanticRouter(self.embedding_model, config.vector_store)
        
        if config.vector_store.store_type == "faiss":
            self.semantic_router.load_faiss_index()
        elif config.vector_store.store_type == "chromadb":
            self.semantic_router.load_chromadb_collection()
        
        # Load BM25 index for hybrid retrieval
        try:
            logger.info("Loading BM25 index for hybrid retrieval...")
            self.semantic_router.load_bm25_index()
        except FileNotFoundError:
            logger.warning("BM25 index not found. Hybrid retrieval will not be available. Run phase2_trainer.py to build it.")
        
        # Connect to MCP servers
        logger.info("Connecting to MCP servers...")
        self.mcp_client = MCPClient(config.mcp)
        await self.mcp_client.connect_all()
        await self.mcp_client.list_tools()
        
        # Initialize tool executor
        self.tool_executor = ToolExecutor(self.mcp_client, config.runtime)
        
        logger.info("✓ ToolRouter initialized successfully")
    
    def _create_fallback_tool_schema(self) -> Dict[str, Any]:
        """Create the search_available_tools fallback tool schema."""
        return {
            "name": "search_available_tools",
            "description": "Search for available tools by keyword. Use this if the provided tools don't match your needs.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for finding tools"
                    }
                },
                "required": ["query"]
            }
        }
    
    def _assemble_context(self, tool_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Assemble tool schemas for LLM context.
        
        Args:
            tool_ids: List of tool IDs to include
        
        Returns:
            List of tool schemas
        """
        schemas = []
        
        # Add retrieved tools
        for tool_id in tool_ids:
            tool_schema = self.mcp_client.tools.get(tool_id)
            if tool_schema:
                schemas.append(tool_schema.raw_schema)
        
        # Add fallback tool
        if config.runtime.enable_fallback_tool:
            schemas.append(self._create_fallback_tool_schema())
        
        return schemas
    
    async def _call_heavy_llm(self, user_query: str, tool_schemas: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Call the heavy LLM to generate tool calls.
        
        Args:
            user_query: Original user query
            tool_schemas: Available tool schemas
        
        Returns:
            LLM response with tool calls
        """
        system_prompt = """You are a helpful AI assistant with access to tools. 
Analyze the user's request and determine which tool(s) to use.
If the available tools don't match the user's needs, use the search_available_tools function to find better options.

Respond with tool calls in JSON format:
{
  "tool_calls": [
    {
      "tool_name": "tool_name",
      "arguments": {...}
    }
  ],
  "reasoning": "Brief explanation of your choice"
}
"""
        
        tools_text = json.dumps(tool_schemas, indent=2)
        user_message = f"""User Query: {user_query}

Available Tools:
{tools_text}

What tool(s) should be called to fulfill this request?"""
        
        try:
            from litellm import acompletion
            response = await acompletion(
                model=config.llm.heavy_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=config.llm.heavy_temperature,
                max_tokens=config.llm.heavy_max_tokens
            )
            
            content = response.choices[0].message.content.strip()
            
            # Try to parse JSON response
            try:
                # Extract JSON from markdown code blocks if present
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                return json.loads(content)
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON")
                return {
                    "tool_calls": [],
                    "reasoning": content
                }
        
        except Exception as e:
            logger.error(f"Heavy LLM call failed: {e}")
            return {
                "tool_calls": [],
                "reasoning": f"Error: {str(e)}"
            }
            
    async def _call_heavy_llm_stream(self, user_query: str, tool_schemas: List[Dict[str, Any]]):
        """Call heavy LLM and yield chunks."""
        system_prompt = """You are a helpful AI assistant with access to tools. 
Analyze the user's request and determine which tool(s) to use.
If the available tools don't match the user's needs, use the search_available_tools function to find better options.

Respond with tool calls in JSON format:
{
  "tool_calls": [
    {
      "tool_name": "tool_name",
      "arguments": {...}
    }
  ],
  "reasoning": "Brief explanation of your choice"
}
"""
        tools_text = json.dumps(tool_schemas, indent=2)
        user_message = f"""User Query: {user_query}

Available Tools:
{tools_text}

What tool(s) should be called to fulfill this request?"""
        
        try:
            from litellm import acompletion
            response = await acompletion(
                model=config.llm.heavy_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=config.llm.heavy_temperature,
                max_tokens=config.llm.heavy_max_tokens,
                stream=True
            )
            
            async for chunk in response:
                delta = chunk.choices[0].delta.content or ""
                yield delta
        except Exception as e:
            logger.error(f"Heavy LLM stream failed: {e}")
            yield f'{{"reasoning": "Error: {str(e)}", "tool_calls": []}}'
    
    async def process_query(self, user_query: str) -> Dict[str, Any]:
        """
        Process a user query end-to-end.
        
        Args:
            user_query: User's input query
        
        Returns:
            Processing result with tool outputs
        """
        logger.info("=" * 60)
        logger.info(f"Processing query: {user_query}")
        logger.info("=" * 60)
        
        import time
        start_time = time.time()
        
        # Step 1: Query Expansion
        logger.info("\n[1/5] Query Expansion")
        t0 = time.time()
        expanded_query = await self.query_expander.expand_query(user_query)
        expansion_time = time.time() - t0
        
        # Step 2: Semantic Routing
        logger.info("\n[2/5] Semantic Routing")
        t0 = time.time()
        retrieved_tools = self.semantic_router.retrieve_tools(expanded_query)
        tool_ids = [tool_id for tool_id, _ in retrieved_tools]
        routing_time = time.time() - t0
        
        # Step 3: Context Assembly
        logger.info("\n[3/5] Context Assembly")
        t0 = time.time()
        tool_schemas = self._assemble_context(tool_ids)
        logger.info(f"Assembled context with {len(tool_schemas)} tools")
        context_assembly_time = time.time() - t0
        
        # Step 4: Heavy LLM Execution
        logger.info("\n[4/5] Heavy LLM Execution")
        t0 = time.time()
        llm_response = await self._call_heavy_llm(user_query, tool_schemas)
        logger.info(f"LLM Reasoning: {llm_response.get('reasoning', 'N/A')}")
        llm_time = time.time() - t0
        
        # Step 5: Tool Execution
        logger.info("\n[5/5] Tool Execution")
        results = []
        
        tool_calls = llm_response.get("tool_calls", [])
        for i, tool_call in enumerate(tool_calls[:config.runtime.max_tool_calls]):
            tool_name = tool_call.get("tool_name")
            arguments = tool_call.get("arguments", {})
            
            # Handle fallback tool
            if tool_name == "search_available_tools":
                search_query = arguments.get("query", "")
                logger.info(f"Fallback tool called with query: {search_query}")
                matches = await self.mcp_client.search_tools(search_query)
                results.append({
                    "tool_name": tool_name,
                    "success": True,
                    "result": [{"id": t.id, "name": t.name, "description": t.description} for t in matches]
                })
            else:
                # Find full tool ID
                tool_id = None
                for tid in tool_ids:
                    if tid.endswith(f".{tool_name}") or tid == tool_name:
                        tool_id = tid
                        break
                
                if tool_id:
                    t0_tool = time.time()
                    result = await self.tool_executor.execute_tool(tool_id, arguments)
                    tool_exec_time = time.time() - t0_tool
                    results.append({
                        "tool_name": tool_name,
                        "tool_id": tool_id,
                        "time_taken": tool_exec_time,
                        **result
                    })
                else:
                    logger.warning(f"Tool not found: {tool_name}")
                    results.append({
                        "tool_name": tool_name,
                        "success": False,
                        "time_taken": 0,
                        "error": "Tool not found in retrieved set"
                    })
        
        total_time = time.time() - start_time
        logger.info("\n" + "=" * 60)
        logger.info(f"Query processing complete in {total_time:.2f}s")
        logger.info("=" * 60)
        
        # Enrich retrieved tools with complete metadata
        enriched_tools = []
        for tid, score in retrieved_tools:
            tool_schema = self.mcp_client.tools.get(tid)
            if tool_schema:
                enriched_tools.append({
                    "id": tid,
                    "score": score,
                    "name": tool_schema.name,
                    "description": tool_schema.description,
                    "server_name": tool_schema.server_name,
                    "parameters": tool_schema.parameters,
                    "input_schema": tool_schema.raw_schema.get("inputSchema", {}),
                    "output_format": tool_schema.raw_schema.get("outputFormat", "Tool execution result")
                })
            else:
                # Fallback if tool schema not found
                enriched_tools.append({
                    "id": tid,
                    "score": score,
                    "name": tid.split('.')[-1] if '.' in tid else tid,
                    "description": "Tool metadata not available",
                    "server_name": "unknown",
                    "parameters": {},
                    "input_schema": {},
                    "output_format": "Tool execution result"
                })
        
        return {
            "query": user_query,
            "expanded_query": expanded_query,
            "retrieved_tools": enriched_tools,
            "llm_reasoning": llm_response.get("reasoning"),
            "tool_results": results,
            "timings": {
                "total_time": total_time,
                "expansion_time": expansion_time,
                "routing_time": routing_time,
                "context_assembly_time": context_assembly_time,
                "llm_time": llm_time
            }
        }
        
    async def process_query_stream(self, user_query: str):
        """
        Process a user query end-to-end and yield events for streaming.
        
        Args:
            user_query: User's input query
        """
        import time
        start_time = time.time()
        
        # We'll build the final result as we go to yield it at the end if needed,
        # but the primary output is the stream of events.
        timings = {}
        
        # Start event
        yield json.dumps({"event": "start", "data": {"query": user_query}}) + "\n"
        
        # Step 1: Query Expansion
        t0 = time.time()
        expanded_query = ""
        async for chunk in self.query_expander.expand_query_stream(user_query):
            expanded_query += chunk
            yield json.dumps({"event": "expansion_stream", "data": {"chunk": chunk}}) + "\n"
            
        expansion_time = time.time() - t0
        timings["expansion_time"] = expansion_time
        
        yield json.dumps({"event": "expansion", "data": {
            "expanded_query": expanded_query, 
            "time": expansion_time
        }}) + "\n"
        
        # Step 2: Semantic Routing
        t0 = time.time()
        retrieved_tools = self.semantic_router.retrieve_tools(expanded_query)
        tool_ids = [tool_id for tool_id, _ in retrieved_tools]
        routing_time = time.time() - t0
        timings["routing_time"] = routing_time
        
        # Enrich retrieved tools with complete metadata for streaming
        enriched_tools = []
        for tid, score in retrieved_tools:
            tool_schema = self.mcp_client.tools.get(tid)
            if tool_schema:
                enriched_tools.append({
                    "id": tid,
                    "score": score,
                    "name": tool_schema.name,
                    "description": tool_schema.description,
                    "server_name": tool_schema.server_name,
                    "parameters": tool_schema.parameters,
                    "input_schema": tool_schema.raw_schema.get("inputSchema", {}),
                    "output_format": tool_schema.raw_schema.get("outputFormat", "Tool execution result")
                })
            else:
                enriched_tools.append({
                    "id": tid,
                    "score": score,
                    "name": tid.split('.')[-1] if '.' in tid else tid,
                    "description": "Tool metadata not available",
                    "server_name": "unknown",
                    "parameters": {},
                    "input_schema": {},
                    "output_format": "Tool execution result"
                })
        
        yield json.dumps({"event": "routing", "data": {
            "retrieved_tools": enriched_tools,
            "time": routing_time
        }}) + "\n"
        
        # Step 3: Context Assembly
        t0 = time.time()
        tool_schemas = self._assemble_context(tool_ids)
        context_assembly_time = time.time() - t0
        timings["context_assembly_time"] = context_assembly_time
        
        # Step 4: Heavy LLM Execution
        t0 = time.time()
        llm_content = ""
        async for chunk in self._call_heavy_llm_stream(user_query, tool_schemas):
            llm_content += chunk
            yield json.dumps({"event": "reasoning_stream", "data": {"chunk": chunk}}) + "\n"
            
        try:
            content = llm_content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            llm_response = json.loads(content)
        except json.JSONDecodeError:
            llm_response = {
                "tool_calls": [],
                "reasoning": llm_content
            }
            
        llm_time = time.time() - t0
        timings["llm_time"] = llm_time
        
        yield json.dumps({"event": "reasoning", "data": {
            "llm_reasoning": llm_response.get("reasoning"),
            "tool_calls": llm_response.get("tool_calls", []),
            "time": llm_time
        }}) + "\n"
        
        # Step 5: Tool Execution
        results = []
        tool_calls = llm_response.get("tool_calls", [])
        
        for i, tool_call in enumerate(tool_calls[:config.runtime.max_tool_calls]):
            tool_name = tool_call.get("tool_name")
            arguments = tool_call.get("arguments", {})
            
            # Handle fallback tool
            if tool_name == "search_available_tools":
                search_query = arguments.get("query", "")
                matches = await self.mcp_client.search_tools(search_query)
                tool_res = {
                    "tool_name": tool_name,
                    "success": True,
                    "time_taken": 0,
                    "result": [{"id": t.id, "name": t.name, "description": t.description} for t in matches]
                }
                results.append(tool_res)
                yield json.dumps({"event": "tool_execution", "data": tool_res}) + "\n"
            else:
                # Find full tool ID
                tool_id = None
                for tid in tool_ids:
                    if tid.endswith(f".{tool_name}") or tid == tool_name:
                        tool_id = tid
                        break
                
                if tool_id:
                    t0_tool = time.time()
                    result = await self.tool_executor.execute_tool(tool_id, arguments)
                    tool_exec_time = time.time() - t0_tool
                    tool_res = {
                        "tool_name": tool_name,
                        "tool_id": tool_id,
                        "time_taken": tool_exec_time,
                        **result
                    }
                    results.append(tool_res)
                    yield json.dumps({"event": "tool_execution", "data": tool_res}) + "\n"
                else:
                    tool_res = {
                        "tool_name": tool_name,
                        "success": False,
                        "time_taken": 0,
                        "error": "Tool not found in retrieved set"
                    }
                    results.append(tool_res)
                    yield json.dumps({"event": "tool_execution", "data": tool_res}) + "\n"
        
        total_time = time.time() - start_time
        timings["total_time"] = total_time
        
        yield json.dumps({"event": "complete", "data": {
            "timings": timings,
            "total_time": total_time
        }}) + "\n"
    
    async def close(self):
        """Clean up resources."""
        if self.mcp_client:
            await self.mcp_client.close_all()
        logger.info("ToolRouter closed")


async def main():
    """Main execution function for interactive mode."""
    # Initialize router
    router = ToolRouter()
    await router.initialize()
    
    print("\n" + "=" * 60)
    print("ToolRouter - Interactive Mode")
    print("=" * 60)
    print("Enter your queries (or 'quit' to exit)\n")
    
    try:
        while True:
            user_input = input("\nQuery: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                break
            
            if not user_input:
                continue
            
            # Process query
            result = await router.process_query(user_input)
            
            # Display results
            print("\n" + "-" * 60)
            print("RESULTS:")
            print("-" * 60)
            
            print(f"\nRetrieved Tools ({len(result['retrieved_tools'])}):")
            for tool_info in result['retrieved_tools']:
                print(f"  - {tool_info['id']} (score: {tool_info['score']:.3f})")
            
            print(f"\nLLM Reasoning:\n{result['llm_reasoning']}")
            
            print(f"\nTool Executions ({len(result['tool_results'])}):")
            for tool_result in result['tool_results']:
                status = "✓" if tool_result.get('success') else "✗"
                print(f"  {status} {tool_result['tool_name']}")
                if tool_result.get('success'):
                    print(f"    Result: {json.dumps(tool_result.get('content', []), indent=6)[:200]}...")
                else:
                    print(f"    Error: {tool_result.get('error')}")
    
    finally:
        await router.close()
        print("\nGoodbye!")


if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
