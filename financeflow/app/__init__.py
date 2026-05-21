"""
Initialize configuration and core services.
"""
from app.config.settings import config
from app.config.logging import logger, setup_logging
from app.observability.telemetry import setup_observability

# Initialize logging
setup_logging()
logger.info(
    "FinanceFlow platform initializing",
    extra={
        "app_name": config.name,
        "version": config.version,
        "environment": config.fastapi.env
    }
)

# Initialize observability
setup_observability()

__all__ = ["config", "logger"]
