# GUIA EXPLICATIVO — Notebook 05: Batch Pipeline para Railway

## Para que serve este *notebook*?

Este *notebook* é a **quinta e última evidência técnica de TRL5** do projeto CLIMARISK-OG. Enquanto os NB01-NB04 demonstraram cada componente individualmente (*hazard*, *multi-hazard*, projeções SSP), este NB05 consolida toda a lógica em um **pipeline único e automatizado** — provando que o motor CLIMADA pode rodar como *batch job* em produção.

**Em termos simples**: este *notebook* é a versão "de produção" dos *notebooks* anteriores. Em vez de rodar célula por célula no Colab, ele executa tudo em sequência, gera um JSON consolidado por ativo e faz *upload* dos resultados para o Cloudflare R2 (o armazenamento de objetos do projeto).

---

## Por que um *batch pipeline* é necessário?

A arquitetura do CLIMARISK-OG é **pré-calculada**: o CLIMADA roda em *batch* (agendado ou sob demanda), grava os resultados no R2, e o *frontend* consome dados já prontos via API REST. Isso significa que:

1. O *frontend* nunca roda CLIMADA diretamente — seria lento demais para uma interface web
2. Os resultados ficam disponíveis instantaneamente para qualquer consulta
3. Novos ativos ou cenários são adicionados re-executando o *pipeline*
4. O *backend* no Railway executa este *script* como um *cron job* ou como *job* disparado manualmente

---

## Explicação Bloco a Bloco

### Bloco 0 — Instalação
Instala CLIMADA, `climada_petals` e `boto3` (cliente S3 para Cloudflare R2). Em produção no Railway, esses pacotes já estão no *container* Docker (via `requirements.txt`). No Colab, precisa instalar.

### Bloco 1 — Verificação de Ambiente
Confirma que CLIMADA está instalado e verifica se `boto3` está disponível. Se não estiver, o *pipeline* continua em modo local (salva JSONs localmente mas não faz *upload* ao R2). Usa `importlib.metadata.version()` como *fallback* (padrão desde o NB01).

### Bloco 2 — *Imports* e Configuração
Carrega todas as dependências e lê variáveis de ambiente:

| Variável | Fonte no Railway | Valor padrão (Colab) |
|:---|:---|:---|
| `R2_ENDPOINT` | *Environment variable* | URL do R2 |
| `S3_BUCKET_NAME` | *Environment variable* | `climarisk-og` |
| `R2_ACCESS_KEY_ID` | *Secret* | (vazio — modo local) |
| `R2_SECRET_ACCESS_KEY` | *Secret* | (vazio — modo local) |
| `OUTPUT_DIR` | *Environment variable* | `./outputs` |

**Conceito-chave**: quando `R2_ACCESS_KEY_ID` está vazio, o *pipeline* funciona normalmente mas simula o *upload* (imprime o caminho que seria usado). Isso permite testar no Colab sem credenciais.

### Bloco 3 — Registro de Ativos
Define a lista de ativos a processar. Para TRL5, temos apenas a REDUC. Em produção (TRL7+), esta lista virá de um banco de dados ou JSON de configuração com os 45 ativos do contrato Petrobras.

Cada ativo define:
- Coordenadas e valor de exposição
- *Bounding box* para a grade de *centroids*
- Lista de *hazards* aplicáveis (`RF`, `HW`)

Também define os cenários SSP e horizontes temporais. Os fatores de escala são os mesmos calibrados no NB04:

| Cenário | *Hazard* | 2030 | 2050 | 2100 |
|:---|:---|:---:|:---:|:---:|
| SSP2-4.5 | Inundação (fator ×) | 1.05 | 1.12 | 1.25 |
| SSP2-4.5 | Calor (ΔT offset °C) | +0.5 | +1.2 | +1.8 |
| SSP5-8.5 | Inundação (fator ×) | 1.08 | 1.22 | 1.55 |
| SSP5-8.5 | Calor (ΔT offset °C) | +0.7 | +1.8 | +3.5 |

### Bloco 4 — Funções Auxiliares
Encapsula em funções reutilizáveis toda a lógica que nos NB01-NB04 estava distribuída em múltiplas células:

- `build_centroids()` — grade 20×20 a partir de *bounding box*
- `build_exposure()` — *Exposure* multi-*hazard* com detecção automática do ID JRC via `climada_petals`
- `build_flood_hazard()` — *hazard* de inundação idêntico ao NB01, com parâmetro `scale_factor` para projeções
- `build_heat_hazard()` — *hazard* de calor idêntico ao NB02, com parâmetro `delta_offset` para projeções
- `build_impact_func_set()` — *ImpactFuncSet* unificado idêntico ao NB03

**Decisão de *design***: todas essas funções usam exatamente os mesmos parâmetros e lógica dos *notebooks* originais. Nenhum valor foi alterado. Isso garante que os resultados do *pipeline* sejam reprodutíveis e comparáveis com os *notebooks* individuais.

### Bloco 5 — Funções de Cálculo
Define as funções que orquestram o cálculo de impacto:

- `compute_impact_single()` — calcula impacto para um *hazard*, retorna dicionário com EAI e impactos por período de retorno
- `run_baseline()` — executa análise *baseline* (equivalente ao NB03)
- `run_ssp_projection()` — executa análise sob cenário SSP para um horizonte (equivalente ao NB04)

### Bloco 6 — *Upload* ao R2
Função que faz *upload* via protocolo S3 (*compatible*) para o Cloudflare R2. Se as credenciais não estão configuradas, o *upload* é simulado (apenas imprime o caminho). Isso permite que o mesmo código rode tanto no Colab (sem R2) quanto no Railway (com R2).

