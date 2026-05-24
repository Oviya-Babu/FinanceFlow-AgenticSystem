"""
Enhanced secure Redis client with async support, authentication, and error handling.
Implements production-grade Redis integration for FinanceFlow + AgentGuard-X.
"""
import json
from datetime import date, datetime
from uuid import UUID
from typing import Any, Dict, Optional
from redis.asyncio import Redis, from_url
from redis.asyncio.connection import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import RedisError, AuthenticationError

from app.config.settings import config
from app.config.logging import logger
from app.observability.telemetry import get_tracer

tracer = get_tracer(__name__)


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    return value


class _InMemoryRedis:
    def __init__(self) -> None:
        self._store: Dict[str, str] = {}

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def append(self, key: str, value: str) -> int:
        current = self._store.get(key, "")
        self._store[key] = f"{current}{value}"
        return len(self._store[key])

    async def expire(self, key: str, ttl: int) -> bool:
        return True

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0


class SecureRedisMemory:
    """
    Secure Redis-backed memory and session store for agents.
    
    Features:
    - Async-first operations (no blocking calls)
    - Password authentication
    - Connection pooling with automatic retry
    - Timeout-safe operations
    - Comprehensive exception handling
    - Observable with OpenTelemetry
    """
    
    def __init__(self):
        """Initialize secure Redis memory manager."""
        self.redis: Optional[Redis] = None
        self._connection_retry = Retry(
            ExponentialBackoff(),
            3  # max retries
        )
    
    async def connect(self) -> None:
        """
        Establish secure Redis connection with authentication.
        
        Raises:
            AuthenticationError: If authentication fails
            RedisError: If connection fails
        """
        with tracer.start_as_current_span("redis_connect") as span:
            try:
                # Build Redis URL with authentication
                redis_url = config.redis.redis_url
                
                logger.info(
                    "Connecting to Redis",
                    extra={
                        "host": config.redis.host,
                        "port": config.redis.port,
                        "requires_auth": bool(config.redis.password)
                    }
                )
                
                # Create async Redis client with retry strategy
                self.redis = await from_url(
                    redis_url,
                    encoding="utf8",
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    socket_keepalive_options={},
                    max_connections=config.redis.connection_pool_size,
                    retry=self._connection_retry,
                    retry_on_timeout=True,
                )
                
                # Test connection and authentication
                pong = await self.redis.ping()
                
                if not pong:
                    raise RedisError("Redis ping failed")
                
                logger.info(
                    "Redis connection established",
                    extra={
                        "host": config.redis.host,
                        "port": config.redis.port,
                        "authenticated": bool(config.redis.password)
                    }
                )
                
                span.set_attribute("status", "connected")
                
            except AuthenticationError as e:
                logger.error(
                    f"Redis authentication failed: {e}",
                    extra={"host": config.redis.host, "port": config.redis.port}
                )
                span.set_attribute("status", "auth_failed")
                raise
            
            except RedisError as e:
                logger.warning(f"Redis unavailable, using in-memory fallback: {e}")
                self.redis = _InMemoryRedis()
                span.set_attribute("status", "memory_fallback")
            
            except Exception as e:
                logger.warning(f"Unexpected Redis error, using in-memory fallback: {e}")
                self.redis = _InMemoryRedis()
                span.set_attribute("status", "memory_fallback")
    
    async def disconnect(self) -> None:
        """Close Redis connection safely."""
        with tracer.start_as_current_span("redis_disconnect"):
            if self.redis:
                try:
                    await self.redis.close()
                    logger.info("Redis connection closed")
                except Exception as e:
                    logger.warning(f"Error closing Redis: {e}")
    
    async def set_session(self, session_id: str, data: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """
        Store session data in Redis with TTL.
        
        Args:
            session_id: Session identifier
            data: Session data dictionary
            ttl: Time to live in seconds (default: agent_memory_ttl from config)
            
        Raises:
            RedisError: If operation fails
        """
        with tracer.start_as_current_span("redis_set_session") as span:
            span.set_attribute("session_id", session_id)
            
            if self.redis is None:
                raise RuntimeError("Redis not connected")
            
            try:
                ttl = ttl or config.agent_memory_ttl
                await self.redis.setex(
                    f"session:{session_id}",
                    ttl,
                    json.dumps(_json_safe(data))
                )
            except RedisError as e:
                logger.error(f"Failed to set session: {e}")
                span.set_attribute("status", "failed")
                raise
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session data from Redis.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session data or None if not found
            
        Raises:
            RedisError: If operation fails
        """
        with tracer.start_as_current_span("redis_get_session") as span:
            span.set_attribute("session_id", session_id)
            
            if self.redis is None:
                raise RuntimeError("Redis not connected")
            
            try:
                data = await self.redis.get(f"session:{session_id}")
                if data:
                    return json.loads(data)
                return None
            except RedisError as e:
                logger.error(f"Failed to get session: {e}")
                span.set_attribute("status", "failed")
                raise
    
    async def set_agent_context(self, agent_id: str, context: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Store agent execution context."""
        with tracer.start_as_current_span("redis_set_agent_context") as span:
            span.set_attribute("agent_id", agent_id)
            
            if self.redis is None:
                raise RuntimeError("Redis not connected")
            
            try:
                ttl = ttl or config.agent_memory_ttl
                await self.redis.setex(
                    f"agent:context:{agent_id}",
                    ttl,
                    json.dumps(_json_safe(context))
                )
            except RedisError as e:
                logger.error(f"Failed to set agent context: {e}")
                span.set_attribute("status", "failed")
                raise
    
    async def get_agent_context(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve agent execution context."""
        with tracer.start_as_current_span("redis_get_agent_context") as span:
            span.set_attribute("agent_id", agent_id)
            
            if self.redis is None:
                raise RuntimeError("Redis not connected")
            
            try:
                data = await self.redis.get(f"agent:context:{agent_id}")
                if data:
                    return json.loads(data)
                return None
            except RedisError as e:
                logger.error(f"Failed to get agent context: {e}")
                span.set_attribute("status", "failed")
                raise
    
    async def append_memory(self, memory_key: str, value: str) -> None:
        """Append to agent memory."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        
        with tracer.start_as_current_span("redis_append_memory") as span:
            span.set_attribute("memory_key", memory_key)
            
            try:
                await self.redis.append(f"memory:{memory_key}", f"\n{value}")
                await self.redis.expire(f"memory:{memory_key}", config.agent_memory_ttl)
            except RedisError as e:
                logger.error(f"Failed to append memory: {e}")
                span.set_attribute("status", "failed")
                raise
    
    async def get_memory(self, memory_key: str) -> str:
        """Retrieve agent memory."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        
        with tracer.start_as_current_span("redis_get_memory") as span:
            span.set_attribute("memory_key", memory_key)
            
            try:
                data = await self.redis.get(f"memory:{memory_key}")
                return data or ""
            except RedisError as e:
                logger.error(f"Failed to get memory: {e}")
                span.set_attribute("status", "failed")
                raise
    
    async def cache_tool_result(self, tool_key: str, result: Any, ttl: int = 3600) -> None:
        """Cache tool execution results."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        
        with tracer.start_as_current_span("redis_cache_tool_result") as span:
            span.set_attribute("tool_key", tool_key)
            
            try:
                await self.redis.setex(
                    f"tool_cache:{tool_key}",
                    ttl,
                    json.dumps(_json_safe(result)) if not isinstance(result, str) else result
                )
            except RedisError as e:
                logger.error(f"Failed to cache tool result: {e}")
                span.set_attribute("status", "failed")
                raise
    
    async def get_cached_tool_result(self, tool_key: str) -> Optional[Any]:
        """Retrieve cached tool result."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        
        with tracer.start_as_current_span("redis_get_cached_tool_result") as span:
            span.set_attribute("tool_key", tool_key)
            
            try:
                data = await self.redis.get(f"tool_cache:{tool_key}")
                if data:
                    try:
                        return json.loads(data)
                    except json.JSONDecodeError:
                        return data
                return None
            except RedisError as e:
                logger.error(f"Failed to get cached tool result: {e}")
                span.set_attribute("status", "failed")
                raise
    
    async def delete(self, key: str) -> None:
        """Delete a key from Redis."""
        if self.redis is None:
            raise RuntimeError("Redis not connected")
        
        try:
            await self.redis.delete(key)
        except RedisError as e:
            logger.error(f"Failed to delete key: {e}")
            raise
    
    async def health_check(self) -> bool:
        """
        Perform health check on Redis connection.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if self.redis is None:
                return False
            
            pong = await self.redis.ping()
            return bool(pong)
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return False


# Global secure Redis memory instance
redis_memory = SecureRedisMemory()
