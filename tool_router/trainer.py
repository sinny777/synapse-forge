"""
Phase 2: PyTorch Model Training/Fine-Tuning

This module fine-tunes a sentence transformer model for tool retrieval:
1. Loads the synthetic JSONL dataset
2. Fine-tunes using MultipleNegativesRankingLoss
3. Saves the fine-tuned model
4. Creates a FAISS/ChromaDB vector index of all tools
"""

import json
import logging
from typing import List, Dict, Any, Tuple
from pathlib import Path
import torch
from torch.utils.data import DataLoader
import numpy as np

from sentence_transformers import SentenceTransformer, InputExample, losses
from sentence_transformers.evaluation import InformationRetrievalEvaluator

from tool_router.config import config, TrainingConfig, EmbeddingConfig, VectorStoreConfig
from tool_router.mcp_client import ToolSchema

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ToolRetrievalDataset:
    """Dataset for tool retrieval training."""
    
    def __init__(self, jsonl_path: Path):
        """
        Initialize dataset from JSONL file.
        
        Args:
            jsonl_path: Path to synthetic queries JSONL file
        """
        self.examples: List[InputExample] = []
        self.load_data(jsonl_path)
    
    def load_data(self, jsonl_path: Path):
        """
        Load training data from JSONL file.
        
        Args:
            jsonl_path: Path to JSONL file
        """
        logger.info(f"Loading training data from {jsonl_path}")
        
        with open(jsonl_path, 'r') as f:
            for line in f:
                data = json.loads(line)
                
                # Create InputExample for sentence-transformers
                # Format: (query, positive_tool_id)
                # Negatives will be handled by the loss function
                example = InputExample(
                    texts=[data['query'], data['positive_tool_id']],
                    label=1.0  # Positive pair
                )
                self.examples.append(example)
        
        logger.info(f"Loaded {len(self.examples)} training examples")
    
    def get_examples(self) -> List[InputExample]:
        """Get all training examples."""
        return self.examples


