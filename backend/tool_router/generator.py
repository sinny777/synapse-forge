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
import re

from litellm import completion, acompletion
from tqdm import tqdm

from tool_router.config import config, DataGenerationConfig, LLMConfig
from tool_router.mcp_client import MCPClient, ToolSchema
from tool_router.status_tracker import update_status

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
    
    PERSONAS = [
        "A highly technical software engineer who uses jargon",
        "A frustrated user in a hurry",
        "An elderly person who is polite and slightly confused",
        "A corporate executive asking for bottom-line results",
        "A casual user texting a friend",
        "A meticulous analyst asking for precise details",
        "Someone who is angry and demanding",
        "A student asking for educational purposes",
        "A non-native English speaker with simple vocabulary",
        "A highly structured project manager"
    ]
    
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
    
    async def _acall_teacher_llm_json(self, prompt: str, expected_count: int = None, retries: int = 3) -> List[str]:
        """
        Call the Teacher LLM with a prompt asynchronously and parse a JSON array of strings.
        Retries on failure or empty results.
        """
        for attempt in range(retries):
            try:
                response = await acompletion(
                    model=self.llm_config.teacher_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=max(self.llm_config.teacher_temperature, 0.8), # Boost temperature for diversity
                    max_tokens=self.llm_config.teacher_max_tokens,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content.strip()
                
                # Extract JSON block if surrounded by markdown
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                    
                parsed_list = []
                try:
                    parsed = json.loads(content)
                    if isinstance(parsed, dict):
                        for key in parsed:
                            if isinstance(parsed[key], list):
                                parsed_list = parsed[key]
                                break
                    elif isinstance(parsed, list):
                        parsed_list = parsed
                except json.JSONDecodeError:
                    # Robust fallback extraction: find everything between [ and ]
                    match = re.search(r'\[(.*)\]', content, re.DOTALL)
                    if match:
                        try:
                            parsed_list = json.loads("[" + match.group(1) + "]")
                        except:
                            # Super fallback: just split by commas and quotes if it's a simple list
                            items = re.findall(r'"([^"]*)"', match.group(1))
                            if items: parsed_list = items
                
                if parsed_list and len(parsed_list) > 0:
                    if expected_count and len(parsed_list) < expected_count and attempt < retries - 1:
                        logger.warning(f"Got {len(parsed_list)} queries but expected {expected_count}. Retrying...")
                        continue
                    return parsed_list
                    
                logger.warning(f"Attempt {attempt+1} failed to extract any queries from: {content[:100]}...")
            except Exception as e:
                logger.error(f"LLM call failed on attempt {attempt+1}: {e}")
                
        return []
            
    async def _generate_direct_queries(self, tool: ToolSchema, count: int) -> List[str]:
        if count <= 0: return []
        personas = random.sample(self.PERSONAS, min(count, len(self.PERSONAS)))
        personas_text = "\n".join([f"- {p}" for p in personas])
        
        prompt = f"""You are generating training data for an AI tool router. 
Generate exactly {count} direct, straightforward user queries that would require using this specific tool.

Tool Name: {tool.name}
Description: {tool.description}
Parameters: {json.dumps(tool.parameters.get('properties', dict()), indent=2)}

CRITICAL REQUIREMENTS:
1. Ensure MAXIMUM diversity in vocabulary, sentence length, and structure.
2. DO NOT start multiple queries with the same phrase.
3. Adopt varying personas for the queries, such as:
{personas_text}

Output ONLY a valid JSON object with a single key "queries" containing a list of {count} strings.
Example format:
{{
  "queries": [
    "What's the weather like in San Francisco right now?",
    "I need the current temperature for SF.",
    "Give me the SF forecast immediately."
  ]
}}
"""
        return await self._acall_teacher_llm_json(prompt, expected_count=count)
    
    async def _generate_implicit_queries(self, tool: ToolSchema, count: int) -> List[str]:
        if count <= 0: return []
        personas = random.sample(self.PERSONAS, min(count, len(self.PERSONAS)))
        personas_text = "\n".join([f"- {p}" for p in personas])
        
        prompt = f"""You are generating training data for an AI tool router.
Generate exactly {count} implicit, natural language queries that would require using this tool, but don't directly mention it.

Tool Name: {tool.name}
Description: {tool.description}
Parameters: {json.dumps(tool.parameters.get('properties', dict()), indent=2)}

CRITICAL REQUIREMENTS:
1. Ensure MAXIMUM diversity in vocabulary, sentence length, and structure.
2. The query must imply needing the tool without explicitly asking for it.
3. Adopt varying personas for the queries, such as:
{personas_text}

Output ONLY a valid JSON object with a single key "queries" containing a list of {count} strings.
Example format:
{{
  "queries": [
    "I'm planning a picnic tomorrow, should I bring an umbrella?",
    "My flight to Boston is in 3 hours, how should I pack?",
    "Is it safe to go sailing today?"
  ]
}}
"""
        return await self._acall_teacher_llm_json(prompt, expected_count=count)
    
    async def _generate_multi_tool_queries(self, primary_tool: ToolSchema, related_tools: List[ToolSchema], count: int) -> List[str]:
        if count <= 0: return []
        
        tools_context = f"Primary Tool: {primary_tool.name} - {primary_tool.description}\n"
        tools_context += "Related Tools:\n"
        for tool in related_tools[:2]:
            tools_context += f"  - {tool.name}: {tool.description}\n"
            
        personas = random.sample(self.PERSONAS, min(count, len(self.PERSONAS)))
        personas_text = "\n".join([f"- {p}" for p in personas])
        
        prompt = f"""You are generating training data for an AI tool router.
Generate exactly {count} complex user queries that would primarily require the main tool, but might also involve related tools.

{tools_context}

CRITICAL REQUIREMENTS:
1. Ensure MAXIMUM diversity in vocabulary, sentence length, and structure.
2. The query should be multi-step or involve multiple aspects.
3. Adopt varying personas for the queries, such as:
{personas_text}

Output ONLY a valid JSON object with a single key "queries" containing a list of {count} strings.
Example format:
{{
  "queries": [
    "I need to check the weather for my trip next week and also find good restaurants in that area.",
    "Can you find me a flight to NY, and then tell me if it will rain when I arrive?",
    "Book a hotel for me in Paris, but first make sure the local events schedule isn't too crowded."
  ]
}}
"""
        return await self._acall_teacher_llm_json(prompt, expected_count=count)
    
    async def _select_hard_negatives_llm(
        self,
        positive_tool: ToolSchema,
        num_negatives: int
    ) -> List[str]:
        """
        Use Teacher LLM to select hard negative tools that operate in a similar domain
        or share keywords, but serve a fundamentally different purpose.
        """
        candidate_tools = [t for t in self.all_tools if t.id != positive_tool.id]
        
        if len(candidate_tools) < num_negatives * 2:
            return self._select_hard_negatives_heuristic(positive_tool, num_negatives)
        
        sample_size = min(30, len(candidate_tools))
        sampled_tools = random.sample(candidate_tools, sample_size)
        
        tools_text = ""
        for i, tool in enumerate(sampled_tools, 1):
            tools_text += f"{i}. {tool.id}\n   Name: {tool.name}\n   Description: {tool.description}\n\n"
        
        prompt = f"""You are an expert at identifying "hard negative" examples for machine learning training.

Given the CORRECT tool, identify {num_negatives} "hard negative" tools from the list below.

**Definition of Hard Negative:** A tool that sounds conceptually related, shares similar keywords, or operates in a similar domain, but serves a fundamentally different purpose. These are tools that a model might accidentally select instead of the correct tool.

**Correct Tool:** {positive_tool.id}
- Name: {positive_tool.name}
- Description: {positive_tool.description}

**Candidate Tools:**
{tools_text}

**Task:** Select exactly {num_negatives} hard negative tool IDs.
Output ONLY a valid JSON object with a single key "tool_ids" containing a list of strings.
Example format:
{{
  "tool_ids": [
    "server.tool_name_1",
    "server.tool_name_2",
    "server.tool_name_3"
  ]
}}
"""
        try:
            response = await acompletion(
                model=self.llm_config.teacher_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3, # Lower temperature for classification tasks
                max_tokens=self.llm_config.teacher_max_tokens,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content.strip()
            
            # Extract JSON block
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            selected_ids = []
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict) and "tool_ids" in parsed:
                    selected_ids = parsed["tool_ids"]
                elif isinstance(parsed, list):
                    selected_ids = parsed
            except json.JSONDecodeError:
                pass
                
            # Filter valid IDs
            valid_ids = [tid for tid in selected_ids if any(t.id == tid for t in sampled_tools)]
            
            if len(valid_ids) < num_negatives:
                logger.warning(f"LLM returned only {len(valid_ids)} valid hard negatives, using heuristic for remainder")
                heuristic_negatives = self._select_hard_negatives_heuristic(positive_tool, num_negatives)
                for neg_id in heuristic_negatives:
                    if neg_id not in valid_ids:
                        valid_ids.append(neg_id)
                        if len(valid_ids) >= num_negatives:
                            break
            
            return valid_ids[:num_negatives]
            
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
        """
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
            
            overlap = len(positive_words & tool_words)
            if overlap > 0:
                candidates.append((tool.id, overlap))
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        hard_negatives = [tool_id for tool_id, _ in candidates[:num_negatives]]
        
        if len(hard_negatives) < num_negatives:
            remaining = [t.id for t in self.all_tools if t.id != positive_tool.id and t.id not in hard_negatives]
            hard_negatives.extend(random.sample(remaining, min(num_negatives - len(hard_negatives), len(remaining))))
        
        return hard_negatives
    
    async def generate_queries_for_tool(self, tool: ToolSchema) -> List[SyntheticQuery]:
        """
        Generate multiple queries for a single tool concurrently.
        """
        queries = []
        
        total = self.data_config.queries_per_tool
        num_direct = int(total * self.data_config.direct_query_ratio)
        num_implicit = int(total * self.data_config.implicit_query_ratio)
        num_multi = total - num_direct - num_implicit
        
        related = random.sample([t for t in self.all_tools if t.id != tool.id], min(3, len(self.all_tools) - 1)) if len(self.all_tools) > 1 else []
        
        # Concurrently generate direct, implicit, multi-tool queries, and get tool-level hard negatives
        results = await asyncio.gather(
            self._generate_direct_queries(tool, num_direct),
            self._generate_implicit_queries(tool, num_implicit),
            self._generate_multi_tool_queries(tool, related, num_multi),
            self._select_hard_negatives_llm(tool, self.data_config.num_hard_negatives),
            return_exceptions=True
        )
        
        direct_queries = results[0] if not isinstance(results[0], Exception) else []
        implicit_queries = results[1] if not isinstance(results[1], Exception) else []
        multi_tool_queries = results[2] if not isinstance(results[2], Exception) else []
        hard_negatives = results[3] if not isinstance(results[3], Exception) else self._select_hard_negatives_heuristic(tool, self.data_config.num_hard_negatives)
        
        # Build SyntheticQuery objects
        for qt in direct_queries[:num_direct]:
            queries.append(SyntheticQuery(query=qt, positive_tool_id=tool.id, hard_negative_tool_ids=hard_negatives, query_type="direct"))
            
        for qt in implicit_queries[:num_implicit]:
            queries.append(SyntheticQuery(query=qt, positive_tool_id=tool.id, hard_negative_tool_ids=hard_negatives, query_type="implicit"))
            
        for qt in multi_tool_queries[:num_multi]:
            queries.append(SyntheticQuery(query=qt, positive_tool_id=tool.id, hard_negative_tool_ids=hard_negatives, query_type="multi_tool"))
            
        return queries
    
    async def generate_dataset(self) -> List[SyntheticQuery]:
        """
        Generate the complete synthetic dataset.
        """
        all_queries = []
        
        logger.info(f"Generating queries for {len(self.all_tools)} tools...")
        update_status(progress=0.1, message=f"Generating queries for {len(self.all_tools)} tools...")
        
        # Using semaphore to limit concurrency based on config batch_size
        semaphore = asyncio.Semaphore(max(1, getattr(self.data_config, 'batch_size', 5)))
        
        async def process_tool(tool):
            async with semaphore:
                try:
                    res = await self.generate_queries_for_tool(tool)
                    logger.debug(f"Generated {len(res)} queries for {tool.id}")
                    return res
                except Exception as e:
                    logger.error(f"Failed to generate queries for {tool.id}: {e}")
                    return []
        
        tasks = [process_tool(tool) for tool in self.all_tools]
        
        completed_tools = 0
        total_tools = len(tasks)
        
        # Gather all tasks with progress tracking
        for f in asyncio.as_completed(tasks):
            result = await f
            all_queries.extend(result)
            completed_tools += 1
            progress_val = 0.1 + (0.8 * (completed_tools / max(total_tools, 1)))
            update_status(progress=progress_val, message=f"Generated queries for {completed_tools}/{total_tools} tools...")
            
        logger.info(f"Generated {len(all_queries)} total queries")
        update_status(progress=0.9, message=f"Generated {len(all_queries)} total queries")
        return all_queries
    
    def save_dataset(self, queries: List[SyntheticQuery], output_path: Path):
        """
        Save dataset to JSONL file.
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
    update_status(progress=0.05, message="Loading tool schemas from MCP servers...")
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
            error_msg = "No MCP servers connected and no predefined tools found. Cannot proceed."
            logger.error(error_msg)
            raise RuntimeError(error_msg)
            
        logger.info("Listing tools from connected servers...")
        await mcp_client.list_tools()
    
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
    update_status(progress=0.95, message="Saving generated dataset...")
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
