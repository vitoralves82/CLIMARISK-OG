# CLIMARISK-OG Backend — main.py
# Rebuilt with CORS, modular routers (resilient), and CLIMADA service integration.

from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── CORS origins ──────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
    "https://climarisk-og-production.up.railway.app",
    "https://climarisk-og.vercel.app",
    "https://climarisk-og-git-main-vitoralves82s-projects.vercel.app",
]

# ── Track which routers loaded successfully ───────────────────────────────────
_loaded_routers: list[str] = []
_failed_routers: dict[str, str] = {}


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CLIMARISK-OG backend starting up. Loaded routers: %s", _loaded_routers)
    if _failed_routers:
        logger.warning("Routers that failed to load: %s", _failed_routers)
    yield
    logger.info("CLIMARISK-OG backend shutting down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="CLIMARISK-OG API",
    version="0.2.0",
    description=(
        "Climate Risk API for Oil & Gas Assets (Petrobras). "
        "Powered by ERA5, CLIMADA impact functions, and Cloudflare R2."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routers — each wrapped in try/except for resilience ──────────────────────
# If a router's imports fail (e.g. missing optional dependency), the server
# continues to run and other routers remain available.

try:
    from app.routers.hazards import router as hazards_router
    app.include_router(hazards_router, prefix="/api/v1/hazards", tags=["Hazards"])
    _loaded_routers.append("hazards")
    logger.info("Router 'hazards' loaded.")
except Exception as exc:
    _failed_routers["hazards"] = str(exc)
    logger.error("Router 'hazards' failed to load: %s", exc)

try:
    from app.routers.data import router as data_router
    app.include_router(data_router, prefix="/api/v1/data", tags=["Data"])
    _loaded_routers.append("data")
    logger.info("Router 'data' loaded.")
except Exception as exc:
    _failed_routers["data"] = str(exc)
    logger.error("Router 'data' failed to load: %s", exc)

try:
    from app.routers.analysis import router as analysis_router
    app.include_router(analysis_router, prefix="/api/v1/analysis", tags=["Analysis"])
    _loaded_routers.append("analysis")
    logger.info("Router 'analysis' loaded.")
except Exception as exc:
    _failed_routers["analysis"] = str(exc)
    logger.error("Router 'analysis' failed to load: %s", exc)

try:
    from app.routers.reports import router as reports_router
    app.include_router(reports_router, prefix="/api/v1/reports", tags=["Reports"])
    _loaded_routers.append("reports")
    logger.info("Router 'reports' loaded.")
except Exception as exc:
    _failed_routers["reports"] = str(exc)
    logger.error("Router 'reports' failed to load: %s", exc)

try:
    from app.routers.climate_data import router as climate_data_router
    app.include_router(climate_data_router, prefix="/api/v1/climate", tags=["Climate Data"])
    _loaded_routers.append("climate_data")
    logger.info("Router 'climate_data' loaded.")
except Exception as exc:
    _failed_routers["climate_data"] = str(exc)
    logger.error("Router 'climate_data' failed to load: %s", exc)

try:
    from app.routers import results
    app.include_router(results.router)
    _loaded_routers.append("results")
    logger.info("Router 'results' loaded.")
except Exception as exc:
    _failed_routers["results"] = str(exc)
    logger.error("Router 'results' failed to load: %s", exc)


# ── Core endpoints ────────────────────────────────────────────────────────────

@app.get("/", tags=["Status"])
def root():
    """API root — basic status and loaded router list."""
    return {
        "status": "ok",
        "message": "CLIMARISK-OG backend running",
        "version": "0.2.0",
        "loaded_routers": _loaded_routers,
        "failed_routers": _failed_routers,
        "docs": "/api/docs",
    }


@app.get("/health", tags=["Status"])
def health():
    """Health check — includes CLIMADA availability status."""
    climada_available = False
    climada_version = None
    try:
        from app.services.climada_impact import climada_service
        climada_available = climada_service.climada_available
        if climada_available:
            try:
                import climada
                climada_version = getattr(climada, "__version__", "unknown")
            except Exception:
                climada_version = "installed"
    except Exception:
        pass

    return {
        "status": "ok",
        "climada_available": climada_available,
        "climada_version": climada_version,
        "loaded_routers": _loaded_routers,
        "failed_routers": _failed_routers,
    }
