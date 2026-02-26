"""
CLIMADA Impact Function Service — CLIMARISK-OG
===============================================

Passo 1 da integração CLIMADA: ImpactFuncSet com curvas de vulnerabilidade
contínuas por tipo de ativo offshore, substituindo o modelo discreto de 3 estados
(0% / 35% / 100%) por funções de dano física e calibrada por referências técnicas.

Arquitetura:
    ClimadaImpactService  ← módulo-level singleton `climada_service`
        └── OffshoreImpactFunctions  ← catálogo de ImpactFunc por ativo/perigo
                └── ImpactFunc (CLIMADA nativo) ou _NumpyImpactFunc (fallback)

Backward compatibility:
    asset_type="generic_offshore" (default) → modelo discreto legado em zarr_reader.py.
    Qualquer outro asset_type  → curvas CLIMADA contínuas.

Evolução futura (Passo 2):
    climada.Hazard  ← ERA5 Zarr / CMEMS NetCDF
    climada.Exposures ← GeoJSON / shapefile de ativos
    Impact.calc() → eai_exp (Expected Annual Impact) + return period curves

Referências:
    DNV-ST-0119   — Marine Operations and Marine Warranty
    DNVGL-OS-E301 — Position Mooring
    API RP 2SK    — Stationkeeping for Floating Structures
    OGP Report 434-14 — Metocean Studies for Field Development
    ISO 19901-2   — Fixed Steel Structures
    API RP 2A-WSD — Fixed Platforms
    DNV-ST-F101   — Submarine Pipeline Systems
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── CLIMADA optional dependency ───────────────────────────────────────────────
try:
    from climada.entity import ImpactFunc, ImpactFuncSet  # type: ignore

    _CLIMADA_AVAILABLE = True
    logger.info("CLIMADA disponível — usando ImpactFuncSet nativo.")
except ImportError:
    _CLIMADA_AVAILABLE = False
    logger.warning(
        "CLIMADA não instalado. Curvas de vulnerabilidade funcionam via numpy "
        "como fallback. Instale com: pip install climada==6.1.0"
    )

# ── Hazard type codes (CLIMADA convention + custom extensions) ────────────────
HAZ_WIND = "WS"  # WindStorm — standard CLIMADA code
HAZ_WAVE = "OW"  # Ocean Wave — custom extension (não existe code padrão CLIMADA)

# ── Asset type registry ───────────────────────────────────────────────────────
ASSET_TYPES: Dict[str, Dict] = {
    "fpso": {
        "name": "FPSO / FLNG",
        "description": (
            "Unidade flutuante de produção, armazenamento e offloading. "
            "Alta inércia estrutural; operações sensíveis a vento e onda acima "
            "de limiares operacionais definidos pelo Marine Warranty Surveyor."
        ),
        "references": ["DNV-ST-0119", "DNVGL-OS-E301", "API RP 2SK", "OGP 434-14"],
        "status": "available",
        "hazards_supported": ["wind", "wave"],
    },
    "fixed_platform": {
        "name": "Plataforma Fixa / Semi-submersível",
        "description": (
            "Estrutura ancorada ao fundo oceânico. Vulnerabilidade estrutural "
            "maior para ondas longas (fadiga) do que para vento."
        ),
        "references": ["API RP 2A-WSD", "ISO 19901-2"],
        "status": "stub",  # usa curvas FPSO como proxy até calibração
        "hazards_supported": ["wind", "wave"],
    },
    "support_vessel": {
        "name": "Embarcação de Apoio (PSV / AHTS)",
        "description": (
            "Navios de suporte offshore. Maior sensibilidade a vento e ondas "
            "em comparação com FPSOs; limiares operacionais mais conservadores."
        ),
        "references": ["IMO MODU Code", "DNV-GL Ship Rules"],
        "status": "stub",
        "hazards_supported": ["wind", "wave"],
    },
    "subsea_pipeline": {
        "name": "Duto Submarino / Risers",
        "description": (
            "Infraestrutura submersa. Praticamente insensível a vento; "
            "vulnerabilidade dominada por correntes e ondas. "
            "Integração com correntes CMEMS prevista no Passo 2."
        ),
        "references": ["DNV-ST-F101", "DNVGL-RP-F105", "API RP 1111"],
        "status": "stub",
        "hazards_supported": ["wave"],
    },
    "generic_offshore": {
        "name": "Offshore Genérico (legado)",
        "description": (
            "Modelo discreto de 3 estados (0% / 35% / 100%) compatível com o "
            "sistema original. Usa fatores de perda configuráveis pelo usuário "
            "(attention_loss_factor / stop_loss_factor), NÃO curvas CLIMADA. "
            "Use para comparação ou quando os limiares operacionais dominam."
        ),
        "references": ["Modelo interno CLIMARISK-OG — compatibilidade retroativa"],
        "status": "legacy",
        "hazards_supported": ["wind", "wave"],
    },
}


# ── Raw curve data ─────────────────────────────────────────────────────────────
# Cada função retorna (intensity, mdd, paa).
# MDR = MDD × PAA  →  damage ratio por passo de tempo.
# Fontes estão nos docstrings de cada curva.

def _fpso_wind_curve() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Curva de vulnerabilidade FPSO/FLNG para vento (nós).

    MDD: fração da capacidade operacional/financeira perdida nesta intensidade.
    PAA: fração dos ativos exposta (aumenta com a intensidade).

    Baseado em: DNV-ST-0119 (Marine Operations), OGP Report 434-14 (Metocean),
    dados operacionais de campos do pré-sal da Bacia de Santos (revisão literária).
    """
    intensity = np.array(
        [0.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 65.0],
        dtype=float,
    )
    mdd = np.array(
        [0.00, 0.01, 0.04, 0.08, 0.14, 0.24, 0.35, 0.50, 0.65, 0.78, 0.88, 0.95],
        dtype=float,
    )
    paa = np.array(
        [0.00, 0.10, 0.30, 0.60, 0.85, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00],
        dtype=float,
    )
    return intensity, mdd, paa


