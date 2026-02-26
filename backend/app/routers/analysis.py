# Analysis Router
# CLIMARISK-OG API endpoints for analysis operations

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
from app.services.zarr_reader import zarr_reader
from app.services.climada_impact import climada_service
import logging
from io import BytesIO
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)

router = APIRouter()


class WindRiskRequest(BaseModel):
    lat: float
    lon: float
    start_time: str
    end_time: str
    operational_max_knots: float = 15.0
    attention_max_knots: float = 20.0
    cost_attention_per_hour: Optional[float] = None
    cost_stop_per_hour: Optional[float] = None
    asset_type: str = "generic_offshore"


class HazardThreshold(BaseModel):
    operational_max: float
    attention_max: float


class MultiRiskRequest(BaseModel):
    lat: float
    lon: float
    start_time: str
    end_time: str
    hazards: List[str]
    thresholds: Dict[str, HazardThreshold]
    stop_cost_per_hour: Optional[float] = None
    combine_mode: str = "worst"
    weights: Optional[Dict[str, float]] = None
    multiplier: Optional[float] = None
    asset_value: Optional[float] = None
    attention_loss_factor: float = 0.35
    stop_loss_factor: float = 1.0
    exceedance_method: str = "weibull"
    risk_load_method: str = "none"
    risk_quantile: float = 0.95
    expense_ratio: float = 0.15
    include_series: bool = False
    asset_type: str = "generic_offshore"

@router.post("/run")
async def run_analysis(
    analysis_request: dict
):
    """
    Run climate risk analysis
    
    Request body:
    {
        "hazard_type": "wind" | "wave" | "flood" | "heatwave",
        "region": {
            "type": "point" | "polygon",
            "coordinates": [...] 
        },
        "period": {
            "start": "2015-01-01",
            "end": "2023-12-31"
        },
        "parameters": {
            "wind_threshold": 25.0,
            ...
        }
    }
    """
    logger.info(f"Running analysis: {analysis_request}")
    
    # TODO: Validate request
    # TODO: Queue async task
    # TODO: Return task ID
    
    return {
        "analysis_id": "analysis_001",
        "status": "queued",
        "message": "Analysis queued for processing"
    }


