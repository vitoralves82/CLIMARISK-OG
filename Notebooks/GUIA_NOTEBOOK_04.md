# GUIA EXPLICATIVO -- Notebook 04: Projecoes Climaticas SSP

## Para que serve este *notebook*?

Este *notebook* completa a evidencia de **multicenario e multihorizonte** exigida para TRL5 do projeto CLIMARISK-OG. Enquanto os NB01-NB03 demonstram o ciclo H x E x V para o cenario *baseline* (clima atual), o NB04 projeta como o risco climatico evolui ao longo do seculo sob diferentes trajetorias de emissoes.

**Pergunta central**: *Quanto o risco financeiro da REDUC vai aumentar ate 2030, 2050 e 2100 sob cenarios SSP2-4.5 e SSP5-8.5?*

---

## Explicacao Bloco a Bloco

### Bloco 1 -- Instalacao do CLIMADA
Mesmo procedimento dos notebooks anteriores. Instala CLIMADA v6.1.0 + `climada_petals`.

### Bloco 2 -- *Imports*
Carrega as classes CLIMADA padrao mais `copy` (para clonar *hazards*) e `flood_imp_func_set` do `climada_petals` (curva JRC oficial).

### Bloco 3 -- Ativo e *Exposure*
**Identico aos NB01/NB02/NB03**. Mesma REDUC, mesmo valor, mesmas coordenadas, mesma grade de centroids. Isso garante comparabilidade direta entre todos os notebooks.

### Bloco 4 -- *Impact Functions* (V)
Carrega as **mesmas duas funcoes de dano** dos notebooks anteriores:

1. **Inundacao (RF)**: JRC *Global flood depth-damage*, America do Sul -- via `climada_petals` (nao reconstruida manualmente, conforme decisao da Sessao 3)
2. **Calor (HW)**: Customizada para infraestrutura industrial (refinaria), baseada em ECA/McKinsey (2009), Kjellstrom et al. (2016), ILO (2019)

### Bloco 5 -- *Hazards Baseline*
Reconstroi os *hazards* sinteticos dos NB01 e NB02 com a **mesma *seed* (42)** para reprodutibilidade. Estes sao os *hazards* do "clima atual" sobre os quais as projecoes serao aplicadas.

### Bloco 6 -- Impacto *Baseline* (verificacao)
Roda o calculo H x E x V com os *hazards baseline* para verificar que os valores de EAI conferem com os notebooks anteriores. Serve como *sanity check* antes de aplicar as projecoes.

### Bloco 7 -- Fatores de Escala Climatica (IPCC AR6) -- **O BLOCO MAIS IMPORTANTE**

Este bloco define **como** o clima futuro afeta os *hazards*. A logica:

**Conceito geral**: O aquecimento global muda a intensidade e frequencia dos eventos extremos. Para esta versao TRL5, modelamos apenas mudancas de **intensidade** (abordagem conservadora).

**Para inundacao fluvial**:
- A relacao de Clausius-Clapeyron estabelece que a atmosfera retém ~7% mais umidade por grau de aquecimento
- Combinado com mudancas no escoamento, adotamos 10% de aumento na profundidade de inundacao por grau_C
- Fator multiplicativo: `intensidade_futura = intensidade_baseline x (1 + 0.10 x deltaT_global)`

**Para ondas de calor**:
- O aquecimento medio se soma diretamente ao deltaT dos eventos extremos
- Para o Sudeste do Brasil, o aquecimento regional e ~1.1x o aquecimento global (IPCC AR6 WGI *Atlas*)
- Acrescimo aditivo: `intensidade_futura = intensidade_baseline + deltaT_regional`

**Valores de aquecimento (IPCC AR6 Table SPM.1)**:

| Cenario   | 2030    | 2050    | 2100    |
|-----------|---------|---------|---------|
| SSP2-4.5  | +1.5 C  | +2.0 C  | +2.7 C  |
| SSP5-8.5  | +1.6 C  | +2.4 C  | +4.4 C  |

O aquecimento adicional (acima do *baseline* de ~1.1 C em 2020) e o que importa para o *scaling*.

### Bloco 8 -- *Loop* Principal de Projecoes
Para cada uma das 6 combinacoes (2 cenarios x 3 horizontes):
1. Clona o *hazard baseline* com `deepcopy`
2. Aplica o fator de escala sobre a matriz de intensidades
3. Roda `ImpactCalc` com a *Exposure* e *ImpactFuncSet* originais
4. Armazena EAI, impactos por periodo de retorno e fatores usados

### Bloco 9 -- Tabela Resumo
Exibe a matriz completa de resultados em formato tabular, incluindo variacao percentual vs *baseline*. Este e o artefato principal para comunicacao com a Petrobras.

