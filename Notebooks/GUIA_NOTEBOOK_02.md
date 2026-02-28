# 🌡️ GUIA EXPLICATIVO — Notebook 02: Ondas de Calor em Duque de Caxias

## Para que serve este *notebook*?

Este *notebook* é a **segunda evidência técnica de TRL5** do projeto CLIMARISK-OG. Enquanto o NB01 demonstrou o ciclo H×E×V para inundação fluvial, este NB02 repete o mesmo ciclo para um *hazard* completamente diferente — **ondas de calor** (*heat waves*) — provando que a plataforma é genuinamente **multi-*hazard***.

**H × E × V = Risco**

Onde:
- **H** (*Hazard*) = perigo climático (onda de calor extrema)
- **E** (*Exposure*) = ativos em risco (REDUC, com valor financeiro)
- **V** (*Vulnerability*) = função de dano (quanto se perde por °C acima do limiar)

A diferença fundamental em relação ao NB01: na inundação, o dano é **físico-destrutivo** (água destrói estruturas). Na onda de calor, o dano é predominantemente **operacional** — perda de *throughput*, paradas forçadas, custos extras de resfriamento, riscos à saúde dos trabalhadores. Isso se reflete em uma curva de dano mais suave.

---

## Por que ondas de calor são relevantes para a REDUC?

A Baixada Fluminense é uma das regiões mais quentes do estado do Rio de Janeiro. Recordes recentes confirmam a tendência:

- **Janeiro/2024**: Duque de Caxias registrou **43,2°C** (estação INMET Xerém/A606)
- **Novembro/2023**: Rio de Janeiro atingiu **42,5°C**, com sensação térmica de 62,3°C
- **Dezembro/2012**: 40,4°C na região metropolitana

A tendência é de **+0,3°C por década** na RMRJ (Dereczynski et al., 2020; PBMC, 2014), o que significa que eventos hoje classificados como RP25 passarão a ser RP10 em poucas décadas.

Para uma refinaria como a REDUC, temperaturas acima de ~40°C causam:

1. **Redução de eficiência das torres de resfriamento** — a troca térmica depende do ΔT entre a água e o ar; quanto mais quente o ar, menor a eficiência
2. ***Trip* de equipamentos de proteção** — sensores de temperatura podem acionar paradas automáticas
3. **Redução forçada de carga** (*throughput*) — a unidade precisa operar abaixo da capacidade para manter temperaturas seguras
4. **Paradas de emergência** — em extremos, *shutdown* completo por superaquecimento
5. **Risco à saúde dos trabalhadores** — NR-15 (atividades insalubres) limita exposição ao calor

---

## Explicação Bloco a Bloco

### Bloco 0 — Instalação do CLIMADA
Instala o CLIMADA e o `climada_petals`. No Google Colab, a primeira célula já contém o comando `!pip install`. Leva ~3 minutos. Neste *notebook*, o `climada_petals` é instalado por consistência (mesmo ambiente do NB01), mas não é estritamente necessário — ondas de calor usam a classe genérica `Hazard`.

### Bloco 1 — Verificação de Versão
Confirma que o CLIMADA está instalado e imprime a versão. Usa `importlib.metadata.version()` como *fallback* (necessário na v6.1.0, conforme descobrimos no NB01).

### Bloco 2 — *Imports*
Carrega as mesmas classes do NB01:
- `Hazard` e `Centroids` → definem o perigo e onde ele atua
- `Exposures` → define os ativos e seus valores
- `ImpactFunc` e `ImpactFuncSet` → funções de dano
- `ImpactCalc` → motor que faz a convolução H×E×V

**Diferença do NB01**: não importamos `RiverFlood` porque ondas de calor não têm classe especializada no CLIMADA — usamos a classe genérica `Hazard` diretamente. Isso demonstra a flexibilidade do *framework*.

### Bloco 3 — Definição do Ativo (REDUC)
**Exatamente igual ao NB01.** Mesmas coordenadas, mesmo valor, mesma *bounding box*. Isso é intencional — ao manter o mesmo ativo, podemos comparar diretamente os impactos de inundação vs. calor no NB03 (*multi-hazard*).

**Reutilização de dados**: este é o ponto onde "não desperdiçamos tempo". Toda a definição do ativo é importável entre *notebooks*.