### Bloco 7 — Execução do *Pipeline*
O bloco principal. Para cada ativo na lista:

1. Constrói *centroids*, *Exposure* e *ImpactFuncSet*
2. Executa análise *baseline* (inundação + calor agregados)
3. Itera por todos os cenários SSP × horizontes (2×3 = 6 projeções)
4. Calcula o delta percentual de cada projeção vs. *baseline*
5. Monta JSON consolidado com toda a informação
6. Salva localmente e faz *upload* ao R2

O JSON de saída contém tudo que o *backend*/frontend precisa para qualquer visualização:

```
{
  "metadata": { ... },
  "asset": { ... },
  "baseline": {
    "hazards": {
      "RF": { "results": { "eai_usd": ..., "impact_by_return_period": {...} } },
      "HW": { "results": { ... } }
    },
    "aggregated": { "eai_total_usd": ... }
  },
  "projections": [
    { "scenario": "SSP2-4.5", "horizon": "2030", ... },
    { "scenario": "SSP2-4.5", "horizon": "2050", ... },
    ...
  ]
}
```

### Bloco 8 — Sumário de Resultados
Imprime uma tabela resumo com todos os cenários processados, mostrando EAI, ratio e delta percentual vs. *baseline*. Útil para validação rápida dos resultados sem precisar abrir o JSON.

### Bloco 9 — Resumo Executivo
Consolida os resultados em formato legível, destacando o cenário mais severo e o mais brando. Inclui limitações documentadas (requisito TRL5).

### Bloco 10 — Diagnóstico e Artefatos
Executa *checks* de consistência:

1. *Pipeline* executou sem erros
2. EAI *baseline* > 0
3. Todas as projeções com EAI > 0
4. JSONs existem e são válidos
5. Cenário SSP5-8.5 2100 > *baseline* (sanidade — o futuro deve ser pior)

---

## Como executar no Google Colab

1. Acesse https://colab.research.google.com
2. Faça *upload* do arquivo `nb05_batch_pipeline.ipynb`
3. Execute célula por célula com Shift+Enter
4. Os resultados aparecerão no diretório `./outputs`

**Tempo estimado**: ~5 minutos na primeira execução (instalação + 7 cálculos de impacto: 1 *baseline* + 6 projeções)

**Diferença dos NB01-NB04**: este *notebook* não gera gráficos — o foco é na geração de dados para o *backend*. Visualizações são responsabilidade do *frontend*.

---

## Como executar no Railway

Em produção, este *notebook* é convertido em *script* Python (`pipeline.py`) e executado como *batch job*:

```bash
# No Dockerfile ou como cron job no Railway
python pipeline.py
```

As variáveis de ambiente no Railway fornecem as credenciais do R2 automaticamente. O *script* gera JSONs, faz *upload*, e encerra.

Para converter o *notebook* em *script*:
```bash
jupyter nbconvert --to script nb05_batch_pipeline.ipynb --output pipeline
```

---

## O que este *notebook* prova (para o TRL5)

Conforme Plano de Trabalho v4.13, seção 6.4:

| Evidência TRL5 | Atendido por |
|---|---|
| *Notebooks* versionados | Este *notebook*, commitado no Git |
| *Pipeline* de ingestão de dados | Blocos 3-7 (dados processados em *batch*) |
| *Outputs* de referência (EAI, curvas) | JSON consolidado |
| Registro de limitações | Bloco 9 |
| Motor CLIMADA funcional | Todos os blocos |
| Capacidade *multi-hazard* | Inundação + calor no mesmo *pipeline* |
| Capacidade *multi-cenário* | SSP2-4.5 e SSP5-8.5 |
| Capacidade *multi-horizonte* | 2030, 2050, 2100 |
| **Script de produção** | **Pipeline automatizado para Railway** |

A contribuição única deste *notebook*: ao encapsular toda a lógica dos NB01-NB04 em funções reutilizáveis e executar como *pipeline* automatizado, demonstramos que a plataforma **está pronta para operação em ambiente de produção** — não é apenas um conjunto de *notebooks* acadêmicos.

---

## Artefatos gerados

| Arquivo | Descrição | Evidência TRL5 |
|:---|:---|:---|
| `results_pipeline_reduc.json` | JSON consolidado (*baseline* + projeções) | *Output* de referência |

Em produção com múltiplos ativos, serão gerados um JSON por ativo: `results_pipeline_reduc.json`, `results_pipeline_repar.json`, etc.

---

## Compatibilidade com os notebooks anteriores

| *Notebook* | Relação com o NB05 |
|:---|:---|
| NB01 | `build_flood_hazard()` replica exatamente a lógica do NB01 |
| NB02 | `build_heat_hazard()` replica exatamente a lógica do NB02 |
| NB03 | `run_baseline()` combina os *hazards* como no NB03 |
| NB04 | `run_ssp_projection()` aplica fatores de escala como no NB04 |

Os resultados do NB05 devem ser **numericamente idênticos** aos dos *notebooks* individuais quando executados com os mesmos parâmetros.

---

## Próximos passos após este *notebook*

1. **Commitar no GitHub** (`notebooks/nb05_batch_pipeline.ipynb`) — com data rastreável
2. **Converter em `pipeline.py`** — via `nbconvert` para execução no Railway
3. **Configurar credenciais R2** — gerar *API keys* S3-*compatible* no Cloudflare
4. **Configurar *cron job*** no Railway — execução periódica (semanal ou sob demanda)
5. **Conectar ao *backend*** — API REST consome JSONs do R2 e serve ao *frontend*