### Bloco 10 -- Graficos Comparativos
Quatro paineis:
1. **Barras agrupadas**: EAI total por cenario e horizonte
2. **Barras empilhadas**: Composicao RF + HW ao longo do tempo (SSP5-8.5)
3. **Linhas**: Variacao percentual vs *baseline*
4. ***Heatmap***: Matriz cenario x horizonte com valores de EAI

### Bloco 11 -- Diagnostico
Verificacoes automaticas:
- **Monotonia**: EAI deve crescer com o horizonte (mais aquecimento = mais risco)
- **Ordenacao**: SSP5-8.5 >= SSP2-4.5 em todos os horizontes
- **Teto**: Nenhum EAI total excede o valor do ativo

### Bloco 12 -- Limitacoes Documentadas
10 limitacoes explicitas -- requisito TRL5. As mais relevantes:
- Fatores de escala globais (nao *downscaling* regional com CORDEX)
- Apenas mudancas de intensidade (nao frequencia)
- *Compound events* nao modelados
- Dados sinteticos (nao observacionais)

### Bloco 13 -- Exportacao JSON
*Schema* compativel com NB01-NB03, acrescido das dimensoes cenario/horizonte. O *backend* consegue parsear usando o mesmo parser, acessando os campos aninhados em `projections[ssp][horizonte]`.

### Bloco 14 -- Resumo Executivo
Consolidacao de todos os resultados com checklist TRL5.

---

## O que os cenarios SSP significam

**SSP2-4.5** ("*Middle of the Road*"): Progresso moderado em sustentabilidade, politicas climaticas intermediarias. Forcamento radiativo de 4.5 W/m2 em 2100. Aquecimento de ~2.7 C. **Este e o cenario considerado mais provavel segundo politicas atuais.**

**SSP5-8.5** ("Desenvolvimento fossilizado"): Crescimento economico baseado em combustiveis fosseis, sem politicas climaticas significativas. Forcamento de 8.5 W/m2. Aquecimento de ~4.4 C. **Cenario de estresse -- util para *stress testing* financeiro (TCFD/ISSB).**

---

## Nota tecnica: por que *scaling factors* e nao dados CMIP6 diretos?

Para TRL5, a abordagem de *scaling factors* e adequada e defensavel porque:

1. **Transparencia**: Os fatores sao derivados diretamente de fontes publicadas (IPCC AR6)
2. **Reproducibilidade**: Qualquer auditor pode replicar os calculos
3. **Eficiencia**: Nao exige download e processamento de terabytes de dados CMIP6
4. **Conservadorismo**: Captura a direcao e magnitude correta da mudanca

Para TRL7+, a abordagem sera substituida por *downscaling* regional usando dados CORDEX *South America* e Eta-INPE, conforme previsto no Plano de Trabalho v4.13.

---

## Como executar no Google Colab

1. Acesse https://colab.research.google.com
2. Faca *upload* do arquivo `nb04_ssp_projections_duque_caxias.ipynb`
3. Execute celula por celula com Shift+Enter
4. Os graficos aparecerao *inline*; o JSON sera salvo no diretorio do Colab

**Tempo estimado**: ~5 minutos (instalacao + calculo)

---

## O que este *notebook* prova (para o TRL5)

Conforme Plano de Trabalho v4.13, secao 6.4:

| Evidencia TRL5 | Atendido por |
|---|---|
| Projecoes climaticas SSP | Cenarios SSP2-4.5 e SSP5-8.5 |
| Multiplos horizontes temporais | 2030, 2050, 2100 |
| Fatores baseados em literatura | IPCC AR6 WG1 (Clausius-Clapeyron) |
| Multi-hazard futuro | Inundacao + Calor projetados |
| Limitacoes documentadas | 10 itens explicitos |
| JSON para *backend* | Schema compativel com NB01-NB03 |

---

## Mapa geral de notebooks para TRL5

| Notebook | Status | Evidencia |
|:---|:---:|:---|
| NB01 - Inundacao | COMITADO | Ciclo H x E x V, hazard terrestre |
| NB02 - Calor | COMITADO | Segundo hazard, impact function customizada |
| NB03 - Multi-hazard | COMITADO | Capacidade multirisco, agregacao |
| **NB04 - Projecoes SSP** | **ESTE NOTEBOOK** | **Multicenario, multihorizonte** |
| NB05 - Batch/Pipeline | PENDENTE | Script de producao para Railway |

---

## Proximos passos apos este *notebook*

1. **Rodar no Colab** e verificar resultados
2. **Commitar no GitHub** via Claude Code
3. **NB05**: Script de producao (*batch job*) para Railway -- consolida NB01-NB04 em pipeline automatizado
4. **Expandir para mais ativos** (alem da REDUC)
5. **Substituir *scaling factors* por CORDEX/Eta-INPE** quando disponivel (TRL7+)
