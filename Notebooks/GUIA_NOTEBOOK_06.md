# 🔥 GUIA EXPLICATIVO — Notebook 06: Incendio Florestal (*WildFire*) em Duque de Caxias

## Para que serve este *notebook*?

Este *notebook* é a **sexta evidência técnica de TRL5** do projeto CLIMARISK-OG e o **primeiro da Fase 2** (novos *hazards*). Enquanto os NB01-NB05 cobriram inundação fluvial e ondas de calor, este NB06 introduz um **terceiro *hazard* terrestre** — **incêndio florestal** (*wildfire*) — usando o módulo nativo `WildFire` do `climada_petals`.

**H × E × V = Risco**

Onde:
- **H** (*Hazard*) = perigo climático (incêndio florestal / focos de calor)
- **E** (*Exposure*) = ativos em risco (REDUC, com valor financeiro)
- **V** (*Vulnerability*) = função de dano (quanto se perde por nível de intensidade do fogo)

A diferença fundamental em relação aos *notebooks* anteriores:

| | NB01 (Inundação) | NB02 (Calor) | **NB06 (*WildFire*)** |
|:---|:---|:---|:---|
| **Tipo de dano** | Físico-destrutivo | Operacional | **Misto (estrutural + operacional)** |
| **Módulo CLIMADA** | `RiverFlood` (petals) | `Hazard` genérico | **`WildFire` (petals)** |
| **Dados de entrada** | Profundidade (m) | Temperatura (°C) | **FIRMS/MODIS (*brightness*, K)** |
| **Fração afetada** | Parcial | Total | **Parcial (onde há focos)** |

---

## Por que incêndios florestais são relevantes para a REDUC?

A REDUC está localizada na Baixada Fluminense, uma região com **vegetação remanescente de Mata Atlântica degradada**, áreas de pastagem abandonada e terrenos baldios que acumulam biomassa combustível. Fatores relevantes:

1. **Proximidade com vegetação** — O entorno da REDUC inclui áreas de cobertura vegetal (Serra de Petrópolis a norte, manguezais da Baía de Guanabara a sul) e extensas áreas de vegetação secundária degradada.

2. **Período seco pronunciado** — Julho a outubro concentra os meses com menor precipitação na Baixada Fluminense. O INPE BDQueimadas registra picos de focos de calor neste período em todo o estado do Rio de Janeiro.

3. **Dados INPE para a região** — O BDQueimadas monitora focos de calor por satélite desde 1998, com cobertura para Duque de Caxias. A região metropolitana do Rio apresenta média de 15-40 focos/ano num raio de 30 km da REDUC.

4. **Risco industrial específico** — Incêndios florestais próximos a refinarias representam riscos de:
   - Ignição de vapores e gases por radiação térmica
   - Contaminação de sistemas de ventilação por fumaça
   - Evacuação forçada de pessoal
   - Danos a infraestrutura periférica (*pipelines*, subestações, estradas de acesso)
   - Interrupção de fornecimento de água (captação comprometida por cinzas)

5. **Tendência climática** — Projeções CMIP6 indicam aumento da frequência e intensidade de secas prolongadas no Sudeste brasileiro (IPCC AR6, WG2, Cap. 12), elevando o risco de incêndios.

---

## Explicação Bloco a Bloco

### Bloco 0 — Instalação do CLIMADA
Instala `climada` e `climada_petals`. O `climada_petals` é **obrigatório** neste *notebook* — o módulo `WildFire` vive exclusivamente nele. Tempo estimado: ~3-5 minutos no Colab.

### Bloco 1 — Verificação de Ambiente
Confirma a versão do CLIMADA e **testa explicitamente** a importação de `WildFire` do `climada_petals`. Se a importação falhar (por dependências pesadas como GDAL), o *notebook* sinaliza e usa o *fallback* no Bloco 6B. A *flag* `PETALS_WF_OK` rastreia o resultado.

### Bloco 2 — *Imports*
Carrega as classes habituais do CLIMADA core, mais:
- `pandas` — necessário para manipular o *DataFrame* FIRMS
- `scipy.sparse` — para a matriz de intensidade no *fallback*
- `WildFire` de `climada_petals.hazard` — o módulo nativo
- `ONE_LAT_KM` — constante para converter km em graus (resolução de *centroids*)

