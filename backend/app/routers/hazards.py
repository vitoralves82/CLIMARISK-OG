# Hazards Router
# CLIMARISK-OG — API endpoints for hazard analysis with CLIMADA impact functions

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from datetime import date
import logging

from app.services.climada_impact import climada_service, ASSET_TYPES, HAZ_WIND, HAZ_WAVE

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def list_hazards():
    """List available hazards with their associated CLIMADA haz_type codes."""
    return {
        "hazards": [
            {
                "id": "wind",
                "name": "Vento",
                "climada_haz_type": HAZ_WIND,
                "description": "Velocidade do vento a 10m — componentes u10/v10 ERA5 (nós)",
                "variables": ["wind_speed_knots", "wind_direction_deg"],
                "intensity_unit": "kn",
                "source": "ERA5 — ECMWF Reanalysis v5",
            },
            {
                "id": "wave",
                "name": "Onda",
                "climada_haz_type": HAZ_WAVE,
                "description": "Altura Significativa de Onda (Hs) — campo hs ERA5 (metros)",
                "variables": ["significant_wave_height_m"],
                "intensity_unit": "m (Hs)",
                "source": "ERA5 — ECMWF Reanalysis v5",
            },
            {
                "id": "flood",
                "name": "Inundação",
                "climada_haz_type": "FL",
                "description": "Risco de inundação para instalações portuárias",
                "variables": ["precipitation_mm", "surge_height_m"],
                "intensity_unit": "m",
                "source": "Planejado para Passo 2 (climada-petals)",
            },
            {
                "id": "heatwave",
                "name": "Ondas Térmicas",
                "climada_haz_type": "HW",
                "description": "Ondas de calor e conforto térmico — operações externas",
                "variables": ["temperature_c", "heat_index", "wbgt"],
                "intensity_unit": "°C",
                "source": "Planejado para Passo 2",
            },
        ]
    }


@router.get("/asset-types")
async def list_asset_types():
    """
    List all offshore asset types supported by the CLIMADA vulnerability engine.

    Each asset type has calibrated ImpactFuncSet curves (wind + wave) that map
    hazard intensity to a continuous damage ratio (MDR = MDD × PAA).
    """
    return {
        "asset_types": climada_service.get_available_asset_types(),
        "default": "generic_offshore",
        "climada_available": climada_service.climada_available,
        "climada_note": (
            "CLIMADA ImpactFunc nativo ativo."
            if climada_service.climada_available
            else "CLIMADA não instalado — usando numpy interp como fallback equivalente."
        ),
    }


@router.get("/impact-functions")
async def list_impact_functions():
    """
    List all available CLIMADA impact functions (vulnerability curves).

    Returns metadata for every (asset_type, hazard) combination, including
    the calibration points (intensity → MDR) for frontend chart rendering.
    """
    result = {}
    for asset_id in ASSET_TYPES:
        result[asset_id] = {
            "asset_name": ASSET_TYPES[asset_id]["name"],
            "status": ASSET_TYPES[asset_id]["status"],
            "curves": {
                "wind": climada_service.get_curve_points(HAZ_WIND, asset_id),
                "wave": climada_service.get_curve_points(HAZ_WAVE, asset_id),
            },
        }
    return {
        "impact_functions": result,
        "climada_available": climada_service.climada_available,
        "haz_type_codes": {"wind": HAZ_WIND, "wave": HAZ_WAVE},
    }


@router.get("/impact-functions/{asset_type}")
async def get_impact_function(asset_type: str):
    """
    Return impact function curves for a specific asset type.

    Includes raw calibration points and a fine-grid interpolation for smooth
    frontend chart rendering.
    """
    if asset_type not in ASSET_TYPES:
        raise HTTPException(
            status_code=404,
            detail=f"Asset type '{asset_type}' not found. Available: {list(ASSET_TYPES.keys())}",
        )
    return {
        "asset_type": asset_type,
        "asset_name": ASSET_TYPES[asset_type]["name"],
        "description": ASSET_TYPES[asset_type]["description"],
        "references": ASSET_TYPES[asset_type]["references"],
        "status": ASSET_TYPES[asset_type]["status"],
        "curves": {
            "wind": climada_service.get_curve_points(HAZ_WIND, asset_type),
            "wave": climada_service.get_curve_points(HAZ_WAVE, asset_type),
        },
        "climada_available": climada_service.climada_available,
    }


