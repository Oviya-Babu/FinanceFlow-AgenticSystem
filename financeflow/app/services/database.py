"""
SQLite enterprise data models and database setup.
Provides financial records, market data, and internal datasets.
"""
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Text, Boolean
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

from app.config.settings import config
from app.config.logging import logger

# Create base class for ORM models
Base = declarative_base()


class FinancialRecord(Base):
    """Financial record model for internal data."""
    __tablename__ = "financial_records"
    
    id = Column(Integer, primary_key=True)
    company_symbol = Column(String(10), index=True)
    date = Column(DateTime, default=datetime.utcnow, index=True)
    revenue = Column(Float)
    expense = Column(Float)
    profit = Column(Float)
    market_cap = Column(Float)
    pe_ratio = Column(Float)
    sector = Column(String(50))
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MarketData(Base):
    """Market data model."""
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), index=True)
    date = Column(DateTime, default=datetime.utcnow, index=True)
    open_price = Column(Float)
    close_price = Column(Float)
    high_price = Column(Float)
    low_price = Column(Float)
    volume = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


class ResearchTask(Base):
    """Research task tracking model."""
    __tablename__ = "research_tasks"
    
    id = Column(Integer, primary_key=True)
    task_id = Column(String(100), unique=True, index=True)
    description = Column(Text)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    assigned_agent = Column(String(50))
    priority = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class ExecutionTrace(Base):
    """Execution trace for observability."""
    __tablename__ = "execution_traces"
    
    id = Column(Integer, primary_key=True)
    trace_id = Column(String(100), unique=True, index=True)
    session_id = Column(String(100), index=True)
    agent_id = Column(String(50), index=True)
    tool_name = Column(String(100))
    tool_input = Column(Text)
    tool_output = Column(Text, nullable=True)
    status = Column(String(20), default="pending")  # pending, running, completed, failed
    error = Column(Text, nullable=True)
    duration_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class DatabaseManager:
    """SQLite database initialization and management."""
    
    def __init__(self):
        """Initialize database manager."""
        self.engine = None
        self.async_session = None
    
    async def init_db(self) -> None:
        """Initialize database connection and create tables."""
        try:
            # Ensure data directory exists
            os.makedirs(os.path.dirname(config.sqlite.db_path) or ".", exist_ok=True)
            
            # For async, we would use create_async_engine, but for development
            # we'll use the sync version with a sync approach
            db_url = config.sqlite.database_url.replace("sqlite:///", "sqlite:///")
            
            # Create sync engine first to initialize tables
            sync_engine = create_engine(
                f"sqlite:///{config.sqlite.db_path}",
                echo=config.sqlite.echo,
                future=True
            )
            
            # Create all tables
            Base.metadata.create_all(sync_engine)
            
            self.engine = sync_engine
            logger.info("Database initialized", extra={"path": config.sqlite.db_path})
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def get_session(self):
        """Get database session."""
        if self.engine is None:
            raise RuntimeError("Database not initialized")
        
        Session = sessionmaker(bind=self.engine, future=True)
        return Session()
    
    async def close(self) -> None:
        """Close database connection."""
        if self.engine:
            self.engine.dispose()
            logger.info("Database connection closed")


# Global database manager instance
db_manager = DatabaseManager()


# Sample data population
async def populate_sample_data() -> None:
    """Populate database with sample financial data."""
    try:
        session = db_manager.get_session()
        
        # Check if data already exists
        existing = session.query(FinancialRecord).first()
        if existing:
            logger.info("Sample data already exists")
            session.close()
            return
        
        # Add sample financial records
        sample_records = [
            FinancialRecord(
                company_symbol="NVDA",
                date=datetime(2024, 1, 15),
                revenue=60.9e9,
                expense=20.3e9,
                profit=40.6e9,
                market_cap=2.1e12,
                pe_ratio=42.5,
                sector="Technology"
            ),
            FinancialRecord(
                company_symbol="MSFT",
                date=datetime(2024, 1, 15),
                revenue=52.9e9,
                expense=18.4e9,
                profit=34.5e9,
                market_cap=2.8e12,
                pe_ratio=35.2,
                sector="Technology"
            ),
            FinancialRecord(
                company_symbol="JPM",
                date=datetime(2024, 1, 15),
                revenue=40.2e9,
                expense=28.5e9,
                profit=11.7e9,
                market_cap=520e9,
                pe_ratio=12.5,
                sector="Finance"
            ),
        ]
        
        session.add_all(sample_records)
        session.commit()
        logger.info("Sample financial data populated", extra={"count": len(sample_records)})
        session.close()
        
    except Exception as e:
        logger.warning(f"Failed to populate sample data: {e}")
