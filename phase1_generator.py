"""
Phase 1: Synthetic Data Generation

This module generates synthetic training data by:
1. Connecting to MCP servers and collecting tool schemas
2. Using a Teacher LLM to generate diverse queries for each tool
3. Creating contrastive learning pairs (positive + hard negatives)
4. Saving the dataset in JSONL format for training
"""

import asyncio
import json
import logging
from typing import List, Dict, Any, Tuple
from pathlib import Path
import random
from dataclasses import dataclass

from litellm import completion
from tqdm import tqdm

from config import config, DataGenerationConfig, LLMConfig
from mcp_client import MCPClient, ToolSchema

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SyntheticQuery:
    """Represents a synthetic query with its target tool and negatives."""
    
    query: str
    positive_tool_id: str
    hard_negative_tool_ids: List[str]
    query_type: str  # "direct", "implicit", or "multi_tool"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSONL output."""
        return {
            "query": self.query,
            "positive_tool_id": self.positive_tool_id,
            "hard_negative_tool_ids": self.hard_negative_tool_ids,
            "query_type": self.query_type
        }


class SyntheticDataGenerator:
    """
    Generates synthetic training data for tool retrieval.
    Uses a Teacher LLM to create diverse, realistic queries.
    """
    
    def __init__(
        self,
        mcp_client: MCPClient,
        llm_config: LLMConfig,
        data_config: DataGenerationConfig
    ):
        """
        Initialize the generator.
        
        Args:
            mcp_client: Connected MCP client
            llm_config: LLM configuration
            data_config: Data generation configuration
        """
        self.mcp_client = mcp_client
        self.llm_config = llm_config
        self.data_config = data_config
        self.all_tools: List[ToolSchema] = []
    
    async def initialize(self):
        """Initialize by fetching all available tools."""
        logger.info("Fetching available tools...")
        self.all_tools = self.mcp_client.get_all_tools()
        logger.info(f"Found {len(self.all_tools)} tools")
    
    def _call_teacher_llm(self, prompt: str) -> str:
        """
        Call the Teacher LLM with a prompt.
        
        Args:
            prompt: Input prompt
        
        Returns:
            LLM response text
        """
        try:
            response = completion(
                model=self.llm_config.teacher_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.llm_config.teacher_temperature,
                max_tokens=self.llm_config.teacher_max_tokens
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""
    
    def _generate_direct_query(self, tool: ToolSchema) -> str:
        """
        Generate a direct, straightforward query for a tool.
        
        Args:
            tool: Tool schema
        
        Returns:
            Generated query
        """
        prompt = f"""Generate a direct, straightforward user query that would require using this tool:

Tool Name: {tool.name}
Description: {tool.description}
Parameters: {json.dumps(tool.parameters.get('properties', {}), indent=2)}

Generate ONE realistic user query that directly asks for this tool's functionality.
Output only the query, nothing else.

Example format: "What's the weather in San Francisco?"
"""
        return self._call_teacher_llm(prompt)
    
    def _generate_implicit_query(self, tool: ToolSchema) -> str:
        """
        Generate an implicit query that implies tool usage without directly asking.
        
        Args:
            tool: Tool schema
        
        Returns:
            Generated query
        """
        prompt = f"""Generate an implicit, natural language query that would require using this tool, but doesn't directly mention it:

Tool Name: {tool.name}
Description: {tool.description}
Parameters: {json.dumps(tool.parameters.get('properties', {}), indent=2)}

Generate ONE realistic user query that implies needing this tool without explicitly asking for it.
The query should be conversational and natural.
Output only the query, nothing else.

Example format: "I'm planning a picnic tomorrow, should I bring an umbrella?"
"""
        return self._call_teacher_llm(prompt)
    
    def _generate_multi_tool_query(self, primary_tool: ToolSchema, related_tools: List[ToolSchema]) -> str:
        """
        Generate a complex query that might require multiple tools.
        
        Args:
            primary_tool: Primary tool for this query
            related_tools: Other related tools
        
        Returns:
            Generated query
        """
        tools_context = f"Primary Tool: {primary_tool.name} - {primary_tool.description}\n"
        tools_context += "Related Tools:\n"
        for tool in related_tools[:2]:  # Include up to 2 related tools
            tools_context += f"  - {tool.name}: {tool.description}\n"
        
        prompt = f"""Generate a complex user query that would primarily require the main tool, but might also involve related tools:

{tools_context}

Generate ONE realistic, complex user query that would need the primary tool as the main solution.
The query should be multi-step or involve multiple aspects.
Output only the query, nothing else.

Example format: "I need to check the weather for my trip next week and also find good restaurants in that area"
"""
        return self._call_teacher_llm(prompt)
    
    def _select_hard_negatives_llm(
        self,
        query: str,
        positive_tool: ToolSchema,
        num_negatives: int
    ) -> List[str]:
        """
        Use Teacher LLM to select hard negative tools that are conceptually similar
        but fundamentally wrong for the query.
        
        Args:
            query: The user query
            positive_tool: The correct tool
            num_negatives: Number of negatives to select
        
        Returns:
            List of negative tool IDs
        """
        # Get candidate tools (exclude the positive tool)
        candidate_tools = [t for t in self.all_tools if t.id != positive_tool.id]
        
        # If we have few tools, use heuristic fallback
        if len(candidate_tools) < num_negatives * 2:
            return self._select_hard_negatives_heuristic(positive_tool, num_negatives)
        
        # Sample a larger pool for LLM to choose from
        sample_size = min(20, len(candidate_tools))
        sampled_tools = random.sample(candidate_tools, sample_size)
        
        # Build tool list for LLM
        tools_text = ""
        for i, tool in enumerate(sampled_tools, 1):
            tools_text += f"{i}. {tool.id}\n   Name: {tool.name}\n   Description: {tool.description}\n\n"
        
        prompt = f"""You are an expert at identifying "hard negative" examples for machine learning training.

Given a user query and the CORRECT tool, identify {num_negatives} "hard negative" tools from the list below.

**Definition of Hard Negative:** A tool that sounds conceptually related or similar to what the user needs, but is fundamentally the WRONG tool to use. These are tools that might confuse a model during training.

**User Query:** {query}

**Correct Tool:** {positive_tool.id}
- Name: {positive_tool.name}
- Description: {positive_tool.description}

**Candidate Tools:**
{tools_text}

**Task:** Select exactly {num_negatives} hard negative tool IDs that:
1. Sound related to the query or correct tool
2. But would be WRONG to use for this query
3. Would be confusing/challenging for a model to distinguish

Output ONLY the tool IDs, one per line, nothing else.
Example output format:
server.tool_name_1
server.tool_name_2
server.tool_name_3
"""
        
        try:
            response = self._call_teacher_llm(prompt)
            
            # Parse tool IDs from response
            lines = [line.strip() for line in response.split('\n') if line.strip()]
            selected_ids = []
            
            for line in lines:
                # Extract tool ID (handle various formats)
                tool_id = line.strip()
                # Check if it's a valid tool ID from our candidates
                if any(t.id == tool_id for t in sampled_tools):
                    selected_ids.append(tool_id)
                    if len(selected_ids) >= num_negatives:
                        break
            
            # If LLM didn't return enough, fall back to heuristic
            if len(selected_ids) < num_negatives:
                logger.warning(f"LLM returned only {len(selected_ids)} hard negatives, using heuristic for remainder")
                heuristic_negatives = self._select_hard_negatives_heuristic(positive_tool, num_negatives)
                for neg_id in heuristic_negatives:
                    if neg_id not in selected_ids:
                        selected_ids.append(neg_id)
                        if len(selected_ids) >= num_negatives:
                            break
            
            return selected_ids[:num_negatives]
            
        except Exception as e:
            logger.error(f"LLM-based hard negative selection failed: {e}, falling back to heuristic")
            return self._select_hard_negatives_heuristic(positive_tool, num_negatives)
    
    def _select_hard_negatives_heuristic(
        self,
        positive_tool: ToolSchema,
        num_negatives: int
    ) -> List[str]:
        """
        Heuristic-based hard negative selection (fallback method).
        Selects tools with similar words in name/description.
        
        Args:
            positive_tool: The correct tool
            num_negatives: Number of negatives to select
        
        Returns:
            List of negative tool IDs
        """
        # Simple heuristic: select tools with similar words in name/description
        positive_words = set(
            positive_tool.name.lower().split() +
            positive_tool.description.lower().split()
        )
        
        candidates = []
        for tool in self.all_tools:
            if tool.id == positive_tool.id:
                continue
            
            tool_words = set(
                tool.name.lower().split() +
                tool.description.lower().split()
            )
            
            # Calculate word overlap
            overlap = len(positive_words & tool_words)
            if overlap > 0:
                candidates.append((tool.id, overlap))
        
        # Sort by overlap (descending) and take top N
        candidates.sort(key=lambda x: x[1], reverse=True)
        hard_negatives = [tool_id for tool_id, _ in candidates[:num_negatives]]
        
        # If not enough hard negatives, add random ones
        if len(hard_negatives) < num_negatives:
            remaining = [t.id for t in self.all_tools if t.id != positive_tool.id and t.id not in hard_negatives]
            hard_negatives.extend(random.sample(remaining, min(num_negatives - len(hard_negatives), len(remaining))))
        
        return hard_negatives
    
    async def generate_queries_for_tool(self, tool: ToolSchema) -> List[SyntheticQuery]:
        """
        Generate multiple queries for a single tool.
        
        Args:
            tool: Tool schema
        
        Returns:
            List of synthetic queries
        """
        queries = []
        
        # Calculate number of each query type
        total = self.data_config.queries_per_tool
        num_direct = int(total * self.data_config.direct_query_ratio)
        num_implicit = int(total * self.data_config.implicit_query_ratio)
        num_multi = total - num_direct - num_implicit
        
        # Generate direct queries
        for _ in range(num_direct):
            query_text = self._generate_direct_query(tool)
            if query_text:
                hard_negatives = self._select_hard_negatives_llm(query_text, tool, self.data_config.num_hard_negatives)
                queries.append(SyntheticQuery(
                    query=query_text,
                    positive_tool_id=tool.id,
                    hard_negative_tool_ids=hard_negatives,
                    query_type="direct"
                ))
        
        # Generate implicit queries
        for _ in range(num_implicit):
            query_text = self._generate_implicit_query(tool)
            if query_text:
                hard_negatives = self._select_hard_negatives_llm(query_text, tool, self.data_config.num_hard_negatives)
                queries.append(SyntheticQuery(
                    query=query_text,
                    positive_tool_id=tool.id,
                    hard_negative_tool_ids=hard_negatives,
                    query_type="implicit"
                ))
        
        # Generate multi-tool queries
        for _ in range(num_multi):
            # Select some related tools
            related = random.sample([t for t in self.all_tools if t.id != tool.id], min(3, len(self.all_tools) - 1))
            query_text = self._generate_multi_tool_query(tool, related)
            if query_text:
                hard_negatives = self._select_hard_negatives_llm(query_text, tool, self.data_config.num_hard_negatives)
                queries.append(SyntheticQuery(
                    query=query_text,
                    positive_tool_id=tool.id,
                    hard_negative_tool_ids=hard_negatives,
                    query_type="multi_tool"
                ))
        
        return queries
    
    async def generate_dataset(self) -> List[SyntheticQuery]:
        """
        Generate the complete synthetic dataset.
        
        Returns:
            List of all synthetic queries
        """
        all_queries = []
        
        logger.info(f"Generating queries for {len(self.all_tools)} tools...")
        
        # Process tools with progress bar
        for tool in tqdm(self.all_tools, desc="Generating queries"):
            try:
                queries = await self.generate_queries_for_tool(tool)
                all_queries.extend(queries)
                logger.debug(f"Generated {len(queries)} queries for {tool.id}")
            except Exception as e:
                logger.error(f"Failed to generate queries for {tool.id}: {e}")
        
        logger.info(f"Generated {len(all_queries)} total queries")
        return all_queries
    
    def save_dataset(self, queries: List[SyntheticQuery], output_path: Path):
        """
        Save dataset to JSONL file.
        
        Args:
            queries: List of synthetic queries
            output_path: Output file path
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            for query in queries:
                f.write(json.dumps(query.to_dict()) + '\n')
        
        logger.info(f"Saved {len(queries)} queries to {output_path}")
        
        # Print statistics
        query_types = {}
        for query in queries:
            query_types[query.query_type] = query_types.get(query.query_type, 0) + 1
        
        logger.info("Dataset statistics:")
        for qtype, count in query_types.items():
            logger.info(f"  {qtype}: {count} ({count/len(queries)*100:.1f}%)")


async def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("Phase 1: Synthetic Data Generation")
    logger.info("=" * 60)
    
    # Initialize MCP client
    logger.info("\n1. Loading tool schemas...")
    mcp_client = MCPClient(config.mcp)
    
    # Try to load predefined tools first (for testing without MCP)
    predefined_tools_path = Path("data/predefined_tools.json")
    if predefined_tools_path.exists():
        logger.info(f"Loading predefined tools from {predefined_tools_path}")
        if mcp_client.load_predefined_tools(predefined_tools_path):
            logger.info(f"✓ Loaded {len(mcp_client.get_all_tools())} predefined tools")
        else:
            logger.error("Failed to load predefined tools")
            return
    else:
        # Fall back to MCP connection
        logger.info("Connecting to MCP servers...")
        connection_results = await mcp_client.connect_all()
        
        connected = sum(1 for success in connection_results.values() if success)
        logger.info(f"Connected to {connected}/{len(connection_results)} servers")
        
        if connected == 0:
            logger.error("No MCP servers connected and no predefined tools found. Cannot proceed.")
            return
    
    # Initialize generator
    logger.info("\n2. Initializing data generator...")
    generator = SyntheticDataGenerator(
        mcp_client=mcp_client,
        llm_config=config.llm,
        data_config=config.data_generation
    )
    await generator.initialize()
    
    # Generate dataset
    logger.info("\n3. Generating synthetic queries...")
    queries = await generator.generate_dataset()
    
    # Save dataset
    logger.info("\n4. Saving dataset...")
    generator.save_dataset(queries, config.data_generation.output_path)
    
    # Save tool cache for later phases
    logger.info("\n5. Saving tool cache...")
    mcp_client.save_tool_cache(config.mcp.tool_cache_path)
    
    # Cleanup
    await mcp_client.close_all()
    
    logger.info("\n" + "=" * 60)
    logger.info("Phase 1 Complete!")
    logger.info(f"Dataset: {config.data_generation.output_path}")
    logger.info(f"Tool Cache: {config.mcp.tool_cache_path}")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

# Made with Bob
