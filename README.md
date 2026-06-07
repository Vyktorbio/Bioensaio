# 🧫 BioEnsaio — Estatística inteligente para bioensaios

App que **detecta o tipo de dado e escolhe sozinho a análise estatística adequada**,
cobrindo os principais delineamentos de laboratório, casa de vegetação e campo com
insetos, fungos e plantas. Todos os cálculos rodam **no próprio aparelho** (offline),
usando o ecossistema científico do Python (numpy/scipy/statsmodels) dentro do navegador
via **Pyodide**.

---

## O que ele faz

### Motor de decisão (escolhe a fórmula automaticamente)
O app inspeciona a resposta e o delineamento e decide a análise:

| Tipo de dado | Como é reconhecido | Análise escolhida |
|---|---|---|
| **Binário** (vivo/morto, presença/ausência) | texto morto/vivo, sim/não, 0/1 | GLM binomial (logístico) |
| **Dose-resposta** (mortalidade × dose) | resposta binária + coluna de dose | **Probit / Logit** (escolhe a ligação por AIC) |
| **Proporção / contagem** (x de n) | coluna n total | GLM binomial; escala quase-binomial se sobredisperso |
| **Severidade (%)** | nome sugere % e valores 0–100 | ANOVA (proporção) + comparação de médias |
| **Contagem** (nº colônias/insetos) | inteiros ≥ 0, variância ≈ média | **Poisson → Binomial Negativa** se sobredisperso |
| **Contínua** (diâmetro, peso, crescimento) | medidas reais | **ANOVA** (após checar pressupostos) |

A decisão usa **outros testes para decidir**: normalidade (Shapiro-Wilk), homogeneidade
(Levene), índice de dispersão (var/média), e o nome/escala da variável. Quando os
pressupostos da ANOVA falham, tenta **transformação** (arcsen√, √(x+3/8), log) e, se ainda
falhar, indica via **não-paramétrica** (Kruskal-Wallis + Dunn).

### Dose-resposta (estilo PoloPlus, e além)
- Ajuste **probit e logit** por máxima verossimilhança (escolhe o de menor AIC)
- **CL/DL10, 25, 50, 90, 95, 99** com **intervalo de confiança por teorema de Fieller**
- **Correção de Abbott** para mortalidade natural (controle), e modelo de mortalidade
  natural estimada (Finney)
- **Qui-quadrado de aderência** e **fator de heterogeneidade (h)** — quando h > 1, o IC
  passa a usar a distribuição t (como o PoloPlus)
- Inclinação (slope) ± erro-padrão e gráfico da curva sigmoide com a CL50 marcada
- **CL/DL personalizada** (escolha quais níveis: CL80, CL95, CL99…) e nível de confiança
- **Razão de potência / resistência** entre produtos ou populações: RR = CL50ᵢ/CL50ref com IC
  (método delta) — referência = menor CL50 (mais sensível); RR&nbsp;&gt;&nbsp;1 = mais resistente
- **Teste de paralelismo** (razão de verossimilhança: slope comum × separado) e teste de
  diferença de potência entre as curvas
- **Unidade da dose** configurável (ppm, L/ha, g/ha, mg/ha…) exibida na CL50, na tabela e no eixo

### Módulo "Mortalidade no tempo" (sobrevivência) — aba própria
Para ensaios de mortalidade/eficácia ao longo do tempo (colunas N_total e N_vivos por
tratamento, repetição e tempo). Espelha um pipeline de bioensaio de campo/laboratório:
- **Mortalidade %** a partir das contagens; **correção de controle** automática:
  Abbott / Schneider-Orelli quando a base inicial é uniforme, **Henderson-Tilton** quando não é
- **Letras de comparação por tempo** (Scott-Knott se nº de tratamentos > limiar, senão Tukey;
  Kruskal-Wallis + Dunn se violar pressupostos)
