"""
Configuration management for FinanceFlow platform.
Loads settings from environment variables with pydantic validation.
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class OllamaConfig(BaseSettings):
    """Ollama LLM runtime configuration."""
    host: str = "http://localhost:11434"
    model: str = "llama3.2:3b"
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048
    
    class Config:
        env_prefix = "OLLAMA_"


class RedisConfig(BaseSettings):
    """Redis memory and session store configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    connection_pool_size: int = 10
    
    class Config:
        env_prefix = "REDIS_"
    
    @property
    def redis_url(self) -> str:
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


class SQLiteConfig(BaseSettings):
    """SQLite enterprise data store configuration."""
    db_path: str = "./data/financeflow.db"
    echo: bool = False
    
    class Config:
        env_prefix = "SQLITE_"
    
    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.db_path}"


class OpenTelemetryConfig(BaseSettings):
    """OpenTelemetry observability configuration."""
    enabled: bool = True
    exporter_otlp_endpoint: str = "http://localhost:4317"
    jaeger_enabled: bool = True
    jaeger_agent_host: str = "localhost"
    jaeger_agent_port: int = 6831
    jaeger_sampler_type: str = "const"
    jaeger_sampler_param: float = 1.0
    
    class Config:
        env_prefix = "OTEL_"


class PrometheusConfig(BaseSettings):
    """Prometheus metrics configuration."""
    enabled: bool = True
    port: int = 9090
    host: str = "0.0.0.0"
    
    class Config:
        env_prefix = "PROMETHEUS_"


class LoggingConfig(BaseSettings):
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"  # json or text
    include_timestamps: bool = True
    include_trace_ids: bool = True
    
    class Config:
        env_prefix = "LOG_"


class FastAPIConfig(BaseSettings):
    """FastAPI server configuration."""
    env: str = "development"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = True
    
    class Config:
        env_prefix = "FASTAPI_"


class AppConfig(BaseSettings):
    """Application metadata and configuration."""
    name: str = "FinanceFlow"
    version: str = "1.0.0"
    description: str = "Enterprise Autonomous Financial Research & Reporting Platform"
    
    # Subsystem configs
    fastapi: FastAPIConfig = FastAPIConfig()
    ollama: OllamaConfig = OllamaConfig()
    redis: RedisConfig = RedisConfig()
    sqlite: SQLiteConfig = SQLiteConfig()
    opentelemetry: OpenTelemetryConfig = OpenTelemetryConfig()
    prometheus: PrometheusConfig = PrometheusConfig()
    logging: LoggingConfig = LoggingConfig()
    
    # Agent configuration
    agent_timeout: int = 300  # seconds
    agent_max_iterations: int = 20
    agent_memory_ttl: int = 3600  # seconds
    
    # Observability hooks (for AgentGuard-X integration)
    enable_observability_hooks: bool = True
    enable_tool_interception_hooks: bool = True
    enable_traffic_correlation: bool = True
    
    # Safety configuration - Simulation mode for dangerous tools
    simulation_mode: bool = True  # Enable safe simulation of dangerous operations
    allow_external_email: bool = False  # Never send real emails
    allow_agent_spawning: bool = False  # Never spawn real agent processes
    max_agent_instances: int = 10  # Maximum concurrent agents
    
    class Config:
        extra = "ignore"
        env_prefix = "APP_"
        env_file = ".env"
        case_sensitive = False


# Global config instance
config = AppConfig()