def _fpso_wave_curve() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Curva de vulnerabilidade FPSO/FLNG para altura significativa de onda — Hs (m).

    Baseado em: DNVGL-OS-E301 (Position Mooring), API RP 2SK (Stationkeeping),
    diretrizes operacionais Petrobras / ANP para FPSOs na Bacia de Santos.
    """
    intensity = np.array(
        [0.0, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 8.0, 10.0, 12.0],
        dtype=float,
    )
    mdd = np.array(
        [0.00, 0.01, 0.04, 0.10, 0.22, 0.38, 0.55, 0.72, 0.85, 0.93],
        dtype=float,
    )
    paa = np.array(
        [0.00, 0.10, 0.40, 0.70, 1.00, 1.00, 1.00, 1.00, 1.00, 1.00],
        dtype=float,
    )
    return intensity, mdd, paa


def _subsea_wave_curve() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Proxy de vulnerabilidade de dutos submarinos a ondas (Hs em metros).
    Sensibilidade menor nas baixas intensidades; efeitos críticos acima de 6 m Hs
    (fadiga de risers, estabilidade lateral do duto).
    """
    intensity = np.array(
        [0.0, 3.0, 5.0, 7.0, 9.0, 12.0, 15.0],
        dtype=float,
    )
    mdd = np.array(
        [0.00, 0.00, 0.03, 0.10, 0.28, 0.55, 0.80],
        dtype=float,
    )
    paa = np.array(
        [0.00, 0.00, 0.20, 0.60, 1.00, 1.00, 1.00],
        dtype=float,
    )
    return intensity, mdd, paa


def _generic_wind_step_curve() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Curva degrau de vento (nós) que replica o modelo discreto legado:
    < 15 kn → 0%, 15–20 kn → 35%, ≥ 20 kn → 100%.
    PAA = 1 em todos os pontos (curva de dano puro).
    """
    intensity = np.array([0.0, 14.9, 15.0, 19.9, 20.0, 100.0], dtype=float)
    mdd = np.array([0.00, 0.00, 0.35, 0.35, 1.00, 1.00], dtype=float)
    paa = np.ones(6, dtype=float)
    return intensity, mdd, paa


def _generic_wave_step_curve() -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Curva degrau de onda (Hs m) que replica o modelo discreto legado:
    < 2 m → 0%, 2–4 m → 35%, ≥ 4 m → 100%.
    """
    intensity = np.array([0.0, 1.9, 2.0, 3.9, 4.0, 20.0], dtype=float)
    mdd = np.array([0.00, 0.00, 0.35, 0.35, 1.00, 1.00], dtype=float)
    paa = np.ones(6, dtype=float)
    return intensity, mdd, paa


# ── ImpactFunc builder ────────────────────────────────────────────────────────

class _NumpyImpactFunc:
    """
    Substituto numpy-only para ImpactFunc do CLIMADA.
    Usado quando climada não está instalado — API idêntica à necessária.
    """

    __slots__ = ("haz_type", "id", "name", "intensity_unit", "intensity", "mdd", "paa")

    def __init__(
        self,
        haz_type: str,
        func_id: int,
        name: str,
        intensity_unit: str,
        intensity: np.ndarray,
        mdd: np.ndarray,
        paa: np.ndarray,
    ) -> None:
        self.haz_type = haz_type
        self.id = func_id
        self.name = name
        self.intensity_unit = intensity_unit
        self.intensity = intensity
        self.mdd = mdd
        self.paa = paa


