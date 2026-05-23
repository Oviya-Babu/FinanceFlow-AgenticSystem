"""
Initialize configuration and core services.
"""
from app.config.settings import config
from app.config.logging import logger, setup_logging

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

__all__ = ["config", "logger"]
