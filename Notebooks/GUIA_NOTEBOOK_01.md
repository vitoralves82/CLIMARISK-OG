# 📘 GUIA EXPLICATIVO — Notebook 01: Inundação em Duque de Caxias

## Para que serve este *notebook*?

Este *notebook* é a **principal evidência técnica de TRL5** do projeto CLIMARISK-OG. Ele demonstra que a EnvironPact consegue executar o ciclo completo de cálculo de risco climático usando o *framework* CLIMADA:

**H × E × V = Risco**

Onde:
- **H** (*Hazard*) = perigo climático (inundação fluvial)
- **E** (*Exposure*) = ativos em risco (REDUC, com valor financeiro)
- **V** (*Vulnerability*) = função de dano (quanto se perde por nível de água)

---

## Explicação Bloco a Bloco

### Bloco 1 — Instalação do CLIMADA
Instala o CLIMADA e o `climada_petals` (módulos complementares com *hazards* específicos como inundação). No Google Colab, basta descomentar a linha `!pip install`. Leva ~3 minutos.

### Bloco 2 — *Imports*
Carrega as classes principais:
- `Hazard` e `Centroids` → definem o perigo e onde ele atua
- `Exposures` → define os ativos e seus valores
- `ImpactFunc` e `ImpactFuncSet` → funções de dano
- `ImpactCalc` → motor que faz a convolução H×E×V
- `RiverFlood` → classe especializada de inundação fluvial (do `climada_petals`)

### Bloco 3 — Definição do Ativo (REDUC)
Define as coordenadas e o valor de reposição da REDUC. O valor de USD 5 bilhões é uma estimativa conservadora — em produção, virá dos dados reais da Petrobras.

**Por que Duque de Caxias?** A REDUC é um dos 45 ativos priorizados pela Petrobras, e a Baixada Fluminense é uma das regiões mais vulneráveis a inundações no Brasil. É um caso perfeito para demonstrar a capacidade da ferramenta.

### Bloco 4 — *Exposures* (E)
Cria um `GeoDataFrame` com o ativo georreferenciado. O campo `impf_RF = 6` vincula este ativo à função de dano da América do Sul (RF6). Em produção, cada ativo terá sua própria função de dano baseada na tipologia construtiva.

### Bloco 5 — *Hazard* (H) — O Bloco Mais Importante
Dois passos:

1. **Teste do módulo `RiverFlood`**: Verifica se o módulo nativo do CLIMADA funciona carregando dados DEMO (Europa). Isso prova que o *engine* está operacional.

2. **Hazard customizado para Brasil**: Como os dados DEMO cobrem Europa, construímos um *hazard* customizado para a região de Duque de Caxias com 6 eventos de inundação (períodos de retorno de 5 a 250 anos).

**Sobre os dados sintéticos**: Os dados de profundidade de inundação neste notebook são **calibrados** (baseados em registros da ANA e Defesa Civil), mas não são modelagem hidrológica real. Isso é explicitamente documentado como limitação. Em produção (TRL7+), estes dados virão do ISIMIP (dados globais reais) ou de ERA5 processado por modelo hidrológico.

**Conceitos-chave**:
- **Intensidade**: profundidade da água em metros (quanto mais fundo, pior)
- **Frequência**: 1 / período de retorno (evento de 50 anos → frequência 0.02/ano)
- **Centroids**: grade de pontos onde o *hazard* é calculado
- **`csr_matrix`**: formato de matriz esparsa que o CLIMADA usa para eficiência

### Bloco 6 — *Impact Functions* (V)
Carrega as funções de dano do JRC (*Joint Research Centre* da UE), publicadas em Huizinga et al. (2017). Cada continente tem uma curva específica — usamos a **RF6 (América do Sul)**.

A curva traduz profundidade da água em fator de dano:
| Profundidade (m) | Dano (% do valor) |
|:-:|:-:|
| 0.0 | 0% |
| 0.5 | 25% |
| 1.0 | 40% |
| 2.0 | 60% |
| 4.0 | 85% |
| 6.0+ | 100% |

### Bloco 7 — Cálculo de Impacto (H × E × V)
A linha mais importante do notebook inteiro:

```python
imp = ImpactCalc(exp, impf_set, haz_flood).impact(save_mat=True)
```

Esta linha executa o ciclo completo:
1. Para cada evento de inundação...
2. Encontra os *centroids* mais próximos de cada ativo...
3. Lê a intensidade (profundidade) naquele ponto...
4. Aplica a função de dano para obter o fator de perda...
5. Multiplica pelo valor do ativo → impacto em USD

Os *outputs* principais:
- **`aai_agg`** = *Average Annual Impact* = EAI (perda anual esperada total)
- **`eai_exp`** = EAI por localização de exposição
- **`at_event`** = impacto por evento
- **`tot_value`** = valor total exposto

### Bloco 8 — Curva de Excedência
Gera dois gráficos fundamentais:
1. **Impacto por período de retorno**: barras mostrando quanto se perde em cada cenário
2. **Curva de excedência**: mostra a relação perda × probabilidade

A curva de excedência é o gráfico que seguradoras e gestores de risco mais usam. Ela responde à pergunta: "*Qual a perda máxima que posso esperar com X% de probabilidade?*"

### Bloco 9 — Resumo Executivo
Consolida todos os resultados em formato legível, incluindo **limitações documentadas** — requisito explícito do TRL5.

### Bloco 10 — Exportação JSON
Salva os resultados em formato JSON para consumo pela API do *backend* (Railway). Este arquivo será eventualmente gravado no R2 (Cloudflare) para o *frontend* exibir.

---

## Como executar no Google Colab

1. Acesse https://colab.research.google.com
2. Faça *upload* do arquivo `nb01_flood_duque_caxias.py`
3. No Colab, crie um novo *notebook* e copie o conteúdo (ou renomeie para `.ipynb`)
4. Na primeira célula, adicione: `!pip install climada climada-petals --quiet`
5. Execute célula por célula com Shift+Enter
6. Os gráficos aparecerão *inline*

**Tempo estimado**: ~10 minutos na primeira execução (instalação + cálculo)

---

## O que este *notebook* prova (para o TRL5)

Conforme Plano de Trabalho v4.13, seção 6.4:

| Evidência TRL5 | ✅ Atendido por |
|---|---|
| *Notebooks* versionados | Este notebook, commitado no Git |
| Pipeline de ingestão de dados | Blocos 3-5 (dados processados) |
| Outputs de referência (EAI, curvas) | Blocos 7-8 |
| Registro de limitações | Bloco 9 |
| Motor CLIMADA funcional | Todos os blocos |

---

## Próximos passos após este *notebook*

1. **Commitar no GitHub** com data rastreável
2. **Notebook 02**: Ondas de calor (*heat wave*) para o mesmo ativo
3. **Notebook 03**: Multi-*hazard* (combinação inundação + calor)
4. **Notebook 04**: Projeções futuras sob SSP2-4.5 e SSP5-8.5
5. **Script de produção**: Converter em *batch job* para o Railway
