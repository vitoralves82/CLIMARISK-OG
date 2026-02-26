# CLIMARISK-OG

Plataforma de análise de risco climático para operações offshore, com foco em suporte à decisão operacional e impacto econômico/financeiro.

O projeto combina:
- engine de risco com curvas de vulnerabilidade CLIMADA por tipo de ativo offshore;
- backend de processamento climático (ERA5 Zarr) e cálculo de métricas atuariais;
- frontend analítico com mapa, dashboards e comparação de cenários.

---

## Arquitetura de Risco — Integração CLIMADA (Passo 1 de 3)

### Antes
```
valores ERA5 → classificação 3 estados (0/1/2) → fator fixo × asset_value
```

### Depois (Passo 1 atual)
```
valores ERA5 → ImpactFunc.calc_mdr(intensidade) → damage_ratio contínuo (0.0–1.0) × asset_value
```

### Roadmap técnico

| Passo | Status | Descrição |
|-------|--------|-----------|
| **1** | ✅ **Concluído** | `ImpactFuncSet` com curvas de vulnerabilidade por tipo de ativo; MDR contínuo substitui fatores fixos; backward compatible via `asset_type="generic_offshore"` |
| **2** | Planejado | `climada.Hazard` ← ERA5 Zarr + CMEMS; `climada.Exposures` ← shapefiles; `Impact.calc()` → EAI + curvas de período de retorno |
| **3** | Futuro | `climada-petals`: TropCyclone, StormEurope; incerteza; catálogos de eventos sintéticos |

---

## Tipos de Ativo Suportados

| `asset_type` | Nome | Curvas | Referências | Status |
|---|---|---|---|---|
| `fpso` | FPSO / FLNG | Vento (kn) + Onda (Hs m) | DNV-ST-0119, DNVGL-OS-E301, API RP 2SK | Calibrado |
| `fixed_platform` | Plataforma Fixa / Semi-sub | Vento + Onda | API RP 2A-WSD, ISO 19901-2 | Stub (usa FPSO) |
| `support_vessel` | Embarcação de Apoio PSV/AHTS | Vento + Onda | IMO MODU Code, DNV-GL | Stub (usa FPSO) |
| `subsea_pipeline` | Duto Submarino / Risers | Onda (sem vento direto) | DNV-ST-F101, DNVGL-RP-F105 | Stub |
| `generic_offshore` | Offshore Genérico (legado) | Step 0%/35%/100% | Modelo interno | Legado |

> **Backward compatibility:** `asset_type="generic_offshore"` (default) replica exatamente o comportamento anterior.
> Qualquer outro `asset_type` ativa curvas contínuas CLIMADA.

---

## Funcionalidades

- Análise multi-risco por ponto geográfico (vento + onda, extensível para corrente, temperatura).
- Curvas de vulnerabilidade contínuas por tipo de ativo (CLIMADA ImpactFuncSet).
- Classificação operacional por limites configuráveis (operacional / atenção / parada).
- Métricas atuariais completas: AAL, PML, VaR, TVaR, prêmio puro e técnico.
- Dashboards: histogramas, curvas de excedência, séries temporais, rosa dos ventos.
- Seleção de área/ponto via mapa; suporte a shapefiles para campos e blocos.
- Análise de exposição geoespacial (Monte Carlo, histograma 2D, grade de pontos).
- Scripts de ingestão ERA5 e CMEMS com armazenamento em Zarr.

---

## Estrutura de pastas (detalhada)

```text
CLIMARISK-OG/
├─ backend/
│  ├─ app/
│  │  ├─ main.py                 # Entrada da API FastAPI + inicialização ClimadaImpactService
│  │  ├─ database.py
│  │  ├─ routers/
│  │  │  ├─ analysis.py          # POST /multi-risk (asset_type), GET /asset-types, GET /vulnerability-curve
│  │  │  ├─ hazards.py           # GET /impact-functions, POST /wind/analyze, POST /wave/analyze
│  │  │  ├─ climate_data.py
│  │  │  ├─ data.py
│  │  │  └─ reports.py
│  │  ├─ services/
│  │  │  ├─ climada_impact.py    ← NOVO — ImpactFuncSet singleton (ClimadaImpactService)
│  │  │  ├─ zarr_reader.py       # Modificado — asset_type + damage ratios CLIMADA
│  │  │  ├─ netcdf_reader.py
│  │  │  └─ cmems_current.py
│  │  │  └─ vulnerability_curves/   ← NOVA PASTA
│  │  │     ├─ fpso_wind.csv     # Pontos calibrados — vento FPSO/FLNG
│  │  │     └─ fpso_wave.csv     # Pontos calibrados — onda FPSO/FLNG
│  │  ├─ models/
│  │  ├─ schemas/
│  │  └─ utils/
│  ├─ requirements.txt           # climada==6.1.0 ativado
│  └─ Dockerfile
│
├─ frontend/
│  └─ ...                        # React + TypeScript + Vite
│
├─ scripts/
│  ├─ download_era5_temperature_to_zarr.py
│  └─ download_cmems_current_to_zarr.py
│
├─ docker-compose.yml
└─ README.md
```

---

## API — Endpoints Principais

### Análise Multi-Risco

```
POST /api/v1/analysis/multi-risk
```

Campos adicionados nesta versão:

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `asset_type` | `str` | `"generic_offshore"` | Tipo de ativo para curva de vulnerabilidade |