def _build_impact_func(
    haz_type: str,
    func_id: int,
    name: str,
    intensity_unit: str,
    intensity: np.ndarray,
    mdd: np.ndarray,
    paa: np.ndarray,
) -> "_NumpyImpactFunc | ImpactFunc":
    """Constrói ImpactFunc CLIMADA ou _NumpyImpactFunc dependendo da disponibilidade."""
    if _CLIMADA_AVAILABLE:
        func = ImpactFunc(
            haz_type=haz_type,
            id=func_id,
            name=name,
            intensity_unit=intensity_unit,
            intensity=intensity,
            mdd=mdd,
            paa=paa,
        )
        func.check()
        return func
    return _NumpyImpactFunc(haz_type, func_id, name, intensity_unit, intensity, mdd, paa)


# ── Catalogue ─────────────────────────────────────────────────────────────────

class OffshoreImpactFunctions:
    """
    Catálogo de curvas de vulnerabilidade offshore por tipo de ativo e perigo.

    Para adicionar um novo tipo de ativo:
        1. Defina ``_<type>_<hazard>_curve()`` retornando (intensity, mdd, paa).
        2. Registre em ``_build_all()`` sob a chave do asset_type.
        3. Adicione entrada em ``ASSET_TYPES`` com metadados.
    """

    def __init__(self) -> None:
        # registry: asset_type → {haz_type_code: ImpactFunc}
        self._registry: Dict[str, Dict[str, object]] = {}
        self._build_all()

    def _build_all(self) -> None:
        fpso_wind = _build_impact_func(
            HAZ_WIND, 1, "FPSO/FLNG — Wind Vulnerability (kn)", "kn",
            *_fpso_wind_curve(),
        )
        fpso_wave = _build_impact_func(
            HAZ_WAVE, 2, "FPSO/FLNG — Wave Vulnerability (Hs m)", "m",
            *_fpso_wave_curve(),
        )

        self._registry["fpso"] = {HAZ_WIND: fpso_wind, HAZ_WAVE: fpso_wave}

        # Stubs — reusam curvas FPSO até calibração específica
        self._registry["fixed_platform"] = self._registry["fpso"]
        self._registry["support_vessel"] = self._registry["fpso"]

        # Subsea pipeline: sem sensibilidade direta a vento
        zero_wind = _build_impact_func(
            HAZ_WIND, 3, "Subsea Pipeline — Wind (sem sensibilidade direta)", "kn",
            np.array([0.0, 100.0], dtype=float),
            np.array([0.0, 0.0], dtype=float),
            np.array([0.0, 0.0], dtype=float),
        )
        sub_wave = _build_impact_func(
            HAZ_WAVE, 4, "Subsea Pipeline — Wave Vulnerability (Hs m)", "m",
            *_subsea_wave_curve(),
        )
        self._registry["subsea_pipeline"] = {HAZ_WIND: zero_wind, HAZ_WAVE: sub_wave}

        # Generic offshore (legacy step curves)
        gen_wind = _build_impact_func(
            HAZ_WIND, 5, "Generic Offshore — Wind step (legado)", "kn",
            *_generic_wind_step_curve(),
        )
        gen_wave = _build_impact_func(
            HAZ_WAVE, 6, "Generic Offshore — Wave step (legado)", "m",
            *_generic_wave_step_curve(),
        )
        self._registry["generic_offshore"] = {HAZ_WIND: gen_wind, HAZ_WAVE: gen_wave}

    def get(
        self, asset_type: str, haz_type: str
    ) -> "Optional[_NumpyImpactFunc | ImpactFunc]":
        """Retorna ImpactFunc para o par ativo/perigo, ou None se não encontrado."""
        asset_key = asset_type if asset_type in self._registry else "generic_offshore"
        return self._registry[asset_key].get(haz_type)

    def get_funcset(self, asset_type: str) -> "Optional[ImpactFuncSet]":
        """Retorna ImpactFuncSet CLIMADA com todas as curvas do tipo de ativo."""
        if not _CLIMADA_AVAILABLE:
            return None
        funcs = list(
            self._registry.get(asset_type, self._registry["generic_offshore"]).values()
        )
        if not funcs:
            return None
        fs = ImpactFuncSet()
        for f in funcs:
            fs.append(f)
        return fs


# ── Service ───────────────────────────────────────────────────────────────────

