"""
Orquestrador de decisão — o "cérebro" do app.

Recebe os dados e os papéis das colunas (resposta, dose, fator(es),
bloco, n_total), DECIDE qual análise é adequada e devolve um relatório
unificado com: detecção, justificativa da decisão, descritiva,
diagnósticos, modelo escolhido e comparação de médias (Tukey + Scott-Knott).

Contrato de entrada
-------------------
analisar(dados, papeis, opcoes)

dados  : dict  coluna -> lista de valores (cru)
papeis : dict  com chaves possíveis:
           "resposta" : nome da coluna (obrigatório)
           "n_total"  : nome da coluna (opcional; dados x de n)
           "dose"     : nome da coluna (opcional)
           "fatores"  : lista de nomes de colunas categóricas (opcional)
           "bloco"    : nome da coluna (opcional)
opcoes : dict  {"alfa":0.05, "log_dose":True, "controle_mort":None}
"""

from __future__ import annotations

import numpy as np

from . import detect, diagnostics as diag, doseresponse, anova as anova_mod, glmcount
from . import posthoc


def _col(dados, nome):
    return dados[nome] if nome and nome in dados else None


def _descritiva(valores, chaves):
    """Estatística descritiva por tratamento."""
    valores = np.asarray(valores, float)
    out = []
    for grp in sorted(set(chaves)):
        v = valores[np.array([c == grp for c in chaves])]
        v = v[~np.isnan(v)]
        if v.size == 0:
            continue
        out.append({
            "tratamento": grp, "n": int(v.size),
            "media": float(np.mean(v)), "dp": float(np.std(v, ddof=1)) if v.size > 1 else 0.0,
            "ep": float(np.std(v, ddof=1) / np.sqrt(v.size)) if v.size > 1 else 0.0,
            "mediana": float(np.median(v)),
            "min": float(np.min(v)), "max": float(np.max(v)),
            "cv": float(100 * np.std(v, ddof=1) / np.mean(v)) if v.size > 1 and np.mean(v) != 0 else None,
        })
    return out


def _dispersao_intra(valores, chaves):
    """Razão variância/média intra-grupo agrupada (índice de dispersão de Poisson).
    ~1 = compatível com contagem; <<1 = subdisperso (medida contínua)."""
    valores = np.asarray(valores, float)
    var_pool, gl, medias = 0.0, 0, []
    for grp in set(chaves):
        v = valores[np.array([c == grp for c in chaves])]
        v = v[~np.isnan(v)]
        if v.size >= 2:
            var_pool += np.sum((v - v.mean()) ** 2)
            gl += v.size - 1
            medias.append(v.mean())
    if gl == 0 or not medias:
        return None
    var_intra = var_pool / gl
    media_ref = float(np.mean(medias))
    return var_intra / media_ref if media_ref > 0 else None


def _chaves_tratamento(dados, fatores):
    """Constrói o rótulo do tratamento (combinação dos fatores)."""
    if not fatores:
        return None
    cols = [[str(v) for v in dados[f]] for f in fatores]
    n = len(cols[0])
    return [" × ".join(c[i] for c in cols) for i in range(n)]