Campos adicionados na resposta:

| Campo | Descrição |
|---|---|
| `asset_type` | Tipo de ativo usado no cálculo |
| `impact_functions_used` | Metadados e pontos das curvas CLIMADA usadas (por hazard) |
| `hazard_pricing_models[hazard].impact_function` | Descrição da curva por hazard |

### Tipos de Ativo

```
GET /api/v1/analysis/asset-types
GET /api/v1/hazards/asset-types
```

### Curvas de Vulnerabilidade

```
GET /api/v1/analysis/vulnerability-curve?hazard=WS&asset_type=fpso
GET /api/v1/hazards/impact-functions
GET /api/v1/hazards/impact-functions/{asset_type}
```

### Análise Pontual de Perigo

```
POST /api/v1/hazards/wind/analyze?lat=...&lon=...&wind_threshold=35&asset_type=fpso
POST /api/v1/hazards/wave/analyze?lat=...&lon=...&wave_threshold=5&asset_type=fpso
```

---

## Pré-requisitos

### Sistema
- Python 3.10+
- Node.js 18+ / npm 9+
- Git

### Dados
- Arquivo ERA5 em formato Zarr (caminhos configurados em `zarr_reader.py`)
- Credenciais CDS (ERA5) e Copernicus Marine (CMEMS) para re-ingestão
- Token Mapbox para o mapa no frontend

---

## Como rodar localmente

### 1) Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

> **Nota:** `climada==6.1.0` está listado em `requirements.txt`.
> Se o CLIMADA não estiver instalado, o serviço funciona com interpolação numpy como fallback — a API retorna exatamente os mesmos resultados.

Documentação interativa da API:
- http://127.0.0.1:8000/api/docs

### 2) Frontend

```bash
cd frontend
npm install
npm run dev
```

Aplicação web:
- http://localhost:5173

### 3) Variáveis de ambiente

Copie `.env.example` para `.env` e configure:

| Variável | Descrição |
|---|---|
| `VITE_MAPBOX_TOKEN` | Token Mapbox para o mapa |
| `ZARR_PATH` | Caminho para o arquivo ERA5 Zarr local |

---

## Verificação CLIMADA

```bash
# Verificar se ClimadaImpactService inicializa corretamente
python -c "
from backend.app.services.climada_impact import climada_service
import numpy as np

# Damage ratio a 35 nós para FPSO — esperado: ~0.35
dr_wind = climada_service.calc_damage_ratio('WS', np.array([35.0]), 'fpso')
print(f'FPSO 35 kn → MDR = {dr_wind[0]*100:.1f}%')

# Damage ratio a 5 m Hs para FPSO — esperado: ~0.38
dr_wave = climada_service.calc_damage_ratio('OW', np.array([5.5]), 'fpso')
print(f'FPSO 5.5 m Hs → MDR = {dr_wave[0]*100:.1f}%')

print('CLIMADA nativo:', climada_service.climada_available)
"
```

---

## Stack tecnológico

### Frontend
- React 18 + TypeScript
- Vite
- Chart.js + react-chartjs-2
- Mapbox GL + react-map-gl
- Deck.gl
- MUI (Material UI)
- Zustand

### Backend
- FastAPI + Uvicorn
- Pydantic v2
- SQLAlchemy / SQLModel / Alembic
- **CLIMADA 6.1.0** — ImpactFuncSet por tipo de ativo offshore
- Xarray, NetCDF4, Zarr (ERA5 local)
- GeoPandas, Shapely, Fiona, Rasterio, Rioxarray
- Celery + Redis (estrutura preparada)

### Infraestrutura
- Docker e Docker Compose
- Frontend: Vercel (deploy automático a cada push na main)
- Backend: DigitalOcean Droplet (API + Zarr em memória)
- Dados climáticos: armazenamento local / S3 (arquivo Zarr ERA5)

---

## Scripts de ingestão

- `scripts/download_era5_temperature_to_zarr.py` — temperatura ERA5
- `scripts/download_cmems_current_to_zarr.py` — correntes CMEMS

---

## Referências Técnicas das Curvas de Vulnerabilidade

| Curva | Referência |
|-------|-----------|
| FPSO — vento | DNV-ST-0119 (Marine Operations and Marine Warranty), OGP Report 434-14 |
| FPSO — onda | DNVGL-OS-E301 (Position Mooring), API RP 2SK (Stationkeeping) |
| Plataforma fixa | API RP 2A-WSD (Fixed Platforms), ISO 19901-2 |
| Duto submarino | DNV-ST-F101, DNVGL-RP-F105 (Free Spanning Pipelines) |
| Modelo CLIMADA | Aznar-Siguan & Bresch (2019), *Geosci. Model Dev.* 12, 3085–3097 |
| Excedência | Weibull (1939), Hazen (1914), Gringorten (1963) |
| VaR / TVaR | Artzner et al. (1999), *Mathematical Finance* 9(3) |
| AAL / PML | OASIS Loss Modelling Framework; AIR Worldwide; RMS |

---

## Contato

- Responsável: Barbara Dias
- E-mail: [preencher]
- LinkedIn/GitHub: [preencher]

---

## Última atualização

- 26/02/2026 — Passo 1: Integração CLIMADA ImpactFuncSet com curvas de vulnerabilidade contínuas por tipo de ativo offshore.
