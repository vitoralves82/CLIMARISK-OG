"""
Router de resultados CLIMARISK-OG
Serve JSONs consolidados por ativo (baseline + projecoes SSP)
Fallback: le de /app/data/ quando R2 nao esta disponivel
"""
import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/assets", tags=["assets"])

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).parent.parent / "data"
R2_AVAILABLE = False

try:
    import boto3
    r2_endpoint = os.getenv("R2_ENDPOINT_URL")
    r2_key = os.getenv("R2_ACCESS_KEY_ID")
    r2_secret = os.getenv("R2_SECRET_ACCESS_KEY")
    r2_bucket = os.getenv("R2_BUCKET_NAME", "climarisk-og")

    if r2_endpoint and r2_key and r2_secret:
        s3 = boto3.client(
            "s3",
            endpoint_url=r2_endpoint,
            aws_access_key_id=r2_key,
            aws_secret_access_key=r2_secret,
        )
        R2_AVAILABLE = True
except Exception:
    pass


def _load_from_r2(asset_id: str) -> Optional[dict]:
    """Tenta carregar JSON do R2."""
    if not R2_AVAILABLE:
        return None
    try:
        key = f"results/results_{asset_id}.json"
        obj = s3.get_object(Bucket=r2_bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        return None


def _load_from_local(asset_id: str) -> Optional[dict]:
    """Carrega JSON do diretorio local (seed data / fallback)."""
    # Tenta match exato e depois por prefixo
    for f in DATA_DIR.glob("*.json"):
        if asset_id.lower() in f.stem.lower():
            with open(f, encoding="utf-8") as fh:
                return json.load(fh)
    return None


def _load_asset(asset_id: str) -> dict:
    """Carrega dados do ativo -- R2 primeiro, local como fallback."""
    data = _load_from_r2(asset_id)
    if data is None:
        data = _load_from_local(asset_id)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    return data


def _list_local_assets() -> list:
    """Lista ativos disponiveis nos JSONs locais."""
    assets = []
    for f in DATA_DIR.glob("results_*.json"):
        try:
            with open(f, encoding="utf-8") as fh:
                d = json.load(fh)
            asset_info = d.get("asset", {})
            assets.append({
                "id": asset_info.get("id", f.stem),
                "name": asset_info.get("name", f.stem),
                "lat": asset_info.get("lat"),
                "lon": asset_info.get("lon"),
                "type": asset_info.get("type"),
                "region": asset_info.get("region"),
            })
        except Exception:
            continue
    return assets


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/")
async def list_assets():
    """Lista todos os ativos disponiveis."""
    assets = _list_local_assets()
    # TODO: merge com lista do R2 quando disponivel
    return {"count": len(assets), "assets": assets}


@router.get("/{asset_id}/results")
async def get_asset_results(asset_id: str):
    """Retorna JSON consolidado completo (baseline + projecoes)."""
    return _load_asset(asset_id)


@router.get("/{asset_id}/hazards")
async def list_hazards(asset_id: str):
    """Lista hazards disponiveis para o ativo."""
    data = _load_asset(asset_id)
    baseline = data.get("baseline", {}).get("hazards", {})
    hazards_summary = {}
    for haz_key, haz_data in baseline.items():
        hazards_summary[haz_key] = {
            "type": haz_data.get("type"),
            "type_name": haz_data.get("type_name"),
            "eai_usd": haz_data.get("results", {}).get("eai_usd"),
            "intensity_unit": haz_data.get("intensity_unit"),
        }
    return {"asset_id": asset_id, "hazards": hazards_summary}


@router.get("/{asset_id}/hazards/{hazard_type}")
async def get_hazard_detail(asset_id: str, hazard_type: str):
    """Retorna detalhes de um hazard especifico (baseline)."""
    data = _load_asset(asset_id)
    hazard_type_upper = hazard_type.upper()
    baseline_hazards = data.get("baseline", {}).get("hazards", {})
    if hazard_type_upper not in baseline_hazards:
        available = list(baseline_hazards.keys())
        raise HTTPException(
            status_code=404,
            detail=f"Hazard '{hazard_type}' not found. Available: {available}",
        )
    return {
        "asset_id": asset_id,
        "hazard": baseline_hazards[hazard_type_upper],
    }


@router.get("/{asset_id}/projections")
async def get_projections(
    asset_id: str,
    scenario: Optional[str] = Query(None, description="Filter by SSP scenario (e.g. ssp245, ssp585)"),
    horizon: Optional[int] = Query(None, description="Filter by horizon year (e.g. 2030, 2050, 2100)"),
):
    """Retorna projecoes SSP, com filtros opcionais."""
    data = _load_asset(asset_id)
    projections = data.get("projections", {})

    if scenario:
        scenario_lower = scenario.lower()
        if scenario_lower not in projections:
            available = list(projections.keys())
            raise HTTPException(
                status_code=404,
                detail=f"Scenario '{scenario}' not found. Available: {available}",
            )
        projections = {scenario_lower: projections[scenario_lower]}

    if horizon:
        filtered = {}
        for sc_key, sc_data in projections.items():
            horizons = sc_data.get("horizons", {})
            h_str = str(horizon)
            if h_str in horizons:
                filtered[sc_key] = {
                    **{k: v for k, v in sc_data.items() if k != "horizons"},
                    "horizons": {h_str: horizons[h_str]},
                }
        projections = filtered

    return {"asset_id": asset_id, "projections": projections}


@router.get("/{asset_id}/summary")
async def get_summary(asset_id: str):
    """Retorna resumo executivo para o dashboard."""
    data = _load_asset(asset_id)
    asset = data.get("asset", {})
    baseline = data.get("baseline", {})
    agg = baseline.get("aggregated_results", {})
    hazards = baseline.get("hazards", {})
    projections = data.get("projections", {})

    # Build projection timeline
    timeline = []
    timeline.append({
        "label": "Baseline",
        "year": 2024,
        "eai_total_usd": agg.get("eai_total_usd"),
    })
    for sc_key, sc_data in projections.items():
        for h_year, h_data in sc_data.get("horizons", {}).items():
            timeline.append({
                "label": f"{sc_key.upper()} {h_year}",
                "scenario": sc_key,
                "year": int(h_year),
                "eai_total_usd": h_data.get("aggregated", {}).get("eai_total_usd"),
            })

    return {
        "asset": asset,
        "baseline_eai_total_usd": agg.get("eai_total_usd"),
        "baseline_eai_ratio_pct": agg.get("eai_total_ratio_pct"),
        "hazard_contributions": agg.get("contribution_pct"),
        "hazards": {
            k: {
                "type_name": v.get("type_name"),
                "eai_usd": v.get("results", {}).get("eai_usd"),
            }
            for k, v in hazards.items()
        },
        "projection_timeline": sorted(timeline, key=lambda x: (x.get("scenario", ""), x["year"])),
    }


@router.post("/upload-seed")
async def upload_seed_to_r2():
    """Upload seed data para R2 (admin only - chamado uma vez)."""
    if not R2_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="R2 not configured. Check env vars: R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY"
        )
    uploaded = []
    errors = []
    for f in DATA_DIR.glob("results_*.json"):
        key = f"results/{f.name}"
        try:
            s3.upload_file(
                str(f),
                r2_bucket,
                key,
                ExtraArgs={"ContentType": "application/json"},
            )
            uploaded.append(key)
        except Exception as e:
            errors.append({"file": f.name, "error": str(e)})
    return {
        "uploaded": uploaded,
        "errors": errors,
        "r2_available": R2_AVAILABLE,
        "bucket": r2_bucket,
    }


@router.get("/r2-status")
async def r2_status():
    """Verifica status da conexao com R2."""
    if not R2_AVAILABLE:
        return {
            "r2_available": False,
            "reason": "Env vars missing or boto3 import failed",
        }
    try:
        response = s3.list_objects_v2(Bucket=r2_bucket, Prefix="results/", MaxKeys=10)
        objects = [
            {"key": obj["Key"], "size": obj["Size"]}
            for obj in response.get("Contents", [])
        ]
        return {
            "r2_available": True,
            "bucket": r2_bucket,
            "objects": objects,
            "count": len(objects),
        }
    except Exception as e:
        return {
            "r2_available": True,
            "bucket": r2_bucket,
            "error": str(e),
        }