@router.post("/wind/analyze")
async def analyze_wind(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    wind_threshold: float = Query(default=25.0, description="Wind speed threshold (knots)"),
    asset_type: str = Query(default="fpso", description="Asset type for vulnerability curve"),
):
    """
    Analyze wind hazard for a given location using CLIMADA impact functions.

    Returns the damage ratio at the given threshold intensity, plus curve metadata
    for the specified asset type. For a full time-series risk analysis, use
    ``POST /api/v1/analysis/multi-risk`` with ``hazards: ["wind"]``.
    """
    logger.info("Analyzing wind hazard at (%.4f, %.4f), asset_type=%s", lat, lon, asset_type)
    try:
        import numpy as np
        threshold_arr = np.array([wind_threshold])
        damage_ratio = float(climada_service.calc_damage_ratio(HAZ_WIND, threshold_arr, asset_type)[0])
        curve_meta = climada_service.describe_curve(HAZ_WIND, asset_type)
        return {
            "hazard_type": "wind",
            "location": {"lat": lat, "lon": lon},
            "analysis": {
                "threshold_knots": wind_threshold,
                "damage_ratio_at_threshold": round(damage_ratio, 4),
                "interpretation": (
                    f"A {wind_threshold:.1f} kn, o tipo de ativo '{asset_type}' "
                    f"apresenta MDR = {damage_ratio*100:.1f}% (damage ratio)."
                ),
            },
            "impact_function": curve_meta,
            "climada_available": climada_service.climada_available,
            "note": (
                "Para análise completa de série temporal com AAL/VaR/TVaR, "
                "use POST /api/v1/analysis/multi-risk com hazards=['wind'] e asset_type."
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/wave/analyze")
async def analyze_wave(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    wave_threshold: float = Query(default=4.0, description="Wave height threshold (Hs metres)"),
    asset_type: str = Query(default="fpso", description="Asset type for vulnerability curve"),
):
    """
    Analyze wave hazard for a given location using CLIMADA impact functions.

    Returns the damage ratio at the given Hs threshold for the asset type.
    """
    logger.info("Analyzing wave hazard at (%.4f, %.4f), asset_type=%s", lat, lon, asset_type)
    try:
        import numpy as np
        threshold_arr = np.array([wave_threshold])
        damage_ratio = float(climada_service.calc_damage_ratio(HAZ_WAVE, threshold_arr, asset_type)[0])
        curve_meta = climada_service.describe_curve(HAZ_WAVE, asset_type)
        return {
            "hazard_type": "wave",
            "location": {"lat": lat, "lon": lon},
            "analysis": {
                "threshold_m_hs": wave_threshold,
                "damage_ratio_at_threshold": round(damage_ratio, 4),
                "interpretation": (
                    f"A Hs = {wave_threshold:.1f} m, o tipo de ativo '{asset_type}' "
                    f"apresenta MDR = {damage_ratio*100:.1f}% (damage ratio)."
                ),
            },
            "impact_function": curve_meta,
            "climada_available": climada_service.climada_available,
            "note": (
                "Para análise completa de série temporal com AAL/VaR/TVaR, "
                "use POST /api/v1/analysis/multi-risk com hazards=['wave'] e asset_type."
            ),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/flood/analyze")
async def analyze_flood(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    precip_threshold: float = Query(default=50.0, description="Precipitation threshold (mm)"),
):
    """
    Analyze flood hazard for a given location.

    Note: Flood ImpactFunctions and ERA5 precipitation time series integration
    are planned for Passo 2 (climada-petals).
    """
    logger.info("Flood analysis requested at (%.4f, %.4f) — Passo 2", lat, lon)
    return {
        "hazard_type": "flood",
        "location": {"lat": lat, "lon": lon},
        "status": "planned",
        "message": (
            "Análise de inundação planejada para integração no Passo 2 "
            "(climada-petals + dados de precipitação ERA5/CMEMS)."
        ),
    }


@router.post("/heatwave/analyze")
async def analyze_heatwave(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    temp_threshold: float = Query(default=32.0, description="Temperature threshold (Celsius)"),
):
    """
    Analyze heat wave hazard for a given location.

    Note: Heatwave ImpactFunctions are planned for Passo 2.
    """
    logger.info("Heatwave analysis requested at (%.4f, %.4f) — Passo 2", lat, lon)
    return {
        "hazard_type": "heatwave",
        "location": {"lat": lat, "lon": lon},
        "status": "planned",
        "message": (
            "Análise de ondas térmicas planejada para integração no Passo 2 "
            "(dados de temperatura ERA5 + índice WBGT para operações externas)."
        ),
    }
