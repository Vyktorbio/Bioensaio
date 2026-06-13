"""
Modelos lineares generalizados para tratamentos categóricos quando a
resposta é contagem ou proporção (x de n) — sem preditor de dose.

  - contagem  : Poisson  ->  Binomial Negativa se houver sobredispersão
  - proporção : Binomial ->  ajuste de escala (quase-binomial) se sobredisperso

Compara os tratamentos por contrastes de Wald no preditor linear, ajusta
os p-valores (Holm) e produz as letras (compact letter display).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import patsy
import statsmodels.api as sm
import statsmodels.formula.api as smf

from . import diagnostics as diag
from .posthoc import compact_letters, _ajuste_p


def _letras_por_contraste(res, niveis, design_info, alfa, dispersao=1.0):
    """Comparações pareadas no preditor linear -> letras."""
    linhas = {}
    for lv in niveis:
        d = patsy.dmatrix(design_info, pd.DataFrame({"F1": [lv]}), return_type="dataframe")
        linhas[lv] = np.asarray(d.iloc[0].values, float)

    cov = np.asarray(res.cov_params(), float) * dispersao
    beta = np.asarray(res.params, float)

    pares, pvals, detalhes = [], [], []
    for i in range(len(niveis)):
        for j in range(i + 1, len(niveis)):
            a, b = niveis[i], niveis[j]
            c = linhas[a] - linhas[b]
            est = float(c @ beta)
            se = float(np.sqrt(max(c @ cov @ c, 0.0)))
            z = est / se if se > 0 else 0.0
            from scipy import stats as _st
            p = 2 * (1 - _st.norm.cdf(abs(z)))
            pares.append((a, b)); pvals.append(p)
            detalhes.append({"g1": a, "g2": b, "dif_link": est, "z": z, "p": p})

    pajs = _ajuste_p(pvals, "holm")
    difere = set()
    for (a, b), paj, det in zip(pares, pajs, detalhes):
        det["p_ajustado"] = float(paj)
        det["significativo"] = bool(paj < alfa)
        if paj < alfa:
            difere.add(frozenset({a, b}))
    return difere, detalhes


def _medias_preditas(res, niveis, design_info, link_inv):
    out = {}
    for lv in niveis:
        d = patsy.dmatrix(design_info, pd.DataFrame({"F1": [lv]}), return_type="dataframe")
        eta = float(np.asarray(d.iloc[0].values, float) @ np.asarray(res.params, float))
        out[lv] = float(link_inv(eta))
    return out


def glm_contagem(resp, fator, alfa=0.05):
    """Resposta de contagem ~ um fator categórico."""
    df = pd.DataFrame({"y": np.asarray(resp, float), "F1": [str(v) for v in fator]}).dropna()
    niveis = sorted(df["F1"].unique())

    pois = smf.glm("y ~ C(F1)", data=df, family=sm.families.Poisson()).fit()
    over = diag.sobredispersao_poisson(df["y"].values, pois.fittedvalues.values,
                                       len(pois.params))

    modelo, familia, nota = pois, "Poisson", None
    if over["sobredisperso"]:
        try:
            nb = smf.glm("y ~ C(F1)", data=df,
                         family=sm.families.NegativeBinomial()).fit()
            modelo, familia = nb, "Binomial Negativa"
            nota = (f"sobredispersão detectada (φ={over['phi']:.2f}); "
                    "modelo trocado de Poisson para Binomial Negativa")
        except Exception:
            nota = (f"sobredispersão (φ={over['phi']:.2f}); usando quase-Poisson "
                    "(erros-padrão inflados)")

    design_info = modelo.model.data.design_info
    dispersao = over["phi"] if (familia == "Poisson" and over["sobredisperso"]) else 1.0
    difere, comparacoes = _letras_por_contraste(modelo, niveis, design_info, alfa, dispersao)
    medias = _medias_preditas(modelo, niveis, design_info, np.exp)
    ordem = [t for t, _ in sorted(medias.items(), key=lambda kv: kv[1], reverse=True)]
    letras = compact_letters(ordem, difere)

    return {"tipo_analise": f"GLM {familia} (contagem)", "familia": familia,
            "nota_modelo": nota, "sobredispersao": over,
            "medias_estimadas": medias, "letras": letras,
            "comparacoes": comparacoes, "ordem": ordem,
            "aic": float(modelo.aic), "alfa": alfa}


def glm_proporcao(y, n, fator, alfa=0.05):
    """Resposta binomial (x de n) ~ um fator categórico (ex.: % afetados)."""
    df = pd.DataFrame({"y": np.asarray(y, float), "n": np.asarray(n, float),
                       "F1": [str(v) for v in fator]}).dropna()
    df["falha"] = df["n"] - df["y"]
    niveis = sorted(df["F1"].unique())

    endog = df[["y", "falha"]].values
    X = patsy.dmatrix("C(F1)", df, return_type="dataframe")
    design_info = X.design_info
    modelo = sm.GLM(endog, X, family=sm.families.Binomial()).fit()

    mu_prop = np.asarray(modelo.predict(X), dtype=float)
    over = diag.sobredispersao_binomial(df["y"].values, df["n"].values,
                                        mu_prop, len(modelo.params))
    dispersao = over["phi"] if over["sobredisperso"] else 1.0
    familia = "Binomial" + (" (escala quase-binomial)" if over["sobredisperso"] else "")
    nota = (f"sobredispersão (φ={over['phi']:.2f}); erros-padrão corrigidos por escala"
            if over["sobredisperso"] else None)

    inv = lambda eta: 1 / (1 + np.exp(-eta))
    difere, comparacoes = _letras_por_contraste(modelo, niveis, design_info, alfa, dispersao)
    medias = _medias_preditas(modelo, niveis, design_info, inv)
    ordem = [t for t, _ in sorted(medias.items(), key=lambda kv: kv[1], reverse=True)]
    letras = compact_letters(ordem, difere)

    return {"tipo_analise": f"GLM {familia} (proporção x de n)", "familia": familia,
            "nota_modelo": nota, "sobredispersao": over,
            "proporcoes_estimadas": medias, "letras": letras,
            "comparacoes": comparacoes, "ordem": ordem,
            "aic": float(modelo.aic), "alfa": alfa}