class ToolEmbeddingTrainer:
    """
    Trainer for fine-tuning embedding models for tool retrieval.
    Uses contrastive learning with MultipleNegativesRankingLoss.
    """
    
    def __init__(
        self,
        embedding_config: EmbeddingConfig,
        training_config: TrainingConfig
    ):
        """
        Initialize trainer.
        
        Args:
            embedding_config: Embedding model configuration
            training_config: Training configuration
        """
        self.embedding_config = embedding_config
        self.training_config = training_config
        self.model: SentenceTransformer = None
    
    def load_base_model(self):
        """Load the base pre-trained model."""
        logger.info(f"Loading base model: {self.embedding_config.base_model_name}")
        
        self.model = SentenceTransformer(
            self.embedding_config.base_model_name,
            device=self.embedding_config.device
        )
        
        logger.info(f"Model loaded. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
    
    def train(self, dataset: ToolRetrievalDataset):
        """
        Fine-tune the model on the dataset.
        
        Args:
            dataset: Training dataset
        """
        logger.info("Starting model fine-tuning...")
        
        # Create DataLoader
        train_dataloader = DataLoader(
            dataset.get_examples(),
            shuffle=True,
            batch_size=self.training_config.batch_size
        )
        
        # Define loss function
        # MultipleNegativesRankingLoss: treats other examples in batch as negatives
        train_loss = losses.MultipleNegativesRankingLoss(self.model)
        
        # Calculate training steps
        num_train_steps = len(train_dataloader) * self.training_config.num_epochs
        
        logger.info(f"Training configuration:")
        logger.info(f"  Batch size: {self.training_config.batch_size}")
        logger.info(f"  Epochs: {self.training_config.num_epochs}")
        logger.info(f"  Learning rate: {self.training_config.learning_rate}")
        logger.info(f"  Total steps: {num_train_steps}")
        logger.info(f"  Warmup steps: {self.training_config.warmup_steps}")
        
        # Train the model
        self.model.fit(
            train_objectives=[(train_dataloader, train_loss)],
            epochs=self.training_config.num_epochs,
            warmup_steps=self.training_config.warmup_steps,
            output_path=str(self.embedding_config.fine_tuned_model_dir),
            show_progress_bar=True,
            save_best_model=True,
            optimizer_params={'lr': self.training_config.learning_rate}
        )
        
        logger.info("Training complete!")
    
    def save_model(self):
        """Save the fine-tuned model."""
        output_dir = self.embedding_config.fine_tuned_model_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        
        self.model.save(str(output_dir))
        logger.info(f"Model saved to {output_dir}")
    
    def load_fine_tuned_model(self):
        """Load the fine-tuned model."""
        model_path = self.embedding_config.fine_tuned_model_dir
        
        if not model_path.exists():
            raise FileNotFoundError(f"Fine-tuned model not found at {model_path}")
        
        logger.info(f"Loading fine-tuned model from {model_path}")
        self.model = SentenceTransformer(str(model_path), device=self.embedding_config.device)
        logger.info("Fine-tuned model loaded successfully")


class VectorIndexBuilder:
    """
    Builds and manages vector indices for tool embeddings.
    Supports FAISS and ChromaDB.
    """
    
    def __init__(
        self,
        model: SentenceTransformer,
        vector_config: VectorStoreConfig
    ):
        """
        Initialize index builder.
        
        Args:
            model: Fine-tuned embedding model
            vector_config: Vector store configuration
        """
        self.model = model
        self.vector_config = vector_config
        self.index = None
        self.tool_ids: List[str] = []
    
    def build_faiss_index(self, tools: List[ToolSchema]):
        """
        Build FAISS index from tool schemas.
        
        Args:
            tools: List of tool schemas
        """
        import faiss
        
        logger.info(f"Building FAISS index for {len(tools)} tools...")
        
        # Extract tool texts for embedding
        tool_texts = [tool.get_embedding_text() for tool in tools]
        self.tool_ids = [tool.id for tool in tools]
        
        # Generate embeddings
        logger.info("Generating embeddings...")
        embeddings = self.model.encode(
            tool_texts,
            show_progress_bar=True,
            convert_to_numpy=True
        )
        
        # Normalize embeddings for cosine similarity
        faiss.normalize_L2(embeddings)
        
        # Create FAISS index
        dimension = embeddings.shape[1]
        
        if self.vector_config.faiss_index_type == "IndexFlatIP":
            # Inner Product (cosine similarity with normalized vectors)
            self.index = faiss.IndexFlatIP(dimension)
        elif self.vector_config.faiss_index_type == "IndexFlatL2":
            # L2 distance
            self.index = faiss.IndexFlatL2(dimension)
        else:
            raise ValueError(f"Unsupported FAISS index type: {self.vector_config.faiss_index_type}")
        
        # Add embeddings to index
        self.index.add(embeddings)
        
        logger.info(f"FAISS index built with {self.index.ntotal} vectors")
    
    def build_bm25_index(self, tools: List[ToolSchema]):
        """
        Build BM25 index from tool schemas for sparse retrieval.
        
        Args:
            tools: List of tool schemas
        """
        from rank_bm25 import BM25Okapi
        
        logger.info(f"Building BM25 index for {len(tools)} tools...")
        
        # Extract tool texts and IDs
        tool_texts = [tool.get_embedding_text() for tool in tools]
        self.tool_ids = [tool.id for tool in tools]
        
        # Tokenize documents (simple whitespace tokenization)
        tokenized_corpus = [doc.lower().split() for doc in tool_texts]
        
        # Create BM25 index
        self.bm25_index = BM25Okapi(tokenized_corpus)
        
        logger.info(f"BM25 index built with {len(tokenized_corpus)} documents")
    
    def save_bm25_index(self):
        """Save BM25 index to disk using pickle."""
        import pickle
        
        if not hasattr(self, 'bm25_index') or self.bm25_index is None:
            raise ValueError("No BM25 index to save. Build index first.")
        
        bm25_path = self.vector_config.faiss_index_path.parent / "bm25_index.pkl"
        bm25_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save BM25 index
        with open(bm25_path, 'wb') as f:
            pickle.dump(self.bm25_index, f)
        
        # Save tool IDs mapping (same as FAISS)
        mapping_path = bm25_path.with_suffix('.json')
        with open(mapping_path, 'w') as f:
            json.dump({"tool_ids": self.tool_ids}, f, indent=2)
        
        logger.info(f"BM25 index saved to {bm25_path}")
    
    def load_bm25_index(self) -> Tuple[Any, List[str]]:
        """
        Load BM25 index from disk.
        
        Returns:
            Tuple of (bm25_index, tool_ids)
        """
        import pickle
        
        bm25_path = self.vector_config.faiss_index_path.parent / "bm25_index.pkl"
        mapping_path = bm25_path.with_suffix('.json')
        
        if not bm25_path.exists():
            raise FileNotFoundError(f"BM25 index not found at {bm25_path}")
        
        # Load BM25 index
        with open(bm25_path, 'rb') as f:
            bm25_index = pickle.load(f)
        
        # Load tool IDs
        with open(mapping_path, 'r') as f:
            data = json.load(f)
            tool_ids = data["tool_ids"]
        
        logger.info(f"Loaded BM25 index with {len(tool_ids)} tools")
        return bm25_index, tool_ids
    
    def save_faiss_index(self):
        """Save FAISS index to disk."""
        import faiss
        
        if self.index is None:
            raise ValueError("No index to save. Build index first.")
        
        index_path = self.vector_config.faiss_index_path
        index_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save index
        faiss.write_index(self.index, str(index_path))
        
        # Save tool IDs mapping
        mapping_path = index_path.with_suffix('.json')
        with open(mapping_path, 'w') as f:
            json.dump({"tool_ids": self.tool_ids}, f, indent=2)
        
        logger.info(f"FAISS index saved to {index_path}")
        logger.info(f"Tool ID mapping saved to {mapping_path}")
    
    def build_chromadb_index(self, tools: List[ToolSchema]):
        """
        Build ChromaDB collection from tool schemas.
        
        Args:
            tools: List of tool schemas
        """
        import chromadb
        from chromadb.config import Settings
        
        logger.info(f"Building ChromaDB collection for {len(tools)} tools...")
        
        # Initialize ChromaDB client
        client = chromadb.PersistentClient(
            path=str(self.vector_config.chromadb_path),
            settings=Settings(anonymized_telemetry=False)
        )
        
        # Create or get collection
        collection = client.get_or_create_collection(
            name=self.vector_config.chromadb_collection_name,
            metadata={"description": "Tool embeddings for ToolRouter"}
        )
        
        # Prepare data
        tool_texts = [tool.get_embedding_text() for tool in tools]
        tool_ids = [tool.id for tool in tools]
        
        # Generate embeddings
        logger.info("Generating embeddings...")
        embeddings = self.model.encode(
            tool_texts,
            show_progress_bar=True,
            convert_to_numpy=True
        )
        
        # Add to collection
        collection.add(
            ids=tool_ids,
            embeddings=embeddings.tolist(),
            documents=tool_texts,
            metadatas=[{"name": tool.name, "description": tool.description} for tool in tools]
        )
        
        logger.info(f"ChromaDB collection created with {len(tools)} tools")
        self.index = collection
    
    def load_faiss_index(self) -> Tuple[Any, List[str]]:
        """
        Load FAISS index from disk.
        
        Returns:
            Tuple of (index, tool_ids)
        """
        import faiss
        
        index_path = self.vector_config.faiss_index_path
        mapping_path = index_path.with_suffix('.json')
        
        if not index_path.exists():
            raise FileNotFoundError(f"FAISS index not found at {index_path}")
        
        # Load index
        index = faiss.read_index(str(index_path))
        
        # Load tool IDs
        with open(mapping_path, 'r') as f:
            data = json.load(f)
            tool_ids = data["tool_ids"]
        
        logger.info(f"Loaded FAISS index with {index.ntotal} vectors")
        return index, tool_ids


def load_tools_from_cache(cache_path: Path) -> List[ToolSchema]:
    """
    Load tool schemas from cache file.
    
    Args:
        cache_path: Path to tool cache JSON
    
    Returns:
        List of ToolSchema objects
    """
    logger.info(f"Loading tools from cache: {cache_path}")
    
    with open(cache_path, 'r') as f:
        cache_data = json.load(f)
    
    tools = []
    for tool_dict in cache_data.get("tools", []):
        tool = ToolSchema(**tool_dict)
        tools.append(tool)
    
    logger.info(f"Loaded {len(tools)} tools from cache")
    return tools


def main():
    """Main execution function."""
    logger.info("=" * 60)
    logger.info("Phase 2: Model Training & Fine-Tuning")
    logger.info("=" * 60)
    
    # Check if training data exists
    if not config.training.training_data_path.exists():
        logger.error(f"Training data not found: {config.training.training_data_path}")
        logger.error("Please run phase1_generator.py first to generate training data")
        return
    
    # Load dataset
    logger.info("\n1. Loading training dataset...")
    dataset = ToolRetrievalDataset(config.training.training_data_path)
    
    # Initialize trainer
    logger.info("\n2. Initializing trainer...")
    trainer = ToolEmbeddingTrainer(config.embedding, config.training)
    trainer.load_base_model()
    
    # Train model
    logger.info("\n3. Fine-tuning model...")
    trainer.train(dataset)
    
    # Save model
    logger.info("\n4. Saving fine-tuned model...")
    trainer.save_model()
    
    # Load tools from cache
    logger.info("\n5. Loading tool schemas...")
    tools = load_tools_from_cache(config.mcp.tool_cache_path)
    
    # Build vector index
    logger.info("\n6. Building dense vector index...")
    index_builder = VectorIndexBuilder(trainer.model, config.vector_store)
    
    if config.vector_store.store_type == "faiss":
        index_builder.build_faiss_index(tools)
        index_builder.save_faiss_index()
    elif config.vector_store.store_type == "chromadb":
        index_builder.build_chromadb_index(tools)
    else:
        logger.error(f"Unsupported vector store type: {config.vector_store.store_type}")
        return
    
    # Build BM25 sparse index for hybrid retrieval
    logger.info("\n7. Building BM25 sparse index...")
    index_builder.build_bm25_index(tools)
    index_builder.save_bm25_index()
    
    logger.info("Phase 2 Complete!")
    logger.info(f"Fine-tuned model: {config.embedding.fine_tuned_model_dir}")
    if config.vector_store.store_type == "faiss":
        logger.info(f"Dense index (FAISS): {config.vector_store.faiss_index_path}")
    else:
        logger.info(f"Dense index (ChromaDB): {config.vector_store.chromadb_path}")
    logger.info(f"Sparse index (BM25): {config.vector_store.faiss_index_path.parent / 'bm25_index.pkl'}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()

# Made with Bob