# --------------------------------------------------------------------------- #
def analisar(dados, papeis, opcoes=None):
    opcoes = opcoes or {}
    alfa = float(opcoes.get("alfa", 0.05))
    avisos = []

    resp_col = papeis.get("resposta")
    if not resp_col or resp_col not in dados:
        return {"ok": False, "erro": "Selecione a coluna de resposta."}

    resp = dados[resp_col]
    n_total = _col(dados, papeis.get("n_total"))
    dose = _col(dados, papeis.get("dose"))
    fatores_cols = papeis.get("fatores") or []
    bloco = _col(dados, papeis.get("bloco"))

    # 1) detecção
    rinfo = detect.detectar_resposta(resp, n_total=n_total, nome=resp_col)
    fatores_vals = [dados[f] for f in fatores_cols]
    dinfo = detect.detectar_desenho(dose=dose, fatores=fatores_vals, bloco=bloco)

    chaves = _chaves_tratamento(dados, fatores_cols)

    # 1b) override manual do tipo de resposta (usuário confirma/corrige na interface)
    forcado = papeis.get("tipo_resposta") or opcoes.get("tipo_resposta")
    if forcado and forcado != rinfo["tipo"]:
        avisos.append(f"Tipo de resposta definido manualmente como '{forcado}' "
                      f"(detecção automática sugeria '{rinfo['tipo']}').")
        rinfo["tipo"] = forcado
    elif rinfo["tipo"] == "contagem" and chaves is not None:
        # refino: contagem subdispersa intra-grupo é, na prática, medida contínua
        razao = _dispersao_intra(rinfo["valores"], chaves)
        if razao is not None and razao < 0.4:
            avisos.append("Valores inteiros, mas com variância intra-grupo muito "
                          "menor que a média (subdispersão) → tratados como medida "
                          "CONTÍNUA (ANOVA), não como contagem de Poisson.")
            rinfo["tipo"] = "continua"

    relatorio = {
        "ok": True,
        "deteccao": {
            "resposta": resp_col, "tipo_resposta": rinfo["tipo"],
            "detalhe_resposta": rinfo["detalhe"], "desenho": dinfo,
        },
        "avisos": avisos,
    }

    tipo = rinfo["tipo"]
    relatorio["deteccao"]["tipo_resposta"] = tipo

    # ----------------------------------------------------------------- #
    # ROTA A — DOSE-RESPOSTA (resposta binária/binomial + preditor de dose)
    # ----------------------------------------------------------------- #
    if dinfo["tem_dose"] and tipo in ("binario", "binomial"):
        relatorio["decisao"] = _texto_decisao_dose(tipo, dinfo)
        relatorio["analise"] = _rodar_dose_resposta(
            dados, papeis, rinfo, chaves, fatores_cols, opcoes, alfa, avisos)
        return relatorio

    # dose com resposta contínua -> regressão (informativo)
    if dinfo["tem_dose"] and tipo in ("continua", "proporcao", "contagem"):
        avisos.append("Há preditor de dose com resposta não-binária: a curva "
                      "de mortalidade (probit/logit) não se aplica; use comparação "
                      "de médias por dose ou regressão. Comparando as doses como "
                      "tratamentos.")
        # cai para comparação de médias tratando dose como fator
        if chaves is None:
            chaves = [str(v) for v in dose]
            fatores_cols = ["dose"]
            dados = {**dados, "dose": [str(v) for v in dose]}
            fatores_vals = [dados["dose"]]

    # ----------------------------------------------------------------- #
    # ROTA B — CONTAGEM (sem dose) -> Poisson/Binomial Negativa
    # ----------------------------------------------------------------- #
    if tipo == "contagem" and chaves is not None and not dinfo["tem_dose"]:
        relatorio["decisao"] = ("Resposta de CONTAGEM (inteiros ≥ 0). Escolhido GLM "
                                "de Poisson; se houver sobredispersão, troca-se "
                                "automaticamente por Binomial Negativa.")
        relatorio["descritiva"] = _descritiva(rinfo["valores"], chaves)
        relatorio["analise"] = glmcount.glm_contagem(rinfo["valores"], chaves, alfa)
        return relatorio

    # ----------------------------------------------------------------- #
    # ROTA C — PROPORÇÃO x de n (sem dose) -> GLM Binomial
    # ----------------------------------------------------------------- #
    if tipo == "binomial" and chaves is not None and not dinfo["tem_dose"]:
        relatorio["decisao"] = ("Resposta BINOMIAL (x de n). Escolhido GLM Binomial "
                                "(logístico); correção de escala se sobredisperso.")
        prop = np.asarray(rinfo["valores"], float) / np.asarray(rinfo["n_total"], float)
        relatorio["descritiva"] = _descritiva(prop * 100, chaves)
        relatorio["analise"] = glmcount.glm_proporcao(
            rinfo["valores"], rinfo["n_total"], chaves, alfa)
        return relatorio

    # ----------------------------------------------------------------- #
    # ROTA D — BINÁRIO individual (sem dose) -> agrega para x de n e GLM Binomial
    # ----------------------------------------------------------------- #
    if tipo == "binario" and chaves is not None and not dinfo["tem_dose"]:
        y_agg, n_agg, grp_agg = [], [], []
        vals = np.asarray(rinfo["valores"], float)
        for grp in sorted(set(chaves)):
            sel = np.array([c == grp for c in chaves]) & ~np.isnan(vals)
            y_agg.append(float(np.nansum(vals[sel]))); n_agg.append(int(np.sum(sel)))
            grp_agg.append(grp)
        relatorio["decisao"] = ("Resposta BINÁRIA (evento/não-evento) por indivíduo. "
                                "Agregada em proporções por tratamento e analisada por "
                                "GLM Binomial (logístico).")
        prop = np.array(y_agg) / np.array(n_agg)
        relatorio["descritiva"] = [{"tratamento": g, "n": nn, "eventos": int(yy),
                                    "proporcao": float(yy / nn)}
                                   for g, nn, yy in zip(grp_agg, n_agg, y_agg)]
        relatorio["analise"] = glmcount.glm_proporcao(y_agg, n_agg, grp_agg, alfa)
        return relatorio

    # ----------------------------------------------------------------- #
    # ROTA E — CONTÍNUA / PROPORÇÃO contínua (severidade %) -> ANOVA + posthoc
    # ----------------------------------------------------------------- #
    if tipo in ("continua", "proporcao") and chaves is not None:
        return _rodar_anova(relatorio, dados, rinfo, fatores_cols, fatores_vals,
                            bloco, chaves, tipo, alfa, opcoes, avisos)

    # ----------------------------------------------------------------- #
    # Sem fatores: só descritiva + normalidade
    # ----------------------------------------------------------------- #
    if chaves is None:
        relatorio["decisao"] = ("Nenhum fator/tratamento informado: apresentando "
                                "estatística descritiva e teste de normalidade.")
        relatorio["descritiva"] = _descritiva(rinfo.get("valores", resp),
                                              ["amostra"] * len(resp))
        relatorio["analise"] = {"tipo_analise": "Descritiva",
                                "normalidade": diag.normalidade(rinfo.get("valores", []))}
        return relatorio

    relatorio["ok"] = False
    relatorio["erro"] = ("Não foi possível decidir a análise para esta combinação "
                         f"de tipo de resposta ('{tipo}') e desenho.")
    return relatorio


