"""
Conversation Session Management Service

Manages multi-turn conversation sessions using Redis for storage.
Supports different memory types (buffer, summary, vector) based on agent configuration.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger("ntr.services.conversation_service")


class ConversationService:
    """Manages conversation sessions with Redis storage"""
    
    def __init__(self, redis_client: aioredis.Redis, ttl_seconds: int = 3600):
        """
        Initialize conversation service.
        
        Args:
            redis_client: Redis client instance
            ttl_seconds: Time-to-live for conversation sessions (default: 1 hour)
        """
        self.ttl_seconds = ttl_seconds
        self.redis = redis_client
    
    async def get_or_create_session(
        self,
        session_id: str,
        agent_id: uuid.UUID
    ) -> dict[str, Any]:
        """
        Get existing session or create new one.
        
        Args:
            session_id: Unique session identifier
            agent_id: Agent UUID for this session
            
        Returns:
            Session metadata dictionary
        """
        key = f"conversation:{session_id}"
        exists = await self.redis.exists(key)
        
        if not exists:
            session_data = {
                "session_id": session_id,
                "agent_id": str(agent_id),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "message_count": 0,
            }
            await self.redis.setex(
                f"{key}:metadata",
                self.ttl_seconds,
                json.dumps(session_data)
            )
            logger.info(f"Created new conversation session: {session_id}")
        
        return {"session_id": session_id}
    
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None
    ) -> None:
        """
        Add message to conversation history.
        
        Args:
            session_id: Session identifier
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional metadata dictionary
        """
        key = f"conversation:{session_id}"
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
        }
        
        await self.redis.rpush(key, json.dumps(message))
        await self.redis.expire(key, self.ttl_seconds)
        logger.debug(f"Added {role} message to session {session_id}")
    
    async def get_history(
        self,
        session_id: str,
        limit: int = 10,
        memory_type: str = "buffer"
    ) -> list[dict[str, Any]]:
        """
        Retrieve conversation history based on memory type.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to retrieve
            memory_type: Memory strategy (buffer, summary, vector)
            
        Returns:
            List of message dictionaries
            
        Memory Types:
        - buffer: Last N messages (simple)
        - summary: Summarized history + recent messages (future)
        - vector: Semantically relevant messages (future)
        """
        if memory_type == "buffer":
            return await self._get_buffer_history(session_id, limit)
        elif memory_type == "summary":
            # Future: implement summarization
            logger.warning(f"Summary memory type not yet implemented, falling back to buffer")
            return await self._get_buffer_history(session_id, limit)
        elif memory_type == "vector":
            # Future: implement semantic search
            logger.warning(f"Vector memory type not yet implemented, falling back to buffer")
            return await self._get_buffer_history(session_id, limit)
        else:
            return await self._get_buffer_history(session_id, limit)
    
    async def _get_buffer_history(
        self,
        session_id: str,
        limit: int
    ) -> list[dict[str, Any]]:
        """
        Simple buffer: return last N messages.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages
            
        Returns:
            List of message dictionaries
        """
        key = f"conversation:{session_id}"
        exists = await self.redis.exists(key)
        
        if not exists:
            logger.debug(f"No history found for session {session_id}")
            return []
        
        # Get last N messages
        messages = await self.redis.lrange(key, -limit, -1)
        history = [json.loads(msg) for msg in messages]
        logger.debug(f"Retrieved {len(history)} messages from session {session_id}")
        return history
    
    async def clear_session(self, session_id: str) -> None:
        """
        Clear conversation session.
        
        Args:
            session_id: Session identifier to clear
        """
        key = f"conversation:{session_id}"
        await self.redis.delete(key)
        await self.redis.delete(f"{key}:metadata")
        logger.info(f"Cleared conversation session: {session_id}")
    
    async def get_session_metadata(self, session_id: str) -> dict[str, Any] | None:
        """
        Get session metadata.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session metadata dictionary or None if not found
        """
        key = f"conversation:{session_id}:metadata"
        data = await self.redis.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def update_session_metadata(
        self,
        session_id: str,
        metadata: dict[str, Any]
    ) -> None:
        """
        Update session metadata.
        
        Args:
            session_id: Session identifier
            metadata: Metadata dictionary to update
        """
        key = f"conversation:{session_id}:metadata"
        existing = await self.get_session_metadata(session_id)
        
        if existing:
            existing.update(metadata)
            await self.redis.setex(key, self.ttl_seconds, json.dumps(existing))
            logger.debug(f"Updated metadata for session {session_id}")

# Made with Bob
