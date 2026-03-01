# GUIA EXPLICATIVO -- Notebook 03: Analise Multi-Hazard (Inundacao + Calor)

## Para que serve este *notebook*?

Este *notebook* e a **terceira evidencia tecnica de TRL5** do projeto CLIMARISK-OG. Ele demonstra que a plataforma consegue analisar **multiplos *hazards* sobre o mesmo ativo**, calcular impactos separadamente e agregar resultados -- provando a capacidade **multirisco** exigida pelo Plano de Trabalho v4.13:

> *"A abordagem e multirisco, multicenario e multihorizonte: cada risco e modelado individualmente [...]"*

Este *notebook* NAO repete o trabalho dos NB01 e NB02. Ele os **integra**: replica os mesmos *hazards* e *impact functions*, mas os executa dentro de uma **unica *Exposure*** com **duas colunas de vinculo** (`impf_RF` e `impf_HW`). Isso demonstra a arquitetura multi-*hazard* do CLIMADA.

---

## O que ha de novo em relacao aos NB01 e NB02?

| Aspecto | NB01/NB02 | NB03 |
|:---|:---|:---|
| *Hazards* | 1 por *notebook* | 2 no mesmo *notebook* |
| *Exposure* | `impf_RF` OU `impf_HW` | `impf_RF` **E** `impf_HW` na mesma linha |
| *ImpactFuncSet* | 1 funcao | 2 funcoes (RF61 + HW1) |
| *Output* JSON | 1 *hazard* por arquivo | Ambos + agregacao |
| Graficos | Individuais | Comparativos lado-a-lado |
| EAI | Por *hazard* | Por *hazard* + **total agregado** |

---

## Explicacao Bloco a Bloco

### Blocos 0-1 -- Instalacao e Verificacao
Identicos aos NB01/NB02. Instalam CLIMADA v6.1.0 e verificam a versao.

### Bloco 2 -- *Imports*
Mesmos *imports* dos *notebooks* anteriores. Nao ha bibliotecas novas -- o CLIMADA ja suporta multi-*hazard* nativamente.

### Bloco 3 -- Definicao do Ativo (REDUC)
Exatamente igual aos NB01/NB02. O ponto importante e a **consistencia**: mesmo ativo, mesmas coordenadas, mesmo valor. Isso garante que a comparacao entre *hazards* e justa.

### Bloco 4 -- *Exposures* Multi-Hazard (E)

**Este e o bloco-chave do NB03.** A *Exposure* agora tem **duas colunas** de vinculo:

```python
'impf_RF': [61],   # vincula a Impact Function de inundacao (JRC)
'impf_HW': [1],    # vincula a Impact Function de calor (customizada)
```

O CLIMADA usa a convencao `impf_` + codigo do *hazard* para saber qual funcao de dano aplicar. Quando o `ImpactCalc` recebe um *Hazard* do tipo `'RF'`, ele procura a coluna `impf_RF` na *Exposure*. Quando recebe `'HW'`, procura `impf_HW`. Isso e o mecanismo que permite calcular multiplos riscos sobre o mesmo ativo.

Em producao (TRL7+), cada ativo do portfolio da Petrobras tera **tantas colunas `impf_` quantos *hazards* forem modelados** (ate 7: RF, HW, LS, WS, DR, WF, OC).

### Bloco 5 -- *Hazard* 1: Inundacao Fluvial (RF)
Replica exata do *hazard* do NB01. Mesmos 6 eventos (RP 5-250a), mesmas intensidades, mesma *seed* de ruido. Isso e intencional -- qualquer diferenca nos resultados indicaria um *bug*.

### Bloco 6 -- *Hazard* 2: Ondas de Calor (HW)
Replica exata do *hazard* do NB02. Mesmos 6 eventos (RP 2-100a), mesmas intensidades, mesma *seed*. Mesma logica de consistencia.

**Nota sobre `units`**: neste *notebook* usamos `'deg_C above threshold'` (sem caractere especial) em vez de `'deg C above threshold'` para evitar o erro de *unicode* que apareceu no NB02. Cosmético, mas evita o `UnicodeEncodeError` do Tornado/Jupyter.

### Bloco 7 -- *Impact Functions* (V)

Cria um **unico `ImpactFuncSet`** contendo **ambas** as funcoes de dano:

1. **RF61**: JRC *Global flood depth-damage* -- South America (Huizinga et al., 2017)
2. **HW1**: *Heat Wave* -- *Industrial Facility* (customizada)

```python
impf_set = ImpactFuncSet([impf_flood, impf_hw])
```

Este bloco tambem gera um grafico comparativo das duas curvas de dano lado-a-lado. A diferenca visual e reveladora:
- **Inundacao**: curva ingreme, atinge 100% de dano a 6m de agua (destruicao total)
- **Calor**: curva suave, atinge 70% de dano a +15 deg_C (perda operacional, nao destruicao)

### Bloco 8 -- Calculo de Impacto

Roda o `ImpactCalc` **duas vezes**, uma para cada *hazard*:

```python
imp_rf = ImpactCalc(exp, impf_set, haz_rf).impact(save_mat=True)
imp_hw = ImpactCalc(exp, impf_set, haz_hw).impact(save_mat=True)
```

O mesmo `ImpactFuncSet` e a mesma `Exposure` sao usados em ambas as chamadas. O CLIMADA resolve automaticamente qual funcao de dano usar baseado no `haz_type` do *Hazard* passado.

A agregacao e por **soma simples**:

```
EAI_total = EAI_inundacao + EAI_calor
```

Isso assume **independencia entre os *hazards*** -- uma limitacao documentada. Em producao, seria necessario modelar correlacoes (ex: sera que anos muito chuvosos tambem sao muito quentes? Provavelmente nao para Duque de Caxias, onde inundacao e associada a chuvas intensas em temperatura moderada, nao a calor).

### Bloco 9 -- Comparacao Visual Multi-Hazard

Gera um painel com 4 graficos:

1. **Pizza de contribuicao**: mostra quanto cada *hazard* contribui para o EAI total
2. **Barras lado-a-lado**: compara impactos por periodo de retorno para os RPs comuns (5, 10, 25, 50, 100 anos)
3. **Curvas de excedencia sobrepostas**: mostra que a inundacao domina em perdas absolutas, mas o calor tem frequencia maior (RP2 = todo verao)
4. **Barras de EAI**: mostra o EAI de cada *hazard* e o total agregado

### Bloco 10 -- Resumo Executivo

Consolida resultados em tabela formatada com:
- EAI por *hazard* (USD e %)
- Contribuicao relativa
- Interpretacao qualitativa
- Referencia cruzada com NB01/NB02
- **8 limitacoes documentadas** (3 a mais que NB01, incluindo a premissa de independencia)

### Bloco 11 -- Exportacao JSON

O *schema* JSON deste *notebook* e diferente dos anteriores -- e uma **evolucao**:

```json
{
  "metadata": { ... },
  "asset": { ... },
  "hazards": {
    "RF": { "results": { ... }, "impact_function": { ... } },
    "HW": { "results": { ... }, "impact_function": { ... } }
  },
  "aggregated_results": {
    "eai_total_usd": ...,
    "contribution_pct": { "RF": ..., "HW": ... },
    "aggregation_method": "simple_sum"
  },
  "limitations": [ ... ]
}
```

O *backend* pode consumir tanto os JSONs individuais (NB01/NB02) quanto o consolidado (NB03). O campo `aggregation_method` documenta que a soma e simples (sem copulas).

---

## Como executar no Google Colab

1. Acesse https://colab.research.google.com
2. Faca *upload* do arquivo `nb03_multihazard_duque_caxias.ipynb`
3. Execute celula por celula com Shift+Enter

**Tempo estimado**: ~10 minutos (instalacao + 2 calculos de impacto)

**IMPORTANTE**: este *notebook* e **autossuficiente** -- nao depende dos JSONs do NB01/NB02. Ele recria ambos os *hazards* do zero. Isso e intencional para reproducibilidade.

---

## O que este *notebook* prova (para o TRL5)

| Evidencia TRL5 | Atendido por |
|---|---|
| *Notebooks* versionados | Este *notebook*, commitado no Git |
| *Pipeline* de ingestao de dados | Blocos 5-6 (dois *hazards* processados) |
| *Outputs* de referencia (EAI, curvas) | Blocos 8-9 |
| Registro de limitacoes | Bloco 10 |
| Motor CLIMADA funcional | Todos os blocos |
| **Capacidade multi-*hazard*** | **Blocos 4, 7, 8, 9 (dois *hazards* no mesmo ativo)** |
| **Agregacao de riscos** | **Bloco 8 (EAI total)** |

---

## Referencia cruzada de valores (para validacao)

O diagnostico (celula final) compara os EAIs obtidos no NB03 com os valores de referencia do NB01 e NB02. Os valores devem ser **identicos** (mesmos *hazards*, mesma *seed*, mesma *Exposure*). Se houver divergencia, indica um *bug*.

| Metrica | NB01 | NB02 | NB03 (esperado) |
|:---|:---:|:---:|:---:|
| EAI Inundacao | ~USD 939M | -- | ~USD 939M |
| EAI Calor | -- | ~USD 542M | ~USD 542M |
| EAI Total | -- | -- | ~USD 1.481M |

---

## Artefatos gerados

| Arquivo | Descricao |
|:---|:---|
| `impf_comparison_multihazard.png` | Funcoes de dano lado-a-lado |
| `multihazard_comparison_reduc.png` | Painel com 4 graficos comparativos |
| `results_nb03_multihazard_reduc.json` | JSON consolidado multi-*hazard* |

---

## Proximos passos apos este *notebook*

1. **Commitar no GitHub** (`notebooks/nb03_multihazard_duque_caxias.ipynb`)
2. **Notebook 04**: Projecoes futuras sob SSP2-4.5 e SSP5-8.5 para horizontes 2030, 2050, 2100
3. **Script de producao**: Converter em *batch job* para o Railway
