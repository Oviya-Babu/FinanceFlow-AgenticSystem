"""
Test suite for FinanceFlow platform.
"""
import pytest
import asyncio
from app.config.settings import config
from app.config.logging import logger
from app.memory.redis import redis_memory


@pytest.fixture
async def redis_client():
    """Fixture for Redis client."""
    await redis_memory.connect()
    yield redis_memory
    await redis_memory.disconnect()


@pytest.mark.asyncio
async def test_redis_connection(redis_client):
    """Test Redis connection."""
    assert redis_client.redis is not None


@pytest.mark.asyncio
async def test_redis_session_storage(redis_client):
    """Test session storage in Redis."""
    test_session = {
        "session_id": "test-123",
        "agent_id": "test-agent",
        "data": {"key": "value"}
    }
    
    await redis_client.set_session(test_session["session_id"], test_session)
    retrieved = await redis_client.get_session(test_session["session_id"])
    
    assert retrieved is not None
    assert retrieved["agent_id"] == "test-agent"


def test_config_loading():
    """Test configuration loading."""
    assert config.app_name == "FinanceFlow"
    assert config.ollama.model == "llama3.2:3b"
    assert config.redis.host == "localhost"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