# --------------------------------------------------------------------------- #
def _texto_decisao_dose(tipo, dinfo):
    return (f"Resposta {'binária' if tipo == 'binario' else 'binomial (x de n)'} "
            f"com preditor quantitativo de DOSE ({dinfo.get('n_doses','?')} níveis). "
            "Escolhida análise de DOSE-RESPOSTA: ajuste probit e logit por máxima "
            "verossimilhança, com a ligação de menor AIC; CL/DL50 e CL/DL90 com "
            "intervalo de confiança por Fieller, correção de Abbott para mortalidade "
            "natural, qui-quadrado de aderência e fator de heterogeneidade.")


def _rodar_dose_resposta(dados, papeis, rinfo, chaves, fatores_cols, opcoes, alfa, avisos):
    dose = np.asarray([float(str(v).replace(",", ".")) for v in dados[papeis["dose"]]], float)
    vals = np.asarray(rinfo["valores"], float)
    log_dose = bool(opcoes.get("log_dose", True))
    controle = opcoes.get("controle_mort", None)
    unidade = opcoes.get("unidade_dose", "") or ""
    probs = opcoes.get("probs") or None
    if probs:  # garante CL50 (necessária p/ gráfico e potência)
        probs = sorted(set([float(p) for p in probs] + [0.5]))

    grupos = sorted(set(chaves)) if chaves is not None else ["(único)"]

    # ligação comum entre curvas (consistência na comparação)
    link_op = opcoes.get("link", "auto")
    if len(grupos) > 1 and link_op == "auto":
        try:
            dd_all = np.log10(dose[dose > 0]) if log_dose else dose[dose > 0]
            sel_all = dose > 0
            if rinfo["tipo"] == "binomial":
                y_all = vals[sel_all]; n_all = np.asarray(rinfo["n_total"], float)[sel_all]
                pool = doseresponse.analisar_dose_resposta(
                    dose[sel_all], y_all, n_all, controle_mort=controle,
                    log_dose=log_dose, link="auto", alfa=alfa)
                link_op = pool["link"]
        except Exception:
            link_op = "logit"

    curvas, dados_grupos = [], []
    for grp in grupos:
        sel = np.ones(len(dose), bool) if chaves is None else np.array([c == grp for c in chaves])
        d = dose[sel]
        if rinfo["tipo"] == "binomial":
            y = vals[sel]; n = np.asarray(rinfo["n_total"], float)[sel]
        else:
            # binário individual -> agrega por dose
            ud = np.unique(d)
            dd, yy, nn = [], [], []
            for u in ud:
                s2 = sel & (dose == u)
                dd.append(u); yy.append(float(np.nansum(vals[s2])))
                nn.append(int(np.sum(s2 & ~np.isnan(vals))))
            d, y, n = np.array(dd), np.array(yy), np.array(nn)
        try:
            r = doseresponse.analisar_dose_resposta(
                d, y, n, controle_mort=controle, log_dose=log_dose,
                link=link_op, probs=probs, alfa=alfa)
            r["grupo"] = grp
            curvas.append(r)
            # dados tratados (dose>0) para o teste de paralelismo
            mt = d > 0
            x_log = np.log10(d[mt]) if log_dose else d[mt]
            dados_grupos.append((grp, x_log, y[mt], n[mt]))
        except Exception as e:
            avisos.append(f"Falha na curva '{grp}': {e}")

    if len(curvas) == 1:
        return curvas[0]

    resultado = {"tipo_analise": "Dose-resposta (múltiplas curvas)", "curvas": curvas}
    if len(curvas) > 1:
        try:
            resultado["comparacao"] = doseresponse.comparar_curvas(
                curvas, dados_grupos, link_op, alfa=alfa, unidade=unidade)
        except Exception as e:
            avisos.append(f"Comparação de curvas falhou: {e}")
    return resultado


