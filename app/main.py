"""Production FastAPI Application Module.

Provides the central FastAPI app instance with CORS, lifespan database initialization,
health check endpoints, and standardized routing.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers.main import router

logger = logging.getLogger("app.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Initialize database tables on startup
    await init_db()
    yield
    # Graceful shutdown


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Enterprise AI Voice & WhatsApp Outreach Platform",
    lifespan=lifespan
)

# CORS middleware
origins = list({
    settings.FRONTEND_ORIGIN,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
})

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Global handler for uncaught exceptions to ensure uniform error format and logging."""
    logger.error(f"Unhandled error processing {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error occurred. Please contact system administrator."}
    )

# Include API routers under /api
app.include_router(router, prefix="/api")

@app.get("/health", tags=["System"])
async def health_check():
    """Service liveness probe."""
    return {"status": "healthy", "service": settings.PROJECT_NAME, "version": "1.0.0"}

@app.get("/ready", tags=["System"])
async def ready_check():
    """Service readiness probe."""
    return {"status": "ready"}
