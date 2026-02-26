"""Service for reading climate data from Zarr files."""

import xarray as xr
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np
from datetime import datetime
import geopandas as gpd
from shapely.geometry import Point
from shapely.ops import unary_union
import fiona

try:
    from app.services.climada_impact import climada_service, HAZ_WIND, HAZ_WAVE
    _CLIMADA_SERVICE_AVAILABLE = True
except ImportError:
    _CLIMADA_SERVICE_AVAILABLE = False
    HAZ_WIND = "WS"
    HAZ_WAVE = "OW"


class ZarrDataReader:
    """Read and process climate data from Zarr stores."""
    
    def __init__(self, zarr_path: str = "D:/OceanPact/climatologia.zarr"):
        """Initialize reader with Zarr path."""
        self.zarr_path = Path(zarr_path)
        self._ds = None
    
    @property
    def ds(self) -> xr.Dataset:
        """Lazy load dataset."""
        if self._ds is None:
            self._ds = xr.open_zarr(str(self.zarr_path))
        return self._ds
    
    def get_available_variables(self) -> List[str]:
        """Get list of available variables in dataset."""
        return list(self.ds.data_vars)
    
    def get_time_range(self) -> Tuple[datetime, datetime]:
        """Get min and max time in dataset."""
        times = self.ds.time.values
        return (
            np.datetime64(times.min()).astype(datetime),
            np.datetime64(times.max()).astype(datetime)
        )
    
    def get_spatial_bounds(self) -> Dict[str, float]:
        """Get spatial bounding box."""
        return {
            "north": float(self.ds.lat.max().values),
            "south": float(self.ds.lat.min().values),
            "west": float(self.ds.lon.min().values),
            "east": float(self.ds.lon.max().values),
        }
    
    def query_data(
        self,
        variable: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lon_min: Optional[float] = None,
        lon_max: Optional[float] = None,
    ) -> xr.DataArray:
        """Query data with spatial and temporal filters."""
        
        # Start with full dataset variable
        data = self.ds[variable]
        
        # Apply time slice
        if start_time or end_time:
            data = data.sel(time=slice(start_time, end_time))
        
        # Apply spatial slice
        if lat_min is not None or lat_max is not None:
            data = data.sel(lat=slice(lat_max, lat_min))  # Note: lat is descending
        
        if lon_min is not None or lon_max is not None:
            data = data.sel(lon=slice(lon_min, lon_max))
        
        return data
    
    def get_timeseries_at_point(
        self,
        variable: str,
        lat: float,
        lon: float,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict:
        """Get time series for a specific point."""
        
        # Select nearest point
        data = self.ds[variable].sel(
            lat=lat,
            lon=lon,
            method="nearest"
        )
        
        # Apply time slice
        if start_time or end_time:
            data = data.sel(time=slice(start_time, end_time))
        
        # Load data and convert to dict
        data_loaded = data.load()
        
        return {
            "time": data_loaded.time.values.astype(str).tolist(),
            "values": data_loaded.values.tolist(),
            "lat": float(data_loaded.lat.values),
            "lon": float(data_loaded.lon.values),
        }

    def get_point_series(
        self,
        variable: str,
        lat: float,
        lon: float,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> xr.DataArray:
        """Get a point time series as DataArray."""
        data = self.ds[variable].sel(lat=lat, lon=lon, method="nearest")
        if start_time or end_time:
            data = data.sel(time=slice(start_time, end_time))
        return data.load()

    def get_wind_speed_series(
        self,
        lat: float,
        lon: float,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> xr.DataArray:
        """Get wind speed (knots) time series for a point."""
        u10 = self.ds["u10"].sel(lat=lat, lon=lon, method="nearest")
        v10 = self.ds["v10"].sel(lat=lat, lon=lon, method="nearest")
        if start_time or end_time:
            u10 = u10.sel(time=slice(start_time, end_time))
            v10 = v10.sel(time=slice(start_time, end_time))
        speed_ms = np.sqrt(u10**2 + v10**2)
        speed_knots = (speed_ms * 1.94384).load()
        return speed_knots

    def get_wind_direction_series(
        self,
        lat: float,
        lon: float,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> xr.DataArray:
        """Get wind direction (degrees, meteorological) time series for a point."""
        u10 = self.ds["u10"].sel(lat=lat, lon=lon, method="nearest")
        v10 = self.ds["v10"].sel(lat=lat, lon=lon, method="nearest")
        if start_time or end_time:
            u10 = u10.sel(time=slice(start_time, end_time))
            v10 = v10.sel(time=slice(start_time, end_time))
        direction_deg = (np.degrees(np.arctan2(u10, v10)) + 180.0) % 360.0
        return direction_deg.load()

    def _exceedance_probs(self, n: int, method: str = "weibull") -> np.ndarray:
        """Empirical exceedance plotting position."""
        if n <= 0:
            return np.array([], dtype=float)

        rank = np.arange(1, n + 1, dtype=float)
        method = (method or "weibull").lower()

        if method == "hazen":
            probs = (rank - 0.5) / n
        elif method == "gringorten":
            probs = (rank - 0.44) / (n + 0.12)
        else:
            probs = rank / (n + 1.0)

        return np.clip(probs, 0.0, 1.0)

    def _workspace_root(self) -> Path:
        return Path(__file__).resolve().parents[3]

    def _find_nearest_shapefile(self, lat: float, lon: float) -> Optional[Path]:
        data_root = self._workspace_root() / "frontend" / "public" / "data"
        if not data_root.exists():
            return None

        point = Point(lon, lat)
        best_path: Optional[Path] = None
        best_dist = float("inf")

        for shp_path in data_root.rglob("*.shp"):
            try:
                with fiona.open(shp_path) as src:
                    bounds = src.bounds
                center_lon = (float(bounds[0]) + float(bounds[2])) / 2.0
                center_lat = (float(bounds[1]) + float(bounds[3])) / 2.0
                dist = point.distance(Point(center_lon, center_lat))
                if dist < best_dist:
                    best_dist = dist
                    best_path = shp_path
            except Exception:
                continue

        return best_path

    def _polygon_exterior_coords(self, geom) -> Tuple[List[float], List[float]]:
        if geom is None or geom.is_empty:
            return [], []

        polygon = None
        if geom.geom_type == "Polygon":
            polygon = geom
        elif geom.geom_type == "MultiPolygon":
            polygon = max(list(geom.geoms), key=lambda item: item.area, default=None)

        if polygon is None or polygon.exterior is None:
            return [], []

        coords = list(polygon.exterior.coords)
        lon_vals = [float(c[0]) for c in coords]
        lat_vals = [float(c[1]) for c in coords]
        return lon_vals, lat_vals

    def _sample_points_inside_geometry(self, geometry, n_points: int = 220) -> Tuple[np.ndarray, np.ndarray]:
        if geometry is None or geometry.is_empty:
            return np.array([], dtype=float), np.array([], dtype=float)

        min_lon, min_lat, max_lon, max_lat = geometry.bounds
        if not np.isfinite([min_lon, min_lat, max_lon, max_lat]).all():
            return np.array([], dtype=float), np.array([], dtype=float)

        rng = np.random.default_rng(42)
        sampled_lon: List[float] = []
        sampled_lat: List[float] = []

        max_attempts = n_points * 60
        attempts = 0
        while len(sampled_lon) < n_points and attempts < max_attempts:
            attempts += 1
            lon_candidate = float(rng.uniform(min_lon, max_lon))
            lat_candidate = float(rng.uniform(min_lat, max_lat))
            candidate = Point(lon_candidate, lat_candidate)
            if geometry.covers(candidate):
                sampled_lon.append(lon_candidate)
                sampled_lat.append(lat_candidate)

        return np.array(sampled_lon, dtype=float), np.array(sampled_lat, dtype=float)

    def _build_exposure_reference(self, lat: float, lon: float) -> Optional[Dict]:
        shp_path = self._find_nearest_shapefile(lat, lon)
        if shp_path is None:
            return None

        try:
            gdf = gpd.read_file(shp_path)
        except Exception:
            return None

        if gdf.empty or "geometry" not in gdf:
            return None

        gdf = gdf[gdf.geometry.notnull()].copy()
        gdf = gdf[~gdf.geometry.is_empty].copy()
        if gdf.empty:
            return None

        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326", allow_override=True)
        elif str(gdf.crs).upper() != "EPSG:4326":
            gdf = gdf.to_crs("EPSG:4326")

        if len(gdf) > 800:
            gdf = gdf.sample(n=800, random_state=42)

        point = Point(lon, lat)
        union_geom = unary_union(gdf.geometry.values)
        point_series = gdf.geometry.representative_point()
        lon_points = point_series.x.to_numpy(dtype=float)
        lat_points = point_series.y.to_numpy(dtype=float)

        gdf_metric = gdf.to_crs("EPSG:3857")
        point_metric = gpd.GeoSeries([point], crs="EPSG:4326").to_crs("EPSG:3857").iloc[0]

        areas = gdf_metric.geometry.area.to_numpy(dtype=float)
        if np.all(~np.isfinite(areas)):
            areas = np.ones_like(lon_points, dtype=float)
        areas = np.nan_to_num(areas, nan=0.0, posinf=0.0, neginf=0.0)
        if np.max(areas) <= 0:
            areas = np.ones_like(areas, dtype=float)
        values_array = areas / np.max(areas)

        distances = gdf_metric.geometry.distance(point_metric)
        nearest_idx = int(distances.idxmin())
        nearest_geom = gdf.loc[nearest_idx, "geometry"]
        boundary_lon, boundary_lat = self._polygon_exterior_coords(union_geom)

        inside_count = 0
        if union_geom is not None and not union_geom.is_empty:
            inside_count = int(np.sum([union_geom.contains(Point(x, y)) for x, y in zip(lon_points, lat_points)]))

        inside_ratio = (inside_count / max(lon_points.size, 1)) if lon_points.size else 0.0
        need_interior_sampling = lon_points.size < 20 or inside_ratio < 0.6

        if need_interior_sampling:
            sample_geom = union_geom
            if sample_geom is None or sample_geom.is_empty:
                sample_geom = nearest_geom
            if sample_geom is not None and not sample_geom.is_empty and sample_geom.geom_type not in {"Polygon", "MultiPolygon"}:
                sample_geom = sample_geom.convex_hull

            sampled_lon, sampled_lat = self._sample_points_inside_geometry(sample_geom, n_points=220)
            if sampled_lon.size > 0:
                lon_points = sampled_lon
                lat_points = sampled_lat
                values_array = np.ones_like(sampled_lon, dtype=float)

        values = values_array.tolist()

        min_lon, min_lat, max_lon, max_lat = gdf.total_bounds
        hist, x_edges, y_edges = np.histogram2d(
            lon_points,
            lat_points,
            bins=[12, 12],
            range=[[float(min_lon), float(max_lon)], [float(min_lat), float(max_lat)]],
        )

        x_centers = ((x_edges[:-1] + x_edges[1:]) / 2.0).tolist()
        y_centers = ((y_edges[:-1] + y_edges[1:]) / 2.0).tolist()

        nearest_geom_metric = gdf_metric.loc[nearest_idx, "geometry"] if nearest_geom is not None else None
        distance_km = float(point_metric.distance(nearest_geom_metric) / 1000.0) if nearest_geom_metric is not None else 0.0

        return {
            "source_name": shp_path.stem,
            "source_path": str(shp_path.relative_to(self._workspace_root())).replace("\\", "/"),
            "nearest_distance_km": distance_km,
            "point": {"lat": float(lat), "lon": float(lon)},
            "bbox": {
                "min_lon": float(min_lon),
                "max_lon": float(max_lon),
                "min_lat": float(min_lat),
                "max_lat": float(max_lat),
            },
            "boundary": {
                "lon": boundary_lon,
                "lat": boundary_lat,
            },
            "exposure_points": {
                "lon": lon_points.tolist(),
                "lat": lat_points.tolist(),
                "value": [float(v) for v in values],
            },
            "raster": {
                "x_centers": [float(v) for v in x_centers],
                "y_centers": [float(v) for v in y_centers],
                "z": hist.T.astype(float).tolist(),
            },
        }

    def get_multi_risk_point(
        self,
        lat: float,
        lon: float,
        start_time: Optional[str],
        end_time: Optional[str],
        hazards: List[str],
        thresholds: Dict[str, Dict[str, float]],
        stop_cost_per_hour: Optional[float] = None,
        combine_mode: str = "worst",
        weights: Optional[Dict[str, float]] = None,
        multiplier: float = 1.5,
        asset_value: Optional[float] = None,
        attention_loss_factor: float = 0.35,
        stop_loss_factor: float = 1.0,
        exceedance_method: str = "weibull",
        risk_load_method: str = "none",
        risk_quantile: float = 0.95,
        expense_ratio: float = 0.15,
        include_series: bool = False,
        asset_type: str = "generic_offshore",
    ) -> Dict:
        """Calculate multi-risk metrics for a single point."""

        series_map: Dict[str, xr.DataArray] = {}
        if "wind" in hazards:
            series_map["wind"] = self.get_wind_speed_series(
                lat, lon, start_time, end_time
            )
        if "wave" in hazards:
            series_map["wave"] = self.get_point_series(
                "hs", lat, lon, start_time, end_time
            )

        if not series_map:
            raise ValueError("No supported hazards provided.")

        aligned = xr.align(*series_map.values(), join="inner")
        aligned_map = dict(zip(series_map.keys(), aligned))
        times = aligned[0].time.values.astype(str).tolist()

        hazards_out: Dict[str, Dict[str, float]] = {}
        distributions_out: Dict[str, Dict[str, List[float]]] = {}
        status_list = []
        status_map: Dict[str, np.ndarray] = {}
        series_out = {}
        metrics_out: Dict[str, Dict[str, float]] = {}
        wind_rose = None
        hazard_pricing_models: Dict[str, Dict] = {}

        for hazard, data in aligned_map.items():
            limits = thresholds.get(hazard, {})
            operational = float(limits.get("operational_max", 0))
            attention = float(limits.get("attention_max", operational))

            values = data.values
            status = np.zeros_like(values, dtype=np.uint8)
            status = np.where(values >= attention, 2, status)
            status = np.where((values >= operational) & (values < attention), 1, status)

            hazards_out[hazard] = {
                "mean": float(np.nanmean(values)),
                "max": float(np.nanmax(values)),
                "operational_hours": int(np.sum(status == 0)),
                "attention_hours": int(np.sum(status == 1)),
                "stop_hours": int(np.sum(status == 2)),
                "operational_max": float(operational),
                "attention_max": float(attention),
            }

            status_list.append(status)
            status_map[hazard] = status
            if include_series:
                series_out[hazard] = values.tolist()

            clean = values[np.isfinite(values)]
            if clean.size:
                counts, bin_edges = np.histogram(clean, bins=20)
                bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
                sorted_vals = np.sort(clean)[::-1]
                exceedance = self._exceedance_probs(sorted_vals.size, exceedance_method)
                distributions_out[hazard] = {
                    "hist_bins": bin_centers.tolist(),
                    "hist_counts": counts.tolist(),
                    "exceedance_values": sorted_vals.tolist(),
                    "exceedance_probs": exceedance.tolist(),
                }
            else:
                distributions_out[hazard] = {
                    "hist_bins": [],
                    "hist_counts": [],
                    "exceedance_values": [],
                    "exceedance_probs": [],
                }

            if clean.size:
                metrics_out[hazard] = {
                    "mean": float(np.nanmean(clean)),
                    "max": float(np.nanmax(clean)),
                    "p50": float(np.nanpercentile(clean, 50)),
                    "p90": float(np.nanpercentile(clean, 90)),
                    "p95": float(np.nanpercentile(clean, 95)),
                    "p99": float(np.nanpercentile(clean, 99)),
                }
            else:
                metrics_out[hazard] = {
                    "mean": 0.0,
                    "max": 0.0,
                    "p50": 0.0,
                    "p90": 0.0,
                    "p95": 0.0,
                    "p99": 0.0,
                }

            if asset_value is not None and float(asset_value) > 0 and status.size > 0:
                asset_value_f = float(asset_value)
                quantile = float(np.clip(risk_quantile, 0.5, 0.999))
                attention_factor = float(np.clip(attention_loss_factor, 0.0, 1.0))
                stop_factor = float(max(stop_loss_factor, attention_factor))

                _use_climada = (
                    _CLIMADA_SERVICE_AVAILABLE
                    and asset_type
                    and asset_type not in ("generic_offshore", "")
                )
                if _use_climada:
                    _haz_code = HAZ_WIND if hazard == "wind" else HAZ_WAVE
                    hazard_damage_ratio = climada_service.calc_damage_ratio(
                        _haz_code, values, asset_type
                    )
                else:
                    # Modelo discreto legado (backward compatible com generic_offshore)
                    hazard_damage_ratio = np.where(
                        status == 2,
                        stop_factor,
                        np.where(status == 1, attention_factor, 0.0),
                    )
                hazard_loss_per_step = asset_value_f * hazard_damage_ratio

                hazard_total_hours = max(float(status.size), 1.0)
                hazard_annualization = 8760.0 / hazard_total_hours

                hazard_aal = float(np.mean(hazard_loss_per_step)) * hazard_annualization
                hazard_pml = float(np.nanmax(hazard_loss_per_step)) * hazard_annualization
                hazard_var_q = float(np.nanquantile(hazard_loss_per_step, quantile)) * hazard_annualization

                hazard_tail = hazard_loss_per_step[hazard_loss_per_step >= np.nanquantile(hazard_loss_per_step, quantile)]
                hazard_tvar_q = (
                    float(np.nanmean(hazard_tail)) if hazard_tail.size else float(np.nanquantile(hazard_loss_per_step, quantile))
                ) * hazard_annualization

                method = (risk_load_method or "none").lower()
                if method == "var":
                    hazard_risk_load = max(hazard_var_q - hazard_aal, 0.0)
                elif method == "tvar":
                    hazard_risk_load = max(hazard_tvar_q - hazard_aal, 0.0)
                elif method == "stdev":
                    hazard_risk_load = float(np.nanstd(hazard_loss_per_step)) * np.sqrt(hazard_annualization)
                else:
                    hazard_risk_load = 0.0

                hazard_pure_premium = hazard_aal
                hazard_technical_premium = hazard_pure_premium * (1.0 + float(max(expense_ratio, 0.0))) + hazard_risk_load

                sensitivity_quantiles = [0.90, 0.95, 0.99]
                quantile_sensitivity = []
                for q in sensitivity_quantiles:
                    var_q = float(np.nanquantile(hazard_loss_per_step, q)) * hazard_annualization
                    tail_q = hazard_loss_per_step[hazard_loss_per_step >= np.nanquantile(hazard_loss_per_step, q)]
                    tvar_q = (
                        float(np.nanmean(tail_q)) if tail_q.size else float(np.nanquantile(hazard_loss_per_step, q))
                    ) * hazard_annualization

                    if method == "var":
                        risk_load_q = max(var_q - hazard_aal, 0.0)
                    elif method == "tvar":
                        risk_load_q = max(tvar_q - hazard_aal, 0.0)
                    elif method == "stdev":
                        risk_load_q = float(np.nanstd(hazard_loss_per_step)) * np.sqrt(hazard_annualization)
                    else:
                        risk_load_q = 0.0

                    tech_q = hazard_pure_premium * (1.0 + float(max(expense_ratio, 0.0))) + risk_load_q
                    quantile_sensitivity.append(
                        {
                            "quantile": float(q),
                            "var": float(var_q),
                            "tvar": float(tvar_q),
                            "technical_premium": float(tech_q),
                        }
                    )

                _haz_code_for_meta = HAZ_WIND if hazard == "wind" else HAZ_WAVE
                _impact_func_meta = (
                    climada_service.describe_curve(_haz_code_for_meta, asset_type)
                    if _CLIMADA_SERVICE_AVAILABLE
                    else {
                        "asset_type": "generic_offshore",
                        "mode": "legacy",
                        "attention_loss_factor": attention_factor,
                        "stop_loss_factor": stop_factor,
                    }
                )
                hazard_pricing_models[hazard] = {
                    "asset_value": asset_value_f,
                    "attention_loss_factor": attention_factor,
                    "stop_loss_factor": stop_factor,
                    "annualization_factor": hazard_annualization,
                    "aal": float(hazard_aal),
                    "pml": float(hazard_pml),
                    "var": float(hazard_var_q),
                    "tvar": float(hazard_tvar_q),
                    "risk_load_method": method,
                    "risk_load": float(hazard_risk_load),
                    "expense_ratio": float(max(expense_ratio, 0.0)),
                    "pure_premium": float(hazard_pure_premium),
                    "technical_premium": float(hazard_technical_premium),
                    "exceedance_method": exceedance_method,
                    "risk_quantile": quantile,
                    "quantile_sensitivity": quantile_sensitivity,
                    "impact_function": _impact_func_meta,
                }

        if "wind" in hazards:
            direction = self.get_wind_direction_series(lat, lon, start_time, end_time)
            direction_values = direction.values
            bins = np.linspace(0, 360, 17)
            counts, _ = np.histogram(direction_values, bins=bins)

            wind_values = aligned_map["wind"].values
            wind_limits = thresholds.get("wind", {})
            wind_operational = float(wind_limits.get("operational_max", 15.0))
            wind_attention = float(wind_limits.get("attention_max", max(20.0, wind_operational)))

            finite_mask = np.isfinite(direction_values) & np.isfinite(wind_values)
            direction_clean = direction_values[finite_mask]
            wind_clean = wind_values[finite_mask]

            operational_mask = wind_clean < wind_operational
            attention_mask = (wind_clean >= wind_operational) & (wind_clean < wind_attention)
            stop_mask = wind_clean >= wind_attention

            operational_counts, _ = np.histogram(direction_clean[operational_mask], bins=bins)
            attention_counts, _ = np.histogram(direction_clean[attention_mask], bins=bins)
            stop_counts, _ = np.histogram(direction_clean[stop_mask], bins=bins)

            direction_labels = [
                "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"
            ]
            spoke_max_values = []
            for idx in range(len(direction_labels)):
                start = bins[idx]
                end = bins[idx + 1]
                if idx == len(direction_labels) - 1:
                    sector_mask = (direction_clean >= start) & (direction_clean <= end)
                else:
                    sector_mask = (direction_clean >= start) & (direction_clean < end)

                if np.any(sector_mask):
                    spoke_max_values.append(float(np.nanmax(wind_clean[sector_mask])))
                else:
                    spoke_max_values.append(0.0)

            wind_rose = {
                "bins": [f"{int(bins[i])}-{int(bins[i+1])}" for i in range(len(bins) - 1)],
                "direction_labels": direction_labels,
                "spoke_max_values": spoke_max_values,
                "global_max_speed": float(np.nanmax(wind_clean)) if wind_clean.size else 0.0,
                "counts": counts.astype(int).tolist(),
                "operational_counts": operational_counts.astype(int).tolist(),
                "attention_counts": attention_counts.astype(int).tolist(),
                "stop_counts": stop_counts.astype(int).tolist(),
                "limits": {
                    "operational_max": wind_operational,
                    "attention_max": wind_attention,
                },
            }
            if include_series:
                series_out["wind_direction_deg"] = direction_values.tolist()

        if combine_mode == "weighted":
            weight_map = weights or {}
            weights_used = np.array([
                float(weight_map.get(hazard, 1.0)) for hazard in aligned_map.keys()
            ])
            weights_used = np.where(weights_used <= 0, 1.0, weights_used)
            stacked = np.vstack([status_map[hazard] for hazard in aligned_map.keys()])
            score = np.average(stacked, axis=0, weights=weights_used)
            combined_status = np.zeros_like(score, dtype=np.uint8)
            combined_status = np.where(score >= 1.5, 2, combined_status)
            combined_status = np.where((score >= 0.5) & (score < 1.5), 1, combined_status)
        else:
            combined_status = np.maximum.reduce(status_list)
            score = combined_status.astype(float)
        combined = {
            "operational_hours": int(np.sum(combined_status == 0)),
            "attention_hours": int(np.sum(combined_status == 1)),
            "stop_hours": int(np.sum(combined_status == 2)),
            "total_hours": int(combined_status.size),
        }

        effective_stop_hours = float(combined["stop_hours"])
        if combine_mode == "multiplier":
            multiplier = max(1.0, float(multiplier))
            attention_mask = np.logical_and.reduce([status_map[hazard] >= 1 for hazard in status_map])
            effective_stop_hours = float(combined["stop_hours"]) + float(np.sum(attention_mask)) * (multiplier - 1)

        pricing = None
        if stop_cost_per_hour is not None:
            stop_cost = float(stop_cost_per_hour) * effective_stop_hours
            pricing = {
                "stop_cost": stop_cost,
                "total_cost": stop_cost,
            }

        score_clean = score[np.isfinite(score)]
        if score_clean.size:
            sorted_score = np.sort(score_clean)[::-1]
            exceedance = self._exceedance_probs(sorted_score.size, exceedance_method)
            combined_exceedance = {
                "values": sorted_score.tolist(),
                "probs": exceedance.tolist(),
            }
            metrics_out["combined"] = {
                "mean": float(np.nanmean(score_clean)),
                "max": float(np.nanmax(score_clean)),
                "p50": float(np.nanpercentile(score_clean, 50)),
                "p90": float(np.nanpercentile(score_clean, 90)),
                "p95": float(np.nanpercentile(score_clean, 95)),
                "p99": float(np.nanpercentile(score_clean, 99)),
            }
        else:
            combined_exceedance = {"values": [], "probs": []}
            metrics_out["combined"] = {
                "mean": 0.0,
                "max": 0.0,
                "p50": 0.0,
                "p90": 0.0,
                "p95": 0.0,
                "p99": 0.0,
            }

        pricing_models = None
        if asset_value is not None and float(asset_value) > 0:
            asset_value_f = float(asset_value)
            quantile = float(np.clip(risk_quantile, 0.5, 0.999))
            attention_factor = float(np.clip(attention_loss_factor, 0.0, 1.0))
            stop_factor = float(max(stop_loss_factor, attention_factor))

            loss_ratio = np.where(
                combined_status == 2,
                stop_factor,
                np.where(combined_status == 1, attention_factor, 0.0),
            )
            loss_per_step = asset_value_f * loss_ratio

            total_hours = max(float(combined["total_hours"]), 1.0)
            annualization = 8760.0 / total_hours

            period_expected_loss = float(np.mean(loss_per_step))
            aal = period_expected_loss * annualization
            pml = float(np.nanmax(loss_per_step)) * annualization
            var_q = float(np.nanquantile(loss_per_step, quantile)) * annualization

            tail = loss_per_step[loss_per_step >= np.nanquantile(loss_per_step, quantile)]
            tvar_q = (float(np.nanmean(tail)) if tail.size else float(np.nanquantile(loss_per_step, quantile))) * annualization

            method = (risk_load_method or "none").lower()
            if method == "var":
                risk_load = max(var_q - aal, 0.0)
            elif method == "tvar":
                risk_load = max(tvar_q - aal, 0.0)
            elif method == "stdev":
                risk_load = float(np.nanstd(loss_per_step)) * np.sqrt(annualization)
            else:
                risk_load = 0.0

            pure_premium = aal
            technical_premium = pure_premium * (1.0 + float(max(expense_ratio, 0.0))) + risk_load

            pricing_models = {
                "asset_value": asset_value_f,
                "attention_loss_factor": attention_factor,
                "stop_loss_factor": stop_factor,
                "annualization_factor": annualization,
                "aal": float(aal),
                "pml": float(pml),
                "var": float(var_q),
                "tvar": float(tvar_q),
                "risk_load_method": method,
                "risk_load": float(risk_load),
                "expense_ratio": float(max(expense_ratio, 0.0)),
                "pure_premium": float(pure_premium),
                "technical_premium": float(technical_premium),
                "exceedance_method": exceedance_method,
                "risk_quantile": quantile,
            }

        # Build impact_functions_used summary (one entry per hazard)
        impact_functions_used: Dict[str, Dict] = {}
        if _CLIMADA_SERVICE_AVAILABLE:
            for hazard in aligned_map:
                _haz_code = HAZ_WIND if hazard == "wind" else HAZ_WAVE
                impact_functions_used[hazard] = climada_service.describe_curve(_haz_code, asset_type)
                if asset_type and asset_type not in ("generic_offshore", ""):
                    impact_functions_used[hazard]["curve_points"] = climada_service.get_curve_points(
                        _haz_code, asset_type
                    )

        result = {
            "time": times,
            "hazards": hazards_out,
            "distributions": distributions_out,
            "combined": combined,
            "combine_mode": combine_mode,
            "effective_stop_hours": effective_stop_hours,
            "pricing": pricing,
            "pricing_models": pricing_models,
            "combined_exceedance": combined_exceedance,
            "metrics": metrics_out,
            "wind_rose": wind_rose,
            "exposure_reference": self._build_exposure_reference(lat=lat, lon=lon),
            "hazard_pricing_models": hazard_pricing_models,
            "asset_type": asset_type,
            "impact_functions_used": impact_functions_used,
        }

        if include_series:
            result["series"] = series_out

        if hazards_out:
            worst_hazard = max(hazards_out.items(), key=lambda item: item[1]["max"])
            stop_pct = 0.0
            if combined["total_hours"]:
                stop_pct = combined["stop_hours"] / combined["total_hours"] * 100
            result["insights"] = [
                f"Parada combinada: {combined['stop_hours']}h ({stop_pct:.1f}% do periodo).",
                f"Maior pico observado: {worst_hazard[0]} com {worst_hazard[1]['max']:.2f}.",
                f"Regra de combinacao: {combine_mode}.",
            ]

        return result
    
    def get_statistics(
        self,
        variable: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lon_min: Optional[float] = None,
        lon_max: Optional[float] = None,
    ) -> Dict:
        """Calculate statistics for queried data."""
        
        data = self.query_data(
            variable, start_time, end_time,
            lat_min, lat_max, lon_min, lon_max
        )
        
        return {
            "mean": float(data.mean().values),
            "min": float(data.min().values),
            "max": float(data.max().values),
            "std": float(data.std().values),
        }
    
    def get_spatial_average(
        self,
        variable: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lon_min: Optional[float] = None,
        lon_max: Optional[float] = None,
    ) -> Dict:
        """Get spatial average time series."""
        
        data = self.query_data(
            variable, start_time, end_time,
            lat_min, lat_max, lon_min, lon_max
        )
        
        # Average over space
        spatial_avg = data.mean(dim=["lat", "lon"]).load()
        
        return {
            "time": spatial_avg.time.values.astype(str).tolist(),
            "values": spatial_avg.values.tolist(),
        }
    
    def get_grid_snapshot(
        self,
        variable: str,
        time: str,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lon_min: Optional[float] = None,
        lon_max: Optional[float] = None,
    ) -> Dict:
        """Get 2D grid data for a specific time."""
        
        # Select time
        data = self.ds[variable].sel(time=time, method="nearest")
        
        # Apply spatial slice
        if lat_min is not None or lat_max is not None:
            data = data.sel(lat=slice(lat_max, lat_min))
        
        if lon_min is not None or lon_max is not None:
            data = data.sel(lon=slice(lon_min, lon_max))
        
        # Load data
        data_loaded = data.load()
        
        return {
            "lat": data_loaded.lat.values.tolist(),
            "lon": data_loaded.lon.values.tolist(),
            "values": data_loaded.values.tolist(),
            "time": str(data_loaded.time.values),
        }

    def get_wind_hazard_snapshot(
        self,
        time: str,
        lat_min: Optional[float] = None,
        lat_max: Optional[float] = None,
        lon_min: Optional[float] = None,
        lon_max: Optional[float] = None,
        operational_limit_knots: float = 15.0,
        attention_limit_knots: float = 20.0,
    ) -> Dict:
        """Get wind speed/direction and operational status for a snapshot."""

        u10 = self.ds["u10"].sel(time=time, method="nearest")
        v10 = self.ds["v10"].sel(time=time, method="nearest")

        if lat_min is not None or lat_max is not None:
            u10 = u10.sel(lat=slice(lat_max, lat_min))
            v10 = v10.sel(lat=slice(lat_max, lat_min))

        if lon_min is not None or lon_max is not None:
            u10 = u10.sel(lon=slice(lon_min, lon_max))
            v10 = v10.sel(lon=slice(lon_min, lon_max))

        speed_ms = np.sqrt(u10**2 + v10**2)
        speed_knots = speed_ms * 1.94384

        # Meteorological direction (0-360, where wind comes from)
        direction_deg = (np.degrees(np.arctan2(u10, v10)) + 180.0) % 360.0

        speed_knots = speed_knots.load()
        direction_deg = direction_deg.load()

        status = np.zeros_like(speed_knots.values, dtype=np.uint8)
        status = np.where(speed_knots.values >= attention_limit_knots, 2, status)
        status = np.where(
            (speed_knots.values >= operational_limit_knots)
            & (speed_knots.values < attention_limit_knots),
            1,
            status,
        )

        return {
            "lat": speed_knots.lat.values.tolist(),
            "lon": speed_knots.lon.values.tolist(),
            "values": speed_knots.values.tolist(),
            "speed_knots": speed_knots.values.tolist(),
            "direction_deg": direction_deg.values.tolist(),
            "status": status.tolist(),
            "time": str(speed_knots.time.values),
            "limits": {
                "operational_max_knots": float(operational_limit_knots),
                "attention_max_knots": float(attention_limit_knots),
            },
        }

    def get_wind_point_risk(
        self,
        lat: float,
        lon: float,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        operational_limit_knots: float = 15.0,
        attention_limit_knots: float = 20.0,
        cost_attention_per_hour: Optional[float] = None,
        cost_stop_per_hour: Optional[float] = None,
        asset_type: str = "generic_offshore",
    ) -> Dict:
        """Calculate wind risk metrics for a single point."""

        u10 = self.ds["u10"].sel(lat=lat, lon=lon, method="nearest")
        v10 = self.ds["v10"].sel(lat=lat, lon=lon, method="nearest")

        if start_time or end_time:
            u10 = u10.sel(time=slice(start_time, end_time))
            v10 = v10.sel(time=slice(start_time, end_time))

        speed_ms = np.sqrt(u10**2 + v10**2)
        speed_knots = speed_ms * 1.94384
        direction_deg = (np.degrees(np.arctan2(u10, v10)) + 180.0) % 360.0

        speed_knots = speed_knots.load()
        direction_deg = direction_deg.load()

        status = np.zeros_like(speed_knots.values, dtype=np.uint8)
        status = np.where(speed_knots.values >= attention_limit_knots, 2, status)
        status = np.where(
            (speed_knots.values >= operational_limit_knots)
            & (speed_knots.values < attention_limit_knots),
            1,
            status,
        )

        total_hours = int(speed_knots.time.size)
        operational_hours = int(np.sum(status == 0))
        attention_hours = int(np.sum(status == 1))
        stop_hours = int(np.sum(status == 2))

        pricing = None
        if cost_attention_per_hour is not None or cost_stop_per_hour is not None:
            pricing = {
                "attention_cost": float(attention_hours * (cost_attention_per_hour or 0.0)),
                "stop_cost": float(stop_hours * (cost_stop_per_hour or 0.0)),
            }
            pricing["total_cost"] = pricing["attention_cost"] + pricing["stop_cost"]

        return {
            "lat": float(speed_knots.lat.values),
            "lon": float(speed_knots.lon.values),
            "time": speed_knots.time.values.astype(str).tolist(),
            "speed_knots": speed_knots.values.tolist(),
            "direction_deg": direction_deg.values.tolist(),
            "status": status.tolist(),
            "limits": {
                "operational_max_knots": float(operational_limit_knots),
                "attention_max_knots": float(attention_limit_knots),
            },
            "summary": {
                "total_hours": total_hours,
                "operational_hours": operational_hours,
                "attention_hours": attention_hours,
                "stop_hours": stop_hours,
            },
            "pricing": pricing,
        }


# Global instance
zarr_reader = ZarrDataReader()
