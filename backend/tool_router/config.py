"""
ToolRouter Configuration Module

This module contains all configuration settings for the ToolRouter framework.
Modify these settings to customize the behavior of data generation, training, and runtime.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""
    
    # Teacher LLM for synthetic data generation (Phase 1)
    teacher_model: str = field(default_factory=lambda: os.getenv("TEACHER_MODEL", "ollama/granite4.1:8b"))
    teacher_temperature: float = 0.7
    teacher_max_tokens: int = 2000
    
    # Query expansion LLM (Phase 3 - fast/cheap)
    expansion_model: str = field(default_factory=lambda: os.getenv("EXPANSION_MODEL", "ollama/granite4.1:8b"))
    expansion_temperature: float = 0.3
    expansion_max_tokens: int = 500
    
    # Heavy LLM for tool execution (Phase 3)
    heavy_model: str = field(default_factory=lambda: os.getenv("HEAVY_MODEL", "ollama/granite4.1:8b"))
    heavy_temperature: float = 0.0
    heavy_max_tokens: int = 4000
    
    # API keys and endpoints (read from environment variables)
    ollama_api_base: Optional[str] = field(default_factory=lambda: os.getenv("OLLAMA_API_BASE", "http://localhost:11434"))
    openai_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    anthropic_api_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))
    google_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_API_KEY"))
    groq_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GROQ_API_KEY"))


@dataclass
class EmbeddingConfig:
    """Configuration for embedding model."""
    
    # Base model to fine-tune
    base_model_name: str = "sentence-transformers/all-MiniLM-L6-v2" 
    # base_model_name: str = "BAAI/bge-small-en-v1.5"
    # base_model_name: str = "BAAI/bge-base-en-v1.5"
    
    # Fine-tuned model paths
    fine_tuned_model_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "models" / "fine_tuned_tool_router")
    
    # Embedding dimensions (auto-detected from model)
    embedding_dim: Optional[int] = None
    
    # Device for inference
    device: str = "cpu"  # Options: "cpu", "cuda", "mps"


@dataclass
class TrainingConfig:
    """Configuration for model training (Phase 2)."""
    
    # Training hyperparameters
    batch_size: int = 16
    num_epochs: int = 3
    learning_rate: float = 2e-5
    warmup_steps: int = 100
    
    # Loss function
    loss_function: str = "MultipleNegativesRankingLoss"
    
    # Evaluation
    eval_steps: int = 100
    save_steps: int = 500
    
    # Data paths
    training_data_path: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "synthetic_queries.jsonl")
    
    # Logging
    logging_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "logs" / "training")


@dataclass
class VectorStoreConfig:
    """Configuration for vector store."""
    
    # Vector store type
    store_type: str = "faiss"  # Options: "faiss", "chromadb"
    
    # FAISS settings
    faiss_index_path: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "faiss_index.bin")
    faiss_index_type: str = "IndexFlatIP"  # Inner product (cosine similarity)
    
    # ChromaDB settings
    chromadb_path: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "chromadb")
    chromadb_collection_name: str = "tool_embeddings"
    
    # Search settings
    top_k: int = 3  # Number of tools to retrieve
    similarity_threshold: float = 0.3  # Minimum similarity score


@dataclass
class MCPConfig:
    """Configuration for MCP servers."""
    
    # MCP server configurations
    # Format: {"server_name": {"command": "...", "args": [...], "env": {...}}}
    servers: Dict[str, Dict[str, Any]] = field(default_factory=lambda: {
        # "filesystem": {
        #     "command": "npx",
        #     "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
        #     "transport": "stdio"
        # },
        # "mediclaim": {
        #     "command": "python",
        #     "args": [str(Path(__file__).parent.parent.parent / "examples" / "beeai_mediclaim_processing" / "mock_fastmcp_server.py")],
        #     "transport": "stdio"
        # },
        "uhnwc_banking": {
            "command": "python",
            "args": [str(Path(__file__).parent.parent.parent / "examples" / "langgraph_UHNW_banking" / "mock_fastmcp_server.py")],
            "transport": "stdio"
        }
        # Add more MCP servers here
    })
    
    # Connection timeout
    connection_timeout: int = 30
    
    # Tool schema cache
    tool_cache_path: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "tool_cache.json")


@dataclass
class DataGenerationConfig:
    """Configuration for synthetic data generation (Phase 1)."""
    
    # Number of queries to generate per tool
    queries_per_tool: int = 10
    
    # Query types distribution
    direct_query_ratio: float = 0.4  # 40% direct queries
    implicit_query_ratio: float = 0.4  # 40% implicit queries
    multi_tool_query_ratio: float = 0.2  # 20% multi-tool queries
    
    # Hard negatives
    num_hard_negatives: int = 3
    
    # Output path
    output_path: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "synthetic_queries.jsonl")
    
    # Batch processing
    batch_size: int = 5  # Tools to process in parallel


@dataclass
class RuntimeConfig:
    """Configuration for runtime execution (Phase 3)."""
    
    # Query expansion
    enable_query_expansion: bool = True
    expansion_prompt_template: str = """Given the user query, break it down into logical steps or sub-tasks that would be needed to accomplish it.
