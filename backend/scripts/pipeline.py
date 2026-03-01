"""
CLIMARISK-OG Batch Pipeline
Versao script do NB05 para execucao no Railway.
Consolida calculo de impacto multi-hazard + projecoes SSP.
Gera JSON por ativo e faz upload ao R2.

Uso:
  python -m scripts.pipeline                    # Roda para todos os ativos
  python -m scripts.pipeline --asset REDUC      # Roda para ativo especifico
  python -m scripts.pipeline --dry-run          # Roda sem upload ao R2
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# CLIMADA imports (com fallback)
# ---------------------------------------------------------------------------
CLIMADA_AVAILABLE = False
try:
    from climada.hazard import Hazard, Centroids
    from climada.entity import Exposures, ImpactFuncSet, ImpactFunc
    from climada.engine import ImpactCalc
    CLIMADA_AVAILABLE = True
except ImportError:
    print("[WARN] CLIMADA nao disponivel. Usando dados sinteticos pre-calculados.")

# ---------------------------------------------------------------------------
# R2 upload (opcional)
# ---------------------------------------------------------------------------
R2_AVAILABLE = False
s3 = None
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

# ---------------------------------------------------------------------------
# Asset registry
# ---------------------------------------------------------------------------
ASSETS = [
    {
        "id": "REDUC",
        "name": "REDUC - Refinaria Duque de Caxias",
        "lat": -22.485,
        "lon": -43.27,
        "value_usd": 2_500_000_000,
        "type": "refinery",
        "region": "Duque de Caxias, RJ",
        "operator": "Petrobras",
    },
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GRID_SIZE_DEG = 0.05
N_GRID = 5
HEAT_THRESHOLD_C = 35
EVENTS_RF = [
    {"rp": 2, "depth_m": 0.3},
    {"rp": 5, "depth_m": 0.8},
    {"rp": 10, "depth_m": 1.5},
    {"rp": 25, "depth_m": 2.5},
    {"rp": 50, "depth_m": 3.2},
    {"rp": 100, "depth_m": 3.8},
]
EVENTS_HW = [
    {"rp": 2, "delta_c": 1.0},
    {"rp": 5, "delta_c": 2.5},
    {"rp": 10, "delta_c": 4.0},
    {"rp": 25, "delta_c": 5.8},
    {"rp": 50, "delta_c": 7.0},
    {"rp": 100, "delta_c": 8.2},
]
SSP_FACTORS = {
    "ssp245": {
        "name": "SSP2-4.5 (Moderate)",
        "desc": "Middle of the road - moderate challenges",
        "2030": {"RF": 1.08, "HW": 1.12},
        "2050": {"RF": 1.18, "HW": 1.30},
        "2100": {"RF": 1.35, "HW": 1.65},
    },
    "ssp585": {
        "name": "SSP5-8.5 (High Emissions)",
        "desc": "Fossil-fueled development - high challenges",
        "2030": {"RF": 1.10, "HW": 1.15},
        "2050": {"RF": 1.30, "HW": 1.55},
        "2100": {"RF": 1.60, "HW": 2.20},
    },
}


# ---------------------------------------------------------------------------
# CLIMADA builders (same logic as NB01-NB05)
# ---------------------------------------------------------------------------
def build_centroids(lat, lon):
    lats = np.array([lat + (i - N_GRID // 2) * GRID_SIZE_DEG for i in range(N_GRID)])
    lons = np.array([lon + (j - N_GRID // 2) * GRID_SIZE_DEG for j in range(N_GRID)])
    lat_grid, lon_grid = np.meshgrid(lats, lons)
    return Centroids.from_lat_lon(lat_grid.flatten(), lon_grid.flatten())


def build_exposure(asset, centroids):
    n_centr = centroids.size
    exp = Exposures(crs="EPSG:4326")
    import pandas as pd
    exp.gdf = pd.DataFrame({
        "latitude": centroids.lat,
        "longitude": centroids.lon,
        "value": np.full(n_centr, asset["value_usd"] / n_centr),
        "impf_RF": np.ones(n_centr, dtype=int) * 3,
        "impf_HW": np.ones(n_centr, dtype=int) * 1,
    })
    import geopandas as gpd
    from shapely.geometry import Point
    exp.gdf = gpd.GeoDataFrame(
        exp.gdf,
        geometry=[Point(lo, la) for lo, la in zip(exp.gdf.longitude, exp.gdf.latitude)],
        crs="EPSG:4326",
    )
    exp.check()
    return exp


def build_flood_hazard(centroids, events=None):
    events = events or EVENTS_RF
    n = centroids.size
    n_ev = len(events)
    intensity = np.zeros((n_ev, n))
    frequency = np.zeros(n_ev)
    for i, ev in enumerate(events):
        base = ev["depth_m"]
        intensity[i, :] = base * (1 + 0.1 * np.random.randn(n))
        intensity[i, :] = np.clip(intensity[i, :], 0, None)
        frequency[i] = 1.0 / ev["rp"]
    from scipy import sparse
    haz = Hazard(haz_type="RF")
    haz.centroids = centroids
    haz.event_id = np.arange(1, n_ev + 1)
    haz.event_name = [f"RF_RP{ev['rp']}" for ev in events]
    haz.date = np.array([736000 + i * 365 for i in range(n_ev)])
    haz.frequency = frequency
    haz.intensity = sparse.csr_matrix(intensity)
    haz.fraction = sparse.csr_matrix(np.ones_like(intensity))
    haz.units = "m"
    haz.check()
    return haz


def build_heat_hazard(centroids, events=None):
    events = events or EVENTS_HW
    n = centroids.size
    n_ev = len(events)
    intensity = np.zeros((n_ev, n))
    frequency = np.zeros(n_ev)
    for i, ev in enumerate(events):
        base = ev["delta_c"]
        intensity[i, :] = base * (1 + 0.05 * np.random.randn(n))
        intensity[i, :] = np.clip(intensity[i, :], 0, None)
        frequency[i] = 1.0 / ev["rp"]
    from scipy import sparse
    haz = Hazard(haz_type="HW")
    haz.centroids = centroids
    haz.event_id = np.arange(1, n_ev + 1)
    haz.event_name = [f"HW_RP{ev['rp']}" for ev in events]
    haz.date = np.array([736000 + i * 365 for i in range(n_ev)])
    haz.frequency = frequency
    haz.intensity = sparse.csr_matrix(intensity)
    haz.fraction = sparse.csr_matrix(np.ones_like(intensity))
    haz.units = "deg_C"
    haz.check()
    return haz


def build_impact_funcs():
    impf_set = ImpactFuncSet()
    # Flood: JRC via climada_petals
    try:
        from climada_petals.entity.impact_funcs.river_flood import flood_imp_func_set
        jrc_set = flood_imp_func_set()
        impf_flood = jrc_set.get_func(haz_type="RF")
        if isinstance(impf_flood, list):
            impf_flood = impf_flood[0]
        impf_set.append(impf_flood)
        flood_source = "climada_petals JRC"
    except Exception:
        # Fallback manual
        impf_flood = ImpactFunc(
            id=3, haz_type="RF",
            intensity=np.array([0, 0.5, 1, 1.5, 2, 3, 4, 5, 6]),
            mdd=np.array([0, 0.04, 0.08, 0.14, 0.22, 0.38, 0.52, 0.64, 0.75]),
            paa=np.ones(9),
            intensity_unit="m",
            name="Flood damage - South America (manual)",
        )
        impf_set.append(impf_flood)
        flood_source = "manual fallback"

    # Heat: custom industrial
    delta_t = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 10])
    mdd_heat = np.array([0, 0.01, 0.03, 0.06, 0.10, 0.16, 0.24, 0.33, 0.42, 0.58])
    impf_heat = ImpactFunc(
        id=1, haz_type="HW",
        intensity=delta_t,
        mdd=mdd_heat,
        paa=np.ones(len(delta_t)),
        intensity_unit="deg_C",
        name="Heat Wave - Industrial Facility (Refinery)",
    )
    impf_set.append(impf_heat)
    impf_set.check()
    return impf_set, impf_flood, impf_heat, flood_source


def compute_impact(exp, impf_set, hazard):
    imp = ImpactCalc(exp, impf_set, hazard).impact(save_mat=True)
    return imp


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def run_asset(asset, dry_run=False):
    """Run full pipeline for a single asset."""
    print(f"\n{'='*60}")
    print(f"  Processing: {asset['name']}")
    print(f"{'='*60}")

    if not CLIMADA_AVAILABLE:
        print("  CLIMADA indisponivel -- usando seed data local")
        seed_path = Path(__file__).parent.parent / "app" / "data" / f"results_{asset['id']}_duque_caxias.json"
        if seed_path.exists():
            with open(seed_path) as f:
                return json.load(f)
        print(f"  ERRO: seed data nao encontrado em {seed_path}")
        return None

    # Build components
    np.random.seed(42)  # Reproducibility
    centroids = build_centroids(asset["lat"], asset["lon"])
    exp = build_exposure(asset, centroids)
    haz_flood = build_flood_hazard(centroids)
    haz_heat = build_heat_hazard(centroids)
    impf_set, impf_flood, impf_heat, flood_source = build_impact_funcs()

    print(f"  Centroids: {centroids.size}")
    print(f"  Exposure total: USD {asset['value_usd']:,.0f}")
    print(f"  Flood source: {flood_source}")

    # Baseline impacts
    imp_flood = compute_impact(exp, impf_set, haz_flood)
    imp_heat = compute_impact(exp, impf_set, haz_heat)

    eai_flood = float(imp_flood.aai_agg)
    eai_heat = float(imp_heat.aai_agg)
    eai_total = eai_flood + eai_heat

    print(f"  EAI Flood: USD {eai_flood:,.0f}")
    print(f"  EAI Heat:  USD {eai_heat:,.0f}")
    print(f"  EAI Total: USD {eai_total:,.0f}")

    # Build result dict
    result = {
        "metadata": {
            "pipeline": "climarisk-og-batch-v1",
            "version": "1.0",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "climada_version": "6.1.0",
            "methodology": "CLIMADA multi-hazard H x E x V probabilistic impact",
            "n_hazards": 2,
            "scenarios": ["baseline", "ssp245", "ssp585"],
            "horizons": [2030, 2050, 2100],
        },
        "asset": asset,
        "baseline": {
            "hazards": {
                "RF": {
                    "type": "RF",
                    "type_name": "River Flood",
                    "n_events": len(EVENTS_RF),
                    "return_periods": [e["rp"] for e in EVENTS_RF],
                    "intensity_unit": "m",
                    "max_intensity": float(haz_flood.intensity.max()),
                    "impact_function": {
                        "name": impf_flood.name,
                        "id": int(impf_flood.id),
                        "source": "Huizinga et al. (2017), doi: 10.2760/16510",
                        "loaded_via": flood_source,
                        "type": "structural_damage",
                    },
                    "results": {
                        "eai_usd": eai_flood,
                        "eai_ratio_pct": float(eai_flood / asset["value_usd"] * 100),
                        "impact_by_return_period": {
                            str(EVENTS_RF[i]["rp"]): float(imp_flood.at_event[i])
                            for i in range(len(EVENTS_RF))
                        },
                    },
                },
                "HW": {
                    "type": "HW",
                    "type_name": "Heat Wave",
                    "n_events": len(EVENTS_HW),
                    "return_periods": [e["rp"] for e in EVENTS_HW],
                    "intensity_unit": "deg_C above threshold",
                    "threshold_c": HEAT_THRESHOLD_C,
                    "max_intensity": float(haz_heat.intensity.max()),
                    "impact_function": {
                        "name": "Heat Wave - Industrial Facility (Refinery)",
                        "source": "Custom - ECA/McKinsey (2009), Kjellstrom et al. (2016), ILO (2019)",
                        "type": "operational_loss",
                    },
                    "results": {
                        "eai_usd": eai_heat,
                        "eai_ratio_pct": float(eai_heat / asset["value_usd"] * 100),
                        "impact_by_return_period": {
                            str(EVENTS_HW[i]["rp"]): float(imp_heat.at_event[i])
                            for i in range(len(EVENTS_HW))
                        },
                    },
                },
            },
            "aggregated_results": {
                "eai_total_usd": eai_total,
                "eai_total_ratio_pct": float(eai_total / asset["value_usd"] * 100),
                "contribution_pct": {
                    "RF": round(eai_flood / eai_total * 100, 1) if eai_total > 0 else 0,
                    "HW": round(eai_heat / eai_total * 100, 1) if eai_total > 0 else 0,
                },
                "aggregation_method": "simple_sum",
                "note": "Independence between hazards assumed. No correlation modeled.",
            },
        },
        "projections": {},
        "limitations": [
            "Synthetic hazard data for both risks (calibrated, not observed)",
            "Exposure value estimated from public sources",
            "Heat wave impact function is custom (not calibrated with real loss data)",
            "Flood impact function is generic (JRC South America residential)",
            "Independence between hazards assumed (no correlation)",
            "Single asset analysis",
            "Scale factors from IPCC AR6 regional averages (not downscaled)",
        ],
    }

    # SSP projections
    for ssp_key, ssp_config in SSP_FACTORS.items():
        ssp_result = {
            "scenario_name": ssp_config["name"],
            "description": ssp_config["desc"],
            "horizons": {},
        }
        for horizon in ["2030", "2050", "2100"]:
            factors = ssp_config[horizon]
            rf_eai = eai_flood * factors["RF"]
            hw_eai = eai_heat * factors["HW"]
            total_eai = rf_eai + hw_eai
            ssp_result["horizons"][horizon] = {
                "scale_factors": factors,
                "hazards": {
                    "RF": {
                        "eai_usd": round(rf_eai, 0),
                        "eai_ratio_pct": round(rf_eai / asset["value_usd"] * 100, 2),
                        "delta_pct": round((factors["RF"] - 1) * 100, 1),
                    },
                    "HW": {
                        "eai_usd": round(hw_eai, 0),
                        "eai_ratio_pct": round(hw_eai / asset["value_usd"] * 100, 2),
                        "delta_pct": round((factors["HW"] - 1) * 100, 1),
                    },
                },
                "aggregated": {
                    "eai_total_usd": round(total_eai, 0),
                    "eai_total_ratio_pct": round(total_eai / asset["value_usd"] * 100, 2),
                },
            }
        result["projections"][ssp_key] = ssp_result

    # Save locally
    output_dir = Path(__file__).parent.parent / "app" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"results_{asset['id']}_duque_caxias.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {output_file}")

    # Upload to R2
    if R2_AVAILABLE and not dry_run:
        key = f"results/{output_file.name}"
        try:
            s3.upload_file(
                str(output_file),
                r2_bucket,
                key,
                ExtraArgs={"ContentType": "application/json"},
            )
            print(f"  Uploaded to R2: s3://{r2_bucket}/{key}")
        except Exception as e:
            print(f"  R2 upload failed: {e}")
    elif dry_run:
        print("  [DRY RUN] Skipping R2 upload")
    else:
        print("  [WARN] R2 not available, skipping upload")

    return result


def main():
    parser = argparse.ArgumentParser(description="CLIMARISK-OG Batch Pipeline")
    parser.add_argument("--asset", type=str, help="Run for specific asset ID")
    parser.add_argument("--dry-run", action="store_true", help="Skip R2 upload")
    args = parser.parse_args()

    print("=" * 60)
    print("  CLIMARISK-OG Batch Pipeline")
    print(f"  Time: {datetime.utcnow().isoformat()}Z")
    print(f"  CLIMADA: {'available' if CLIMADA_AVAILABLE else 'NOT available (using seed)'}")
    print(f"  R2: {'available' if R2_AVAILABLE else 'NOT available'}")
    print("=" * 60)

    assets_to_run = ASSETS
    if args.asset:
        assets_to_run = [a for a in ASSETS if a["id"] == args.asset]
        if not assets_to_run:
            print(f"Asset '{args.asset}' not found. Available: {[a['id'] for a in ASSETS]}")
            sys.exit(1)

    results = {}
    for asset in assets_to_run:
        result = run_asset(asset, dry_run=args.dry_run)
        if result:
            results[asset["id"]] = result

    print(f"\nPipeline complete. Processed {len(results)} assets.")
    return results


if __name__ == "__main__":
    main()