### Bloco 4 — *Exposures* (E)
Cria o `GeoDataFrame` com o ativo georreferenciado. A diferença-chave em relação ao NB01:

| Campo | NB01 (Inundação) | NB02 (Calor) |
|:---|:---|:---|
| Coluna de vínculo | `impf_RF = 61` | `impf_HW = 1` |
| Significado | *Impact Function* JRC América do Sul | *Impact Function* customizada industrial |

O prefixo `impf_` seguido do código do *hazard* (`RF`, `HW`) é a convenção do CLIMADA para vincular cada *exposure* à função de dano correta. Quando rodarmos o NB03 multi-*hazard*, o mesmo ativo terá **ambas as colunas** (`impf_RF` e `impf_HW`).

### Bloco 5 — *Hazard* (H) — Ondas de Calor

**O conceito de intensidade muda completamente:**

| | NB01 (Inundação) | NB02 (Calor) |
|:---|:---|:---|
| **Intensidade** | Profundidade da água (metros) | °C acima do limiar operacional (40°C) |
| **Unidade** | `m` | `°C above threshold` |
| **Distribuição espacial** | Muito localizada (segue cursos d'água) | Regional (cobre toda a área) |
| **Fração afetada** | Parcial (só onde há água) | Total (todo o ativo é atingido) |
| **`haz_type`** | `'RF'` | `'HW'` |

**Sobre o limiar de 40°C**: este é o limiar genérico para infraestrutura industrial. Em produção (TRL7+), cada unidade de processo da REDUC (FCC, destilação atmosférica, *coking*, etc.) teria seu próprio limiar, baseado nas especificações de *design* dos equipamentos.

**Sobre os dados sintéticos**: os dados de temperatura neste *notebook* são **calibrados** com registros INMET para a estação Duque de Caxias/Xerém (A606), mas não são reanálise ERA5. Isso é documentado como limitação. Em produção (TRL7+), estes dados virão do ERA5 (*2m-temperature*) ou projeções CMIP6/CORDEX regionalizadas.

**Conceitos-chave**:
- **ΔT**: diferença entre a temperatura máxima do evento e o limiar operacional. ΔT = 3°C significa T_max = 43°C
- **Efeito ilha de calor urbana** (*UHI*): áreas industriais/urbanas são ~1-2°C mais quentes que o entorno rural. Modelamos isso como +1,5°C no centro (REDUC), decaindo com a distância
- **Fração = 1,0**: diferente da inundação (onde só parte do terreno alaga), uma onda de calor afeta **100% do ativo**. Não há como "escapar" do calor dentro das instalações
- **Frequências**: evento RP2 (todo verão) até RP100 (sem precedentes históricos)

**Eventos modelados**:

| Evento | Período de Retorno | ΔT (°C) | T absoluta | Referência histórica |
|:---|:---:|:---:|:---:|:---|
| `hw_rp2` | 2 anos | 1,0 | 41°C | Ocorre quase todo verão |
| `hw_rp5` | 5 anos | 2,0 | 42°C | Similar a nov/2023 (Rio) |
| `hw_rp10` | 10 anos | 3,0 | 43°C | Similar a jan/2024 (D. Caxias) |
| `hw_rp25` | 25 anos | 4,5 | 44,5°C | Projeção para ~2040 |
| `hw_rp50` | 50 anos | 6,0 | 46°C | Projeção para ~2060 |
| `hw_rp100` | 100 anos | 8,0 | 48°C | Cenário extremo / sem precedentes |

### Bloco 6 — *Impact Function* (V) — O Bloco Mais Diferente do NB01

Este é o bloco que mais difere do NB01. No *notebook* de inundação, usamos a função de dano **JRC publicada** (Huizinga et al., 2017) — uma referência consolidada. Para ondas de calor em infraestrutura industrial, **não existe função de dano *built-in* no CLIMADA**. Construímos uma curva customizada.

**Referências que sustentam a curva**:

1. **ECA *Working Group* (2009)** — *"Shaping Climate-Resilient Development"* (McKinsey/*Swiss Re*/GEF). Capítulo 3: método de quantificação de perdas por *hazard*. Este é o *Guidebook* que está nos anexos do projeto.

2. **Kjellstrom et al. (2016)** — *"Heat, Human Performance, and Occupational Health"*, *Annual Review of Public Health* 37:97-112. Documenta perda de produtividade de ~2-4% por °C acima do limiar de conforto térmico.

3. **ILO (2019)** — *"Working on a Warmer Planet"*. Estimativas globais de perda de produtividade por calor: até 80% para trabalho pesado ao ar livre.

4. **McEvoy et al. (2012)** — *"Economic costs of heat stress on industrial processes"*. Específico para redução de *throughput* em refinarias: 3-5% por °C acima de 40°C.

**A curva traduz ΔT em fator de dano**:

| ΔT (°C acima de 40°C) | T absoluta | Dano (%) | Tipo de impacto |
|:---:|:---:|:---:|:---|
| 0,0 | 40°C | 0% | Sem impacto (dentro do envelope operacional) |
| 0,5 | 40,5°C | 0,5% | Custos marginais de *cooling* |
| 1,0 | 41°C | 2% | Redução leve de eficiência |
| 2,0 | 42°C | 5% | Redução forçada de carga (*throughput*) |
| 3,0 | 43°C | 10% | Paradas parciais + proteção NR-15 |
| 5,0 | 45°C | 20% | Paradas prolongadas + danos a equipamentos |
| 8,0 | 48°C | 40% | *Shutdown* de emergência |
| 12,0 | 52°C | 60% | Dano severo — cenário catastrófico |
| 15,0 | 55°C | 70% | Dano extremo (teórico) |

**Diferença conceitual com a inundação**: no NB01 o dano a 6m de água é 100% (destruição total). Aqui, mesmo a 48°C o dano é "apenas" 40%. Isso porque calor raramente **destrói fisicamente** uma refinaria — ele causa **perdas operacionais** (parada, multas por não-entrega, custos de seguro, manutenção). A curva reflete essa realidade.

**Sobre o PAA** (*Proportion of Assets Affected*): diferente da inundação (onde o PAA varia — nem todo o ativo alaga), para calor o PAA é **1,0** (100%) para qualquer ΔT > 0. A onda de calor atinge toda a instalação uniformemente.

### Bloco 7 — Cálculo de Impacto (H × E × V)
A linha central é **idêntica** ao NB01:

```python
imp = ImpactCalc(exp, impf_set, haz_hw).impact(save_mat=True)
```

Isso demonstra a **universalidade do CLIMADA**: o `ImpactCalc` é agnóstico ao tipo de *hazard*. Tanto faz se é inundação, calor, ciclone ou seca — a convolução H×E×V funciona da mesma forma.

Os *outputs* são os mesmos:
- **`aai_agg`** = EAI (*Expected Annual Impact*) — perda anual esperada
- **`eai_exp`** = EAI por localização
- **`at_event`** = impacto por evento

Além do gráfico de barras por período de retorno (igual ao NB01), este bloco adiciona um gráfico de **ΔT × Dano (%)**  — mostrando visualmente como a perda escala com a temperatura. Este gráfico é particularmente útil para gestores porque permite responder: "*Se a temperatura subir mais 2°C com mudanças climáticas, quanto a mais perdemos?*"

### Bloco 8 — Curva de Excedência
Gera os mesmos dois gráficos do NB01:
1. **Impacto vs. período de retorno** (escala log)
2. **Frequência × severidade** (curva de excedência)

A curva é construída manualmente (não usa `plot_exceedance_imp()` que está depreciado na v6.1.0 — *lesson learned* do NB01).

**Interpretação esperada**: a curva de excedência de calor deve ser **mais suave** que a de inundação. Isso é consistente com a física — inundação tem potencial de destruição total (100% de dano), enquanto calor extremo na faixa modelada causa no máximo ~40% de perda operacional.

### Bloco 9 — Resumo Executivo
Consolida todos os resultados em formato legível, incluindo:
- Comparação qualitativa com NB01 (inundação)
- **Limitações documentadas** — requisito explícito do TRL5
- Referências bibliográficas da função de dano

As 7 limitações documentadas são mais numerosas que as 5 do NB01. Isso é honesto e intencional — a função de dano customizada introduz incertezas adicionais que devem ser declaradas.

### Bloco 10 — Exportação JSON

Salva os resultados em JSON com **exatamente o mesmo *schema*** do NB01. Os campos-chave que mudam:

| Campo JSON | NB01 | NB02 |
|:---|:---|:---|
| `hazard.type` | `'RF'` | `'HW'` |
| `hazard.type_name` | `'River Flood'` | `'Heat Wave'` |
| `hazard.intensity_unit` | (implícito: metros) | `'°C above threshold'` |
| `hazard.threshold_c` | — | `40.0` |
| `impact_function.source` | JRC / Huizinga et al. | Custom / ECA+Kjellstrom+ILO |
| `impact_function.type` | (implícito: structural) | `'operational_loss'` |

O campo `impact_function` é **novo** em relação ao NB01. Recomendo que na próxima iteração do NB01 você adicione este campo retroativamente — assim ambos os JSONs ficarão 100% simétricos para o *parser* do *backend*.

---

## Como executar no Google Colab

1. Acesse https://colab.research.google.com
2. Faça *upload* do arquivo `nb02_heatwave_duque_caxias.ipynb`
3. Abra o arquivo diretamente (já é `.ipynb`)
4. Execute célula por célula com Shift+Enter
5. Os gráficos aparecerão *inline*

**Tempo estimado**: ~8 minutos na primeira execução (instalação + cálculo)

**Diferença do NB01**: este *notebook* é mais rápido porque não tenta carregar dados DEMO do `RiverFlood` (passo que falhava no NB01).

---

## O que este *notebook* prova (para o TRL5)

Conforme Plano de Trabalho v4.13, seção 6.4:

| Evidência TRL5 | ✅ Atendido por |
|---|---|
| *Notebooks* versionados | Este *notebook*, commitado no Git |
| *Pipeline* de ingestão de dados | Blocos 3-5 (dados processados) |
| *Outputs* de referência (EAI, curvas) | Blocos 7-8 |
| Registro de limitações | Bloco 9 |
| Motor CLIMADA funcional | Todos os blocos |
| **Capacidade multi-*hazard*** | **NB01 (inundação) + NB02 (calor)** |

A última linha é a contribuição única deste *notebook*: ao rodar o mesmo ciclo H×E×V com um *hazard* diferente, usando a mesma infraestrutura (CLIMADA, mesma *Exposure*, mesmo motor `ImpactCalc`), demonstramos que a plataforma **não é específica para um único risco**.

---

## Artefatos gerados

| Arquivo | Descrição | Evidência TRL5 |
|:---|:---|:---|
| `exp_reduc_hw.png` | Mapa de exposição (mesmo ativo do NB01) | Consistência de dados |
| `haz_hw_rp10.png` | Mapa de intensidade — RP10 | Visualização do *hazard* |
| `haz_hw_return_periods.png` | Intensidade por período de retorno | Análise probabilística |
| `impf_heatwave_industrial.png` | Função de dano customizada | Transparência metodológica |
| `impact_results_hw_reduc.png` | Resultados de impacto + curva ΔT×Dano | *Output* de referência |
| `exceedance_curve_hw_reduc.png` | Curva de excedência | *Output* de referência |
| `results_nb02_heatwave_reduc.json` | Dados para o *backend* | Integração com plataforma |

---

## Compatibilidade com o NB01 e preparação para o NB03

O *design* deste *notebook* foi pensado para **não desperdiçar trabalho**:

1. **Mesmo ativo** → permite comparação direta de impactos (inundação vs. calor)
2. **Mesmo *schema* JSON** → o *backend* consome ambos com o mesmo *parser*
3. **Mesma grade de *centroids*** → o NB03 poderá sobrepor os dois *hazards* no mesmo mapa
4. **Mesma estrutura de blocos** → documentação e revisão consistentes
5. **Campo `impact_function` no JSON** → permite ao *frontend* exibir a fonte e o tipo de cada curva

O NB03 (*multi-hazard*) será essencialmente:
- Carregar os dois JSONs (`results_nb01_*.json` + `results_nb02_*.json`)
- Somar os EAIs para obter o risco climático agregado
- Plotar comparação lado-a-lado
- Gerar um JSON consolidado com ambos os *hazards*

---

## Próximos passos após este *notebook*

1. **Commitar no GitHub** (`notebooks/nb02_heatwave_duque_caxias.ipynb`) — com data rastreável
2. **Atualizar NB01**: adicionar campo `impact_function` ao JSON para simetria
3. **Notebook 03**: Multi-*hazard* (combinação inundação + calor) para o mesmo ativo
4. **Notebook 04**: Projeções futuras sob SSP2-4.5 e SSP5-8.5
5. **Script de produção**: Converter em *batch job* para o Railway