- **Rankings** de produtos (média no tempo e tempo final) de mortalidade e eficácia
- **Kaplan-Meier**: curvas de sobrevivência, **LT50/LT90** (tempo letal, interpolado) e **log-rank**
- **QA/QC**: mortalidade do controle (limite/estabilidade), monotonicidade (vivos não podem
  aumentar), duplicatas e valores impossíveis
- **Modelos**: GLM binomial Trat×Tempo com **erro-padrão robusto por cluster** (≈ GLMM) e
  **beta-regressão** da eficácia

### Comparação de médias (letras)
- **Tukey HSD** (compact letter display — letras a, b, c…)
- **Scott-Knott** (agrupamento por razão de verossimilhança, sem ambiguidade de letras)
- **Dunn** (não-paramétrico) quando indicado
- Validado numericamente (a CL50 do dataset clássico de Bliss bate com a literatura)

### Sempre mostra "tudo"
Detecção e justificativa da decisão, estatística descritiva (média, DP, EP, CV%, mín/máx),
diagnósticos, tabela da ANOVA / parâmetros do GLM, doses letais, letras de comparação e
gráficos. Exporta por **Imprimir → PDF** e **Copiar relatório**.

### Calculadoras em projeto separado
As calculadoras de laboratório e campo foram separadas do BioEnsaio. Elas agora ficam no
repositório **BioCalculo**:

https://github.com/Vyktorbio/BioCalculo

---

## Como usar agora (navegador / instalar no Android)

1. Sirva a pasta `www/` (qualquer servidor estático). Exemplo:
   ```bash
   cd www && python3 -m http.server 8000
   ```
2. Abra `http://SEU_IP:8000` no navegador do Android (Chrome).
3. Menu ⋮ → **"Adicionar à tela inicial"**. Vira um app com ícone, em tela cheia.
4. **Offline:** abra o app uma vez **com internet** (ele baixa e guarda as bibliotecas no
   aparelho via service worker). Depois funciona **sem internet** — ideal para o campo.

Entrada de dados: **colar** do Excel/Sheets, **importar** `.xlsx/.csv`, ou **digitar** na
grade. O app adivinha os papéis das colunas (resposta, dose, fator, bloco, n) e deixa você
ajustar.

---

## Gerar o aplicativo Android (.apk)

Veja **`BUILD_APK.md`** para os três caminhos:
1. **PWABuilder** (sem instalar nada — recomendado para um APK rápido)
2. **Capacitor** (controle total; precisa de Node + Android SDK + JDK)
3. **Script automatizado** `build_apk.sh`

---

## Estrutura

```
bioestat/
├── bioengine/        # motor estatístico (Python puro; roda aqui e no Pyodide)
│   ├── detect.py         detecção de tipo de dado e desenho
│   ├── diagnostics.py    normalidade, homogeneidade, sobredispersão
│   ├── doseresponse.py   probit/logit, CL50, Fieller, Abbott, qui²
│   ├── anova.py          ANOVA + transformações + Kruskal
│   ├── posthoc.py        Tukey, Scott-Knott, Dunn (letras)
│   ├── glmcount.py       GLM Poisson/NB/binomial para tratamentos
│   └── decide.py         orquestrador (o "cérebro")
├── tests/validate.py # validação contra dados conhecidos (8 testes)
├── www/              # app web (PWA)
│   ├── index.html  styles.css  app.js  exemplos.js
│   ├── manifest.webmanifest  sw.js  icons/
│   └── bioengine/    # cópia do motor servida ao Pyodide
└── capacitor/        # scaffold para empacotar como APK
```

## Validar o motor (no computador)
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install numpy scipy pandas statsmodels patsy
python tests/validate.py
```

## Notas estatísticas
- **Scott-Knott** usa uma variância global e é, por construção, mais conservador nas
  divisões finais que o Tukey — por isso os dois são exibidos lado a lado.
- A escolha probit×logit é por **AIC**; a CL50 é reportada na escala original da dose
  (o ajuste é feito em log₁₀ por padrão).
