# Backend Main Application
# CLIMARISK-OG API

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import routers
from .routers import hazards, data, analysis, reports, climate_data

# CLIMADA Impact Service — initialised at import time as a module-level singleton
from app.services.climada_impact import climada_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    logger.info("CLIMARISK-OG Backend starting...")

    # Passo 1: CLIMADA ImpactFuncSet — curvas de vulnerabilidade por tipo de ativo
    asset_count = len(climada_service.get_available_asset_types())
    logger.info(
        "ClimadaImpactService: %d tipos de ativo carregados. CLIMADA nativo: %s",
        asset_count,
        climada_service.climada_available,
    )

    # TODO (Passo 2): climada.Hazard ← ERA5 Zarr; climada.Exposures ← shapefiles; Impact.calc()
    # TODO (Passo 3): climada-petals — TropCyclone, StormEurope, hazards probabilísticos

    yield

    logger.info("CLIMARISK-OG Backend shutting down...")

# Create FastAPI app
app = FastAPI(
    title="CLIMARISK-OG API",
    description="Climate Risk Pricing Platform for Offshore Operations (CLIMADA-powered)",
    version="0.2.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan
)

# Middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:4173",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:4173",
        "http://localhost:8000",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://climarisk-og-production.up.railway.app",
        "https://climarisk-og.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(hazards.router, prefix="/api/v1/hazards", tags=["Hazards"])
app.include_router(data.router, prefix="/api/v1/data", tags=["Data"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(reports.router, prefix="/api/v1/reports", tags=["Reports"])
app.include_router(climate_data.router, prefix="/api/v1/climate", tags=["Climate Data"])

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "service": "CLIMARISK-OG API",
        "version": "0.2.0",
        "climada": {
            "available": climada_service.climada_available,
            "asset_types": len(climada_service.get_available_asset_types()),
            "step": "Passo 1 — ImpactFuncSet (curvas de vulnerabilidade)",
        },
    }

# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API info"""
    return {
        "message": "Welcome to CLIMARISK-OG API",
        "docs": "/api/docs",
        "version": "0.1.0",
        "endpoints": {
            "hazards": "/api/v1/hazards",
            "data": "/api/v1/data",
            "analysis": "/api/v1/analysis",
            "reports": "/api/v1/reports"
        }
    }

# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={
        "status": "error",
        "message": "Internal server error",
        "detail": str(exc)
    })

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "False").lower() == "true"
    )