Be specific and actionable. List 2-5 steps.

User Query: {query}

Logical Steps:"""
    
    # Tool retrieval
    enable_fallback_tool: bool = True
    fallback_tool_name: str = "search_available_tools"
    
    # Execution
    max_tool_calls: int = 10  # Maximum tool calls per query
    tool_call_timeout: int = 30  # Seconds
    
    # Logging
    log_level: str = "INFO"  # Options: DEBUG, INFO, WARNING, ERROR
    log_file: Path = field(default_factory=lambda: Path(__file__).parent.parent / "logs" / "runtime.log")


@dataclass
class ToolRouterConfig:
    """Main configuration class combining all sub-configurations."""
    
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    vector_store: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    mcp: MCPConfig = field(default_factory=MCPConfig)
    data_generation: DataGenerationConfig = field(default_factory=DataGenerationConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    
    # Project paths
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    data_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data")
    datasets_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "data" / "datasets")
    models_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "models")
    logs_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent / "logs")
    
    def __post_init__(self):
        """Create necessary directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.training.logging_dir.mkdir(parents=True, exist_ok=True)
    
    def validate(self) -> bool:
        """Validate configuration settings."""
        errors = []
        
        # Check API keys
        if not self.llm.openai_api_key and "gpt" in self.llm.teacher_model.lower():
            errors.append("OpenAI API key required for GPT models")
        
        if not self.llm.anthropic_api_key and "claude" in self.llm.teacher_model.lower():
            errors.append("Anthropic API key required for Claude models")
        
        # Check ratios sum to 1.0
        ratio_sum = (
            self.data_generation.direct_query_ratio +
            self.data_generation.implicit_query_ratio +
            self.data_generation.multi_tool_query_ratio
        )
        if abs(ratio_sum - 1.0) > 0.01:
            errors.append(f"Query type ratios must sum to 1.0, got {ratio_sum}")
        
        # Check Top-K value
        if self.vector_store.top_k < 1:
            errors.append("top_k must be at least 1")
        
        if errors:
            print("Configuration validation errors:")
            for error in errors:
                print(f"  - {error}")
            return False
        
        return True
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "ToolRouterConfig":
        """Create configuration from dictionary."""
        return cls(**config_dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "llm": self.llm.__dict__,
            "embedding": self.embedding.__dict__,
            "training": self.training.__dict__,
            "vector_store": self.vector_store.__dict__,
            "mcp": self.mcp.__dict__,
            "data_generation": self.data_generation.__dict__,
            "runtime": self.runtime.__dict__,
        }


# Global configuration instance
config = ToolRouterConfig()


def load_config(config_path: Optional[Path] = None) -> ToolRouterConfig:
    """
    Load configuration from file or return default.
    
    Args:
        config_path: Path to configuration file (JSON or YAML)
    
    Returns:
        ToolRouterConfig instance
    """
    if config_path and config_path.exists():
        import json
        with open(config_path, 'r') as f:
            config_dict = json.load(f)
        return ToolRouterConfig.from_dict(config_dict)
    
    return ToolRouterConfig()


def save_config(config: ToolRouterConfig, config_path: Path):
    """
    Save configuration to file.
    
    Args:
        config: Configuration instance
        config_path: Path to save configuration
    """
    import json
    with open(config_path, 'w') as f:
        json.dump(config.to_dict(), f, indent=2, default=str)


if __name__ == "__main__":
    # Example usage and validation
    config = ToolRouterConfig()
    
    print("ToolRouter Configuration")
    print("=" * 50)
    print(f"Teacher LLM: {config.llm.teacher_model}")
    print(f"Expansion LLM: {config.llm.expansion_model}")
    print(f"Heavy LLM: {config.llm.heavy_model}")
    print(f"Base Embedding Model: {config.embedding.base_model_name}")
    print(f"Vector Store: {config.vector_store.store_type}")
    print(f"Top-K: {config.vector_store.top_k}")
    print(f"Training Epochs: {config.training.num_epochs}")
    print(f"Batch Size: {config.training.batch_size}")
    print("=" * 50)
    
    if config.validate():
        print("✓ Configuration is valid")
    else:
        print("✗ Configuration has errors")

# Made with Bob