class ClimadaImpactService:
    """
    Fachada para o catálogo de funções de impacto CLIMADA.

    Exemplo de uso:
        damage = climada_service.calc_damage_ratio("WS", wind_speed_array, "fpso")
        # damage.shape == wind_speed_array.shape, valores em [0.0, 1.0]

    Passo 2 (futuro):
        hazard = climada_service.build_hazard_from_zarr(ds, haz_type="WS")
        exposures = climada_service.build_exposures(assets_gdf)
        impact = Impact()
        impact.calc(exposures, impf_set, hazard)
        eai = impact.eai_exp  # Expected Annual Impact por ativo
    """

    def __init__(self) -> None:
        self._catalogue = OffshoreImpactFunctions()
        logger.info(
            "ClimadaImpactService inicializado. CLIMADA nativo: %s. Ativos: %s",
            _CLIMADA_AVAILABLE,
            list(ASSET_TYPES.keys()),
        )

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def climada_available(self) -> bool:
        """True se CLIMADA estiver instalado e disponível."""
        return _CLIMADA_AVAILABLE

    # ── Public API ───────────────────────────────────────────────────────────

    def get_available_asset_types(self) -> List[Dict]:
        """Lista de tipos de ativo disponíveis com metadados para a API."""
        return [{"id": k, **v} for k, v in ASSET_TYPES.items()]

    def calc_damage_ratio(
        self,
        haz_type: str,
        intensity: np.ndarray,
        asset_type: str = "generic_offshore",
    ) -> np.ndarray:
        """
        Calcula o Damage Ratio (MDR = MDD × PAA) para cada valor de intensidade.

        A interpolação é linear entre os pontos calibrados da curva;
        valores fora do range são extrapolados para o limite (0 ou máximo).

        Parâmetros
        ----------
        haz_type : str
            Código do perigo: ``"WS"`` (vento, nós) ou ``"OW"`` (onda, metros Hs).
        intensity : np.ndarray
            Array de intensidades (mesma unidade da curva).
        asset_type : str
            Tipo de ativo (chave de ``ASSET_TYPES``).

        Retorna
        -------
        np.ndarray
            Damage ratio, mesmo shape de ``intensity``, valores em [0.0, 1.0].
        """
        func = self._catalogue.get(asset_type, haz_type)
        if func is None:
            logger.warning(
                "Sem ImpactFunc para %s/%s — retornando zeros.", asset_type, haz_type
            )
            return np.zeros_like(np.asarray(intensity, dtype=float))

        mdr_curve = func.mdd * func.paa
        result = np.interp(
            np.asarray(intensity, dtype=float),
            func.intensity,
            mdr_curve,
            left=0.0,
            right=float(mdr_curve[-1]),
        )
        return np.clip(result, 0.0, 1.0)

    def get_curve_points(self, haz_type: str, asset_type: str) -> Dict:
        """
        Retorna os pontos da curva calibrada para visualização no frontend.

        Inclui os pontos brutos (calibration points) e uma grade fina de
        100 pontos interpolados para renderização de gráfico suave.
        """
        func = self._catalogue.get(asset_type, haz_type)
        if func is None:
            return {
                "haz_type": haz_type,
                "asset_type": asset_type,
                "intensity": [],
                "mdd": [],
                "paa": [],
                "mdr": [],
                "fine_intensity": [],
                "fine_mdr": [],
            }

        mdr_raw = (func.mdd * func.paa).tolist()
        fine_x = np.linspace(func.intensity[0], func.intensity[-1], 100)
        fine_y = self.calc_damage_ratio(haz_type, fine_x, asset_type)

        return {
            "haz_type": func.haz_type,
            "name": func.name,
            "intensity_unit": func.intensity_unit,
            "asset_type": asset_type,
            "climada_native": _CLIMADA_AVAILABLE,
            "intensity": func.intensity.tolist(),
            "mdd": func.mdd.tolist(),
            "paa": func.paa.tolist(),
            "mdr": mdr_raw,
            "fine_intensity": fine_x.tolist(),
            "fine_mdr": fine_y.tolist(),
        }

    def describe_curve(self, haz_type: str, asset_type: str) -> Dict:
        """Retorna metadados compactos da curva usada num cálculo (para incluir na resposta)."""
        func = self._catalogue.get(asset_type, haz_type)
        asset_meta = ASSET_TYPES.get(asset_type, ASSET_TYPES["generic_offshore"])
        if func is None:
            return {"asset_type": asset_type, "haz_type": haz_type, "available": False}
        return {
            "available": True,
            "climada_native": _CLIMADA_AVAILABLE,
            "asset_type": asset_type,
            "asset_name": asset_meta["name"],
            "curve_name": func.name,
            "haz_type": func.haz_type,
            "intensity_unit": func.intensity_unit,
            "n_calibration_points": len(func.intensity),
            "references": asset_meta.get("references", []),
            "status": asset_meta.get("status", "unknown"),
        }

    def get_impact_funcset(self, asset_type: str) -> "Optional[ImpactFuncSet]":
        """Retorna ImpactFuncSet CLIMADA para o tipo de ativo (None se CLIMADA indisponível)."""
        return self._catalogue.get_funcset(asset_type)


# ── Module-level singleton ────────────────────────────────────────────────────
climada_service = ClimadaImpactService()
