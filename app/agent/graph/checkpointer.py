"""LangGraph Checkpointer and Stable Thread Management."""

import logging
from typing import Optional, Any
from langgraph.checkpoint.memory import MemorySaver
from app.config import settings

logger = logging.getLogger(__name__)

# Global in-memory saver instance for testing and transient sessions
_in_memory_checkpointer = MemorySaver()

def get_stable_thread_id(call_id: str) -> str:
    """Produce a deterministic, secure thread identifier for a call conversation."""
    return f"call_thread_{call_id}"

async def get_checkpointer(use_postgres: bool = False) -> Any:
    """
    Returns an async checkpointer.
    Uses AsyncPostgresSaver when configured with PostgreSQL,
    or MemorySaver for unit tests and lightweight operations.
    """
    if use_postgres and hasattr(settings, "DATABASE_URL") and "postgres" in settings.DATABASE_URL:
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            # Connection string format for psycopg
            pg_conn = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
            # Note: AsyncPostgresSaver setup requires async context
            checkpointer = AsyncPostgresSaver.from_conn_string(pg_conn)
            return checkpointer
        except Exception as e:
            logger.warning(f"Failed to initialize AsyncPostgresSaver ({e}); using MemorySaver.")

    return _in_memory_checkpointer
