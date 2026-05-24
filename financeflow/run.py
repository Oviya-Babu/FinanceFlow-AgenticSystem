"""
Entry point for running FinanceFlow as a module.
"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.config.settings import config
from app.config.logging import logger


async def main():
    """Run the platform."""
    import uvicorn
    
    logger.info(
        f"Starting {config.name} v{config.version}",
        extra={
            "environment": config.fastapi.env,
            "host": config.fastapi.host,
            "port": config.fastapi.port
        }
    )
    
    config_dict = {
        "app": app,
        "host": config.fastapi.host,
        "port": config.fastapi.port,
        "reload": config.fastapi.reload,
        "log_level": config.logging.level.lower(),
    }
    
    server = uvicorn.Server(uvicorn.Config(**config_dict))
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Platform shutting down...")
        sys.exit(0)
