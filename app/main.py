"""Production FastAPI Application Module.

Provides the central FastAPI app instance with CORS, lifespan database initialization,
health check endpoints, and standardized routing.
"""

import asyncio
import httpx
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.database import init_db
from app.routers.main import router

logger = logging.getLogger("app.main")


async def openwa_keepalive_worker():
    """
    Continuous background keep-alive worker to prevent OpenWA and backend
    from spinning down / sleeping on Render's 15-minute inactivity limit.
    Pings every 5 minutes (300s).
    """
    # Wait 20 seconds after startup before the first ping
    await asyncio.sleep(20)
    while True:
        try:
            base_url = (getattr(settings, "OPENWA_BASE_URL", "") or "").strip().rstrip("/")
            if base_url and not any(h in base_url for h in ["localhost", "127.0.0.1", "host.docker.internal"]):
                async with httpx.AsyncClient(timeout=45.0) as client:
                    res = await client.get(f"{base_url}/health")
                    logger.info(f"OpenWA keep-alive ping: {res.status_code} (preventing Render sleep)")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"OpenWA keep-alive probe note: {e}")

        # Sleep for 5 minutes (300s) — safely under Render's 15-minute idle cutoff
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    # Initialize database tables on startup
    await init_db()
    # Start the continuous 24/7 keep-alive background worker
    keepalive_task = asyncio.create_task(openwa_keepalive_worker())
    yield
    # Graceful shutdown
    keepalive_task.cancel()
    try:
        await keepalive_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Enterprise AI Voice & WhatsApp Outreach Platform",
    lifespan=lifespan
)

# CORS middleware
origins = {
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
}
if settings.FRONTEND_ORIGIN:
    for o in settings.FRONTEND_ORIGIN.split(","):
        cleaned = o.strip().rstrip("/")
        if cleaned:
            origins.add(cleaned)

allow_all = "*" in origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all else list(origins),
    allow_origin_regex=r"https://.*\.pages\.dev" if not allow_all else None,
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
@app.get("/api/health", tags=["System"])
async def health_check():
    """Service liveness probe."""
    return {"status": "healthy", "service": settings.PROJECT_NAME, "version": "1.0.0"}

@app.get("/ready", tags=["System"])
@app.get("/api/ready", tags=["System"])
async def ready_check():
    """Service readiness probe."""
    return {"status": "ready"}