def _rodar_anova(relatorio, dados, rinfo, fatores_cols, fatores_vals,
                 bloco, chaves, tipo, alfa, opcoes, avisos):
    valores = np.asarray(rinfo["valores"], float)

    relatorio["descritiva"] = _descritiva(valores, chaves)

    res_anova = anova_mod.anova(valores, fatores_vals, bloco=bloco, alfa=alfa)

    decisao = ("Resposta CONTÍNUA" if tipo == "continua"
               else "Resposta de PROPORÇÃO/SEVERIDADE contínua")
    decisao += ". Verificadas normalidade dos resíduos (Shapiro-Wilk) e "
    decisao += "homogeneidade de variância (Levene). "
    if res_anova["transformacao"]:
        decisao += (f"Pressupostos violados na escala original → aplicada "
                    f"transformação {res_anova['transformacao']}. ")
    if res_anova["pressupostos_ok"]:
        decisao += "Pressupostos atendidos → ANOVA paramétrica."
    else:
        decisao += ("Pressupostos ainda violados → resultados da ANOVA "
                    "apresentados com cautela e teste não-paramétrico "
                    "(Kruskal-Wallis/Dunn) incluído.")
    relatorio["decisao"] = decisao
    relatorio["analise"] = {k: v for k, v in res_anova.items() if not k.startswith("_")}

    # comparação de médias: SEMPRE Tukey + Scott-Knott (paramétrico);
    # Dunn quando não-paramétrico for indicado.
    medias = {d["tratamento"]: d["media"] for d in relatorio["descritiva"]}
    reps = {d["tratamento"]: d["n"] for d in relatorio["descritiva"]}
    comparacoes = {}

    if res_anova["pressupostos_ok"] or res_anova["kruskal"] is None:
        try:
            comparacoes["tukey"] = posthoc.tukey(valores, chaves, alfa)
        except Exception as e:
            avisos.append(f"Tukey falhou: {e}")
        try:
            comparacoes["scott_knott"] = posthoc.scott_knott(
                medias, reps, res_anova["mse"], res_anova["df_erro"], alfa)
        except Exception as e:
            avisos.append(f"Scott-Knott falhou: {e}")

    if res_anova["kruskal"] is not None:
        try:
            comparacoes["dunn"] = posthoc.dunn(valores, chaves, alfa)
        except Exception as e:
            avisos.append(f"Dunn falhou: {e}")

    relatorio["comparacao_medias"] = comparacoes
    return relatorio