### Bloco 3 — Definição do Ativo (REDUC)
**Idêntico ao NB01-NB03.** Mesmas coordenadas (-22.5167, -43.2833), mesmo valor (USD 5 bilhões), mesma *bounding box* (+-0.15 graus, ~17 km). Consistência entre *notebooks* é requisito para comparabilidade.

### Bloco 4 — *Exposures* (E)
Cria o `GeoDataFrame` com o ativo georreferenciado. A diferença em relação aos *notebooks* anteriores:

| Campo | NB01 (Inundação) | NB02 (Calor) | **NB06 (*WildFire*)** |
|:---|:---|:---|:---|
| Coluna de vínculo | `impf_RF = 61` | `impf_HW = 1` | **`impf_WFsingle = 1`** |
| Significado | *Impact Function* JRC | Customizada industrial | **Placeholder (será substituída)** |

O código `WFsingle` é o `haz_type` nativo do módulo `WildFire` do CLIMADA. A convenção `impf_` + código do *hazard* vincula a *Exposure* à função de dano correta.

### Bloco 5 — Geração de Dados Sintéticos (formato FIRMS/MODIS)

**Este é o bloco mais diferente dos *notebooks* anteriores.** Enquanto NB01/NB02 criavam *hazards* diretamente via matrizes de intensidade, aqui geramos um *DataFrame* no **formato exato do FIRMS** (NASA), que é o *input* esperado pelo módulo `WildFire`.

**Colunas do formato FIRMS:**

| Coluna | Tipo | Descrição |
|:---|:---|:---|
| `latitude` | float | Latitude do foco (graus decimais) |
| `longitude` | float | Longitude do foco (graus decimais) |
| `brightness` | float | Temperatura de brilho MODIS (Kelvin) |
| `scan` | float | Dimensão do pixel na direção do *scan* |
| `track` | float | Dimensão do pixel na direção do *track* |
| `acq_date` | string | Data de aquisição (YYYY-MM-DD) |
| `acq_time` | int | Horário UTC (HHMM) |
| `satellite` | string | Satélite (T = *Terra*, A = *Aqua*) |
| `confidence` | int | Confiança da detecção (0-100) |
| `version` | string | Versão do algoritmo |
| `bright_t31` | float | Temperatura de brilho no canal 31 (K) |
| `frp` | float | *Fire Radiative Power* (MW) |
| `daynight` | string | Detecção diurna (D) ou noturna (N) |

**Calibração com dados INPE BDQueimadas:**
- 10-45 focos por ano (variabilidade interanual realista)
- Concentração em julho-outubro (período seco da Baixada Fluminense)
- *Brightness* entre 310-370 K (típico de vegetação rasteira/degradada)
- FRP entre 3-50+ MW (distribuição exponencial, maioria de baixa intensidade)

**Por que FIRMS e não INPE diretamente?** O módulo `WildFire` do `climada_petals` foi projetado para consumir dados no formato FIRMS/MODIS da NASA. Os dados do INPE BDQueimadas usam formato diferente (colunas em português, sem *brightness*). Para manter a decisão de **sempre usar o módulo nativo**, adaptamos os dados ao formato esperado.

### Bloco 6 — *Hazard* (H) — `WildFire` via `climada_petals`

Usa o método `WildFire.from_hist_fire_seasons_FIRMS()` — o método correto (não-depreciado) que:
1. Recebe o *DataFrame* FIRMS
2. Agrupa focos por **estação de fogo** (*fire season*)
3. Identifica incêndios individuais (agrupamento espacial + temporal)
4. Calcula intensidade (*brightness*) interpolada nos *centroids*
5. Retorna um objeto `Hazard` com `haz_type='WFsingle'`

**Parâmetro `hemisphere='SHS'`**: como a REDUC está no Hemisfério Sul, a *fire season* vai de **julho a junho** (não de janeiro a dezembro). Isso é crítico para a correta atribuição de focos a cada ano.

**Resolução**: ~1 km (resolução nativa do MODIS), via `Centroids.from_pnt_bounds()`.

### Bloco 6B — *Fallback* (Hazard genérico)

**Este bloco só executa se o Bloco 6 falhar.** Algumas instalações do `climada_petals` no Colab podem ter problemas com dependências pesadas (GDAL, *rasterio*). O *fallback*:

1. Cria *centroids* manualmente na mesma grade
2. Para cada ano, encontra o *centroid* mais próximo de cada foco
3. Atribui *brightness* máxima como intensidade
4. Constrói a matriz `intensity` (sparse) e `fraction`
5. Frequência = 1/*n_anos* por evento

O resultado é funcionalmente equivalente, mas **sem** os algoritmos de agrupamento e propagação do módulo nativo. A *flag* `USE_NATIVE_WF` rastreia qual método foi usado, e essa informação vai para o JSON.

### Bloco 7 — *Impact Function* (V) — PLACEHOLDER

**STATUS: PLACEHOLDER** — esta função será substituída na **Etapa 2B**.

A curva atual é uma **aproximação linear simplificada**:

| *Brightness* (K) | MDR (%) | Interpretação |
|:---:|:---:|:---|
| 0-300 | 0% | Sem detecção de fogo |
| 300 | 0% | Limiar de detecção MODIS |
| 350 | 5% | Fogo de baixa intensidade (vegetação rasteira) |
| 400 | 12% | Fogo moderado (danos periféricos) |
| 450 | 22% | Fogo severo (danos a infraestrutura exposta) |
| 500 | 30% | Fogo extremo (MDR máximo) |

**Por que MDR máximo de 30%?** Refinarias possuem múltiplas camadas de proteção contra incêndio:
- Sistemas fixos de combate (*sprinklers*, monitores de espuma, dilúvio)
- Brigada industrial 24h com treinamento periódico
- *Layout* projetado com distâncias de segurança (API 2510, NR-20)
- Tanques com bacia de contenção dimensionada para 100% do volume
- Incêndios florestais causam danos predominantemente **indiretos** (interrupção, evacuação, contaminação por fumaça) — não destruição direta como um *BLEVE* ou explosão industrial.

**Referências pendentes para Etapa 2B:**
- SFPE *Handbook of Fire Protection Engineering*
- API RP 752/753 (*Management of Hazards in Process Plants*)
- Christou & Mattarelli (2000) — *Land-use planning near industrial sites*
- ARIA/BARPI — Base de dados francesa de acidentes industriais

### Bloco 7B — Visualização da *Impact Function*
Gera um gráfico da curva MDR com **badge** visual "STATUS: PLACEHOLDER" para deixar inequívoco que esta curva é provisória. O *badge* aparece em vermelho com fundo amarelo de alerta.

### Bloco 8 — Cálculo de Impacto (H x E x V)
A linha central é **idêntica** ao NB01/NB02:

```python
imp_wf = ImpactCalc(exp, impf_set, haz_wf).impact(save_mat=True)
```

Universalidade do CLIMADA: o `ImpactCalc` é agnóstico ao tipo de *hazard*. Funciona da mesma forma para inundação, calor ou incêndio.

Os *outputs* são os mesmos:
- **EAI** (*Expected Annual Impact*) — perda anual esperada
- **`eai_exp`** — EAI por localização
- **`at_event`** — impacto por evento (*fire season*)

### Bloco 9 — Visualizações
Painel de 4 gráficos:
1. **Mapa de intensidade máxima** — *scatter plot* dos *centroids* afetados, coloridos por *brightness*, com marcador da REDUC
2. **Focos por ano** — gráfico de barras mostrando variabilidade interanual
3. **Distribuição de *brightness*** — histograma com linha de limiar (300 K)
4. **Impacto por *fire season*** — barras de impacto com linha horizontal de EAI

### Bloco 10 — Resumo Executivo
Consolida todos os resultados, incluindo:
- Método usado (*nativo* vs. *fallback*)
- Status da *impact function* (PLACEHOLDER)
- Referências pendentes para Etapa 2B
- **6 limitações documentadas** — requisito TRL5

### Bloco 11 — Exportação JSON
Salva resultados no **mesmo *schema*** dos *notebooks* anteriores. Campos específicos do NB06:

| Campo JSON | Valor |
|:---|:---|
| `hazards.WF.type` | `'WFsingle'` |
| `hazards.WF.type_name` | `'WildFire'` |
| `hazards.WF.intensity_unit` | `'K (brightness)'` |
| `hazards.WF.data_source.format` | `'FIRMS/MODIS (synthetic)'` |
| `hazards.WF.data_source.calibration` | `'INPE BDQueimadas, Duque de Caxias (2015-2024)'` |
| `hazards.WF.hazard_method` | Registra se usou nativo ou *fallback* |
| `hazards.WF.impact_function.status` | **`'placeholder'`** |
| `hazards.WF.impact_function.pending_references` | Lista de 4 referências para Etapa 2B |

O campo `status: "placeholder"` é **novo** — introduzido neste *notebook* para que o *backend* e o *frontend* possam sinalizar ao usuário que este resultado usa uma curva provisória.

### Bloco 12 — Diagnóstico e Artefatos
Executa **8 *checks*** de consistência:
1. EAI *WildFire* > 0
2. Impacto não excede valor do ativo
3. `haz_type` = `WFsingle`
4. *Impact function* = *placeholder*
5. JSON exportado
6. JSON contém campo `status`
7. Dados FIRMS gerados
8. Coordenadas REDUC consistentes com NB01-NB03

---

## Como executar no Google Colab

1. Acesse https://colab.research.google.com
2. Faça *upload* do arquivo `CLIMARISK_OG_NB06.ipynb`
3. Execute célula por célula com Shift+Enter
4. Se o Bloco 6 falhar (dependência GDAL), o Bloco 6B assume automaticamente

**Tempo estimado**: ~5-8 minutos (instalação + geração de dados + cálculo)

**Possível problema**: o módulo `WildFire` pode exigir GDAL funcional. No Colab, geralmente funciona, mas se não funcionar, o *fallback* garante que o *notebook* completa sem erros.

---

## O que este *notebook* prova (para o TRL5)

| Evidência TRL5 | Atendido por |
|:---|:---|
| *Notebooks* versionados | Este *notebook*, commitado no Git |
| *Pipeline* de ingestão de dados | Bloco 5 (FIRMS/MODIS sintéticos) |
| *Outputs* de referência (EAI) | Blocos 8-10 |
| Registro de limitações | Bloco 10 |
| Motor CLIMADA funcional | Todos os blocos |
| **Capacidade multi-*hazard* (3+ *hazards*)** | **NB01 (inundação) + NB02 (calor) + NB06 (*wildfire*)** |
| **Uso de módulo nativo `climada_petals`** | **Bloco 6 (`WildFire.from_hist_fire_seasons_FIRMS`)** |

A contribuição única deste *notebook*: demonstra capacidade com **3 *hazards* terrestres distintos**, usando **módulo nativo** do `climada_petals` (não reconstrução manual), com dados no formato padrão FIRMS/MODIS.

---

## Artefatos gerados

| Arquivo | Descrição | Evidência TRL5 |
|:---|:---|:---|
| `nb06_impact_function_wf.png` | Curva MDR *placeholder* com badge de status | Transparência metodológica |
| `nb06_wildfire_panel.png` | Painel 4 gráficos (mapa, focos/ano, distribuição, impacto) | *Output* de referência |
| `results_nb06_wildfire_reduc.json` | Dados para o *backend* com `status: placeholder` | Integração com plataforma |

---

## Compatibilidade com *notebooks* anteriores e preparação para NB03 expandido

1. **Mesmo ativo** — permite comparação direta (inundação vs. calor vs. incêndio)
2. **Mesmo *schema* JSON** — o *backend* consome com o mesmo *parser*
3. **Mesma *bounding box*** — sobrepõe no mesmo mapa quando atualizarmos o NB03
4. **Campo `status` no JSON** — o *frontend* pode sinalizar resultados provisórios
5. **Campo `pending_references`** — rastreia o que falta para a Etapa 2B

---

## Próximos passos após este *notebook*

1. **Etapa 2B**: Pesquisar literatura e construir *impact function* definitiva para *WildFire* — substituir *placeholder* com curva MDR cientificamente fundamentada (SFPE, API RP 752/753, Christou & Mattarelli, ARIA/BARPI). Esforço estimado: 1 sessão dedicada.
2. **Commitar no GitHub** (`notebooks/CLIMARISK_OG_NB06.ipynb` + `GUIA_NOTEBOOK_06.md`) — modelo recomendado: Sonnet
3. **Etapa 2C**: NB07 *Drought* (seca/escassez hídrica) — módulo `Drought` do `climada_petals`
4. **Atualizar NB03**: incluir WF como terceiro *hazard* no *multi-hazard*
5. **Atualizar *seed data***: adicionar WF ao JSON consolidado do R2
