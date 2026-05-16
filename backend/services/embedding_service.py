"""
SynapseForge — Embedding Service

Manages per-workspace embedding model loading and vector generation.
Each workspace can configure its own embedding model + dimension,
and this service lazily loads / caches models to avoid repeated
initialisation overhead.
"""

import logging
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("ntr.embedding")


class EmbeddingService:
    """
    Generates dense vector embeddings for tool descriptions.

    Models are cached by name so multiple calls for the same workspace
    (same model) don't trigger redundant loading.
    """

    def __init__(self) -> None:
        # model_name → SentenceTransformer instance
        self._models: dict[str, SentenceTransformer] = {}

    # ------------------------------------------------------------------
    # Model management
    # ------------------------------------------------------------------

    def _get_model(self, model_name: str) -> SentenceTransformer:
        """Return a cached model instance, loading it on first use."""
        if model_name not in self._models:
            logger.info("Loading embedding model: %s", model_name)
            self._models[model_name] = SentenceTransformer(model_name)
            logger.info(
                "Loaded %s  (dim=%d)",
                model_name,
                self._models[model_name].get_sentence_embedding_dimension(),
            )
        return self._models[model_name]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_text(
        self,
        text: str,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> list[float]:
        """
        Embed a single text string.

        Args:
            text: Free-form text to embed.
            model_name: HuggingFace model identifier.

        Returns:
            Dense embedding as a list of floats.
        """
        model = self._get_model(model_name)
        vec = model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
        return vec.tolist()

    def embed_tool(
        self,
        name: str,
        description: Optional[str],
        schema_def: Optional[dict],
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    ) -> list[float]:
        """
        Generate an embedding for a tool by combining its metadata.

        The concatenation order is:
            name • description • schema summary

        Args:
            name: Tool name.
            description: Human-readable tool description.
            schema_def: OpenAPI / function-calling schema (JSONB).
            model_name: Embedding model to use.

        Returns:
            Dense embedding as a list of floats.
        """
        parts = [name]
        if description:
            parts.append(description)
        if schema_def:
            # Include a compact summary of the schema for richer embeddings
            parts.append(_schema_to_text(schema_def))

        text = " • ".join(parts)
        return self.embed_text(text, model_name)

    def get_model_dimension(self, model_name: str) -> int:
        """Return the embedding dimension for the given model."""
        model = self._get_model(model_name)
        return model.get_sentence_embedding_dimension()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _schema_to_text(schema: dict) -> str:
    """
    Convert a JSON schema dict to a compact text representation
    suitable for embedding.  Only includes the most semantically
    meaningful fields.
    """
    parts: list[str] = []

    # Top-level description
    if "description" in schema:
        parts.append(schema["description"])

    # Function-calling style
    if "parameters" in schema:
        params = schema["parameters"]
        if isinstance(params, dict):
            for pname, pdef in params.get("properties", {}).items():
                desc = pdef.get("description", pdef.get("type", ""))
                parts.append(f"{pname}: {desc}")

    # OpenAPI inputSchema style
    if "inputSchema" in schema:
        input_schema = schema["inputSchema"]
        if isinstance(input_schema, dict):
            for pname, pdef in input_schema.get("properties", {}).items():
                desc = pdef.get("description", pdef.get("type", ""))
                parts.append(f"{pname}: {desc}")

    return "; ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# Module-level singleton (shared across the application)
# ---------------------------------------------------------------------------
embedding_service = EmbeddingService()