@router.post("/wind-risk")
async def run_wind_risk(request: WindRiskRequest):
    """Run wind risk analysis for a selected point using ERA5 Zarr."""
    try:
        return zarr_reader.get_wind_point_risk(
            lat=request.lat,
            lon=request.lon,
            start_time=request.start_time,
            end_time=request.end_time,
            operational_limit_knots=request.operational_max_knots,
            attention_limit_knots=request.attention_max_knots,
            cost_attention_per_hour=request.cost_attention_per_hour,
            cost_stop_per_hour=request.cost_stop_per_hour,
            asset_type=request.asset_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/multi-risk")
async def run_multi_risk(request: MultiRiskRequest):
    """Run multi-risk analysis for a selected point using ERA5 Zarr."""
    try:
        thresholds = {
            key: {
                "operational_max": value.operational_max,
                "attention_max": value.attention_max,
            }
            for key, value in request.thresholds.items()
        }

        return zarr_reader.get_multi_risk_point(
            lat=request.lat,
            lon=request.lon,
            start_time=request.start_time,
            end_time=request.end_time,
            hazards=request.hazards,
            thresholds=thresholds,
            stop_cost_per_hour=request.stop_cost_per_hour,
            combine_mode=request.combine_mode,
            weights=request.weights,
            multiplier=request.multiplier or 1.5,
            asset_value=request.asset_value,
            attention_loss_factor=request.attention_loss_factor,
            stop_loss_factor=request.stop_loss_factor,
            exceedance_method=request.exceedance_method,
            risk_load_method=request.risk_load_method,
            risk_quantile=request.risk_quantile,
            expense_ratio=request.expense_ratio,
            include_series=request.include_series,
            asset_type=request.asset_type,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/asset-types")
async def list_asset_types():
    """List available asset types for CLIMADA vulnerability curves."""
    return {
        "asset_types": climada_service.get_available_asset_types(),
        "default": "generic_offshore",
        "climada_available": climada_service.climada_available,
    }


@router.get("/vulnerability-curve")
async def get_vulnerability_curve(hazard: str, asset_type: str = "fpso"):
    """
    Return vulnerability curve points for a given hazard and asset type.

    Useful for frontend chart rendering (e.g., showing the damage ratio curve
    alongside the time series).

    - **hazard**: ``WS`` (wind, knots) or ``OW`` (wave, metres Hs)
    - **asset_type**: ``fpso``, ``fixed_platform``, ``support_vessel``,
      ``subsea_pipeline``, ``generic_offshore``
    """
    try:
        return climada_service.get_curve_points(hazard, asset_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/multi-risk-pdf")
async def run_multi_risk_pdf(request: MultiRiskRequest):
    """Generate PDF report for multi-risk analysis."""
    try:
        thresholds = {
            key: {
                "operational_max": value.operational_max,
                "attention_max": value.attention_max,
            }
            for key, value in request.thresholds.items()
        }

        result = zarr_reader.get_multi_risk_point(
            lat=request.lat,
            lon=request.lon,
            start_time=request.start_time,
            end_time=request.end_time,
            hazards=request.hazards,
            thresholds=thresholds,
            stop_cost_per_hour=request.stop_cost_per_hour,
            combine_mode=request.combine_mode,
            weights=request.weights,
            multiplier=request.multiplier or 1.5,
            asset_value=request.asset_value,
            attention_loss_factor=request.attention_loss_factor,
            stop_loss_factor=request.stop_loss_factor,
            exceedance_method=request.exceedance_method,
            risk_load_method=request.risk_load_method,
            risk_quantile=request.risk_quantile,
            expense_ratio=request.expense_ratio,
            include_series=True,
            asset_type=request.asset_type,
        )

        buffer = BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, height - 40, "Relatorio de Analise Multi-Risco")

        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, height - 60, f"Periodo: {request.start_time} a {request.end_time}")
        pdf.drawString(40, height - 75, f"Ponto: {request.lat:.5f}, {request.lon:.5f}")
        pdf.drawString(40, height - 90, f"Riscos: {', '.join(request.hazards)}")
        pdf.drawString(40, height - 105, f"Combinacao: {request.combine_mode}")

        y = height - 120
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Resumo por risco")
        y -= 16
        pdf.setFont("Helvetica", 10)
        for hazard, data in result["hazards"].items():
            pdf.drawString(
                40,
                y,
                f"{hazard}: media {data['mean']:.2f}, max {data['max']:.2f}, parada {data['stop_hours']}h",
            )
            y -= 14

        combined = result["combined"]
        y -= 6
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(40, y, "Resumo combinado")
        y -= 16
        pdf.setFont("Helvetica", 10)
        pdf.drawString(
            40,
            y,
            f"Operacional {combined['operational_hours']}h | Atencao {combined['attention_hours']}h | Parada {combined['stop_hours']}h",
        )
        y -= 14
        if result.get("pricing"):
            pdf.drawString(40, y, f"Custo total: {result['pricing']['total_cost']:.2f}")

        if result.get("metrics"):
            y -= 18
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(40, y, "Metricas (media, max, p50, p90, p95, p99)")
            y -= 14
            pdf.setFont("Helvetica", 9)
            for key, metrics in result["metrics"].items():
                pdf.drawString(
                    40,
                    y,
                    f"{key}: {metrics['mean']:.2f} | {metrics['max']:.2f} | {metrics['p50']:.2f} | {metrics['p90']:.2f} | {metrics['p95']:.2f} | {metrics['p99']:.2f}",
                )
                y -= 12

        if result.get("insights"):
            y -= 20
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(40, y, "Insights")
            pdf.setFont("Helvetica", 10)
            for insight in result["insights"]:
                y -= 14
                pdf.drawString(40, y, insight)

        pdf.showPage()

        # Charts
        time_values = np.array(result["time"], dtype="datetime64[ns]")
        for hazard, values in result.get("series", {}).items():
            if hazard == "wind_direction_deg":
                continue

            fig, axes = plt.subplots(3, 1, figsize=(6.5, 7))
            axes[0].plot(time_values, values)
            axes[0].set_title(f"Serie temporal - {hazard}")
            axes[0].set_ylabel(hazard)

            dist = result.get("distributions", {}).get(hazard, {})
            axes[1].bar(dist.get("hist_bins", []), dist.get("hist_counts", []), width=0.8)
            axes[1].set_title("Histograma")
            axes[1].set_ylabel("Frequencia")

            axes[2].plot(dist.get("exceedance_values", []), dist.get("exceedance_probs", []))
            axes[2].set_title("Excedencia")
            axes[2].set_xlabel("Valor")
            axes[2].set_ylabel("Prob.")

            fig.autofmt_xdate()
            fig.tight_layout()
            img_buf = BytesIO()
            fig.savefig(img_buf, format="png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            img_buf.seek(0)
            pdf.drawImage(ImageReader(img_buf), 30, 80, width=550, height=720)
            pdf.showPage()

        combined_exc = result.get("combined_exceedance", {})
        if combined_exc.get("values"):
            fig, ax = plt.subplots(figsize=(6.5, 4))
            ax.plot(combined_exc.get("values", []), combined_exc.get("probs", []))
            ax.set_title("Excedencia combinada")
            ax.set_xlabel("Severidade combinada")
            ax.set_ylabel("Prob.")
            fig.tight_layout()
            img_buf = BytesIO()
            fig.savefig(img_buf, format="png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            img_buf.seek(0)
            pdf.drawImage(ImageReader(img_buf), 30, 200, width=550, height=400)
            pdf.showPage()

        wind_rose = result.get("wind_rose")
        if wind_rose and wind_rose.get("counts"):
            counts = np.array(wind_rose["counts"], dtype=float)
            labels = wind_rose["bins"]
            angles = np.linspace(0, 2 * np.pi, len(counts), endpoint=False)
            fig = plt.figure(figsize=(6, 6))
            ax = fig.add_subplot(111, projection="polar")
            ax.bar(angles, counts, width=(2 * np.pi / len(counts)), bottom=0.0)
            ax.set_title("Rosa dos ventos")
            ax.set_xticks(angles)
            ax.set_xticklabels(labels, fontsize=7)
            fig.tight_layout()
            img_buf = BytesIO()
            fig.savefig(img_buf, format="png", dpi=150, bbox_inches="tight")
            plt.close(fig)
            img_buf.seek(0)
            pdf.drawImage(ImageReader(img_buf), 60, 140, width=480, height=480)
            pdf.showPage()

        pdf.save()
        buffer.seek(0)

        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=analise-multi-risco.pdf"},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.get("/{analysis_id}/status")
async def get_analysis_status(analysis_id: str):
    """Get status of an analysis"""
    logger.info(f"Getting status for analysis: {analysis_id}")
    
    # TODO: Query database
    
    return {
        "analysis_id": analysis_id,
        "status": "processing",
        "progress": 50,
        "eta_seconds": 120
    }

@router.get("/{analysis_id}/results")
async def get_analysis_results(analysis_id: str):
    """Get results of a completed analysis"""
    logger.info(f"Getting results for analysis: {analysis_id}")
    
    # TODO: Fetch from database/cache
    
    return {
        "analysis_id": analysis_id,
        "hazard_type": "wind",
        "results": {},
        "statistics": {}
    }

@router.delete("/{analysis_id}")
async def delete_analysis(analysis_id: str):
    """Delete an analysis"""
    logger.info(f"Deleting analysis: {analysis_id}")
    
    # TODO: Delete from database
    
    return {
        "analysis_id": analysis_id,
        "status": "deleted"
    }
