"""
ANOVA (uma via e fatorial) com diagnóstico e alternativas.

Fluxo:
  1. ajusta o modelo (OLS) na escala original
  2. testa normalidade dos resíduos e homogeneidade de variância
  3. se violar, tenta transformação adequada e reavalia
  4. se ainda violar (ou poucos dados), indica via não-paramétrica (Kruskal-Wallis)

Devolve QME (mse) e g.l. do erro para alimentar Scott-Knott/Tukey.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

from . import diagnostics as diag


def _df(resp, fatores, bloco=None):
    dados = {"y": np.asarray(resp, float)}
    nomes_fatores = []
    for i, f in enumerate(fatores):
        col = f"F{i+1}"
        dados[col] = [str(v) for v in f]
        nomes_fatores.append(col)
    if bloco is not None:
        dados["bloco"] = [str(v) for v in bloco]
    return pd.DataFrame(dados), nomes_fatores


def _formula(nomes_fatores, bloco, com_interacao):
    termos = nomes_fatores[:]
    if com_interacao and len(nomes_fatores) >= 2:
        termos = ["*".join(nomes_fatores)] if len(nomes_fatores) == 2 else nomes_fatores
        if len(nomes_fatores) == 2:
            termos = [f"{nomes_fatores[0]}*{nomes_fatores[1]}"]
    rhs = " + ".join([f"C({t})" if "*" not in t else
                      "*".join(f"C({x})" for x in t.split("*")) for t in termos])
    if bloco:
        rhs += " + C(bloco)"
    return f"y ~ {rhs}"


def _ajustar(df, nomes_fatores, tem_bloco, com_interacao=True):
    formula = _formula(nomes_fatores, "bloco" if tem_bloco else None, com_interacao)
    modelo = smf.ols(formula, data=df).fit()
    aov = sm.stats.anova_lm(modelo, typ=2)
    return modelo, aov, formula


def anova(resp, fatores, bloco=None, alfa=0.05, transformar_auto=True):
    df, nomes_fatores = _df(resp, fatores, bloco)
    df = df.dropna(subset=["y"])
    tem_bloco = bloco is not None

    transformacao = None
    inversa = None
    usada = "original"

    modelo, aov, formula = _ajustar(df, nomes_fatores, tem_bloco)
    resid = modelo.resid.values
    norm = diag.normalidade(resid)

    # grupos para homogeneidade (combinação dos fatores)
    df["_grp"] = df[nomes_fatores].astype(str).agg("|".join, axis=1)
    grupos = [g["y"].values for _, g in df.groupby("_grp")]
    homog = diag.homogeneidade(grupos)

    pressupostos_ok = bool(norm.get("normal")) and bool(homog.get("homogenea"))

    if not pressupostos_ok and transformar_auto:
        nome_t, ft, inv = diag.sugerir_transformacao(grupos, "continua")
        if ft is not None:
            try:
                df2 = df.copy()
                df2["y"] = ft(df2["y"].values)
                if np.all(np.isfinite(df2["y"].values)):
                    modelo_t, aov_t, formula_t = _ajustar(df2, nomes_fatores, tem_bloco)
                    norm_t = diag.normalidade(modelo_t.resid.values)
                    grupos_t = [g["y"].values for _, g in df2.groupby("_grp")]
                    homog_t = diag.homogeneidade(grupos_t)
                    if bool(norm_t.get("normal")) or bool(homog_t.get("homogenea")):
                        modelo, aov, formula = modelo_t, aov_t, formula_t
                        norm, homog = norm_t, homog_t
                        transformacao, inversa, usada = nome_t, inv, nome_t
                        df = df2
                        pressupostos_ok = bool(norm_t.get("normal")) and bool(homog_t.get("homogenea"))
            except Exception:
                pass

    # extrai QME e g.l. do erro
    mse = float(modelo.mse_resid)
    df_erro = int(modelo.df_resid)

    # tabela ANOVA -> dict
    tabela = []
    for termo in aov.index:
        linha = aov.loc[termo]
        tabela.append({
            "fonte": termo.replace("C(", "").replace(")", ""),
            "gl": float(linha.get("df", np.nan)),
            "sq": float(linha.get("sum_sq", np.nan)),
            "qm": float(linha.get("sum_sq", np.nan) / linha.get("df", np.nan))
                  if linha.get("df", 0) else None,
            "F": float(linha.get("F", np.nan)) if not pd.isna(linha.get("F", np.nan)) else None,
            "p": float(linha.get("PR(>F)", np.nan)) if not pd.isna(linha.get("PR(>F)", np.nan)) else None,
        })

    # significância de cada fator
    fatores_signif = {}
    for i, _ in enumerate(nomes_fatores):
        chave = f"C(F{i+1})"
        if chave in aov.index:
            p = aov.loc[chave, "PR(>F)"]
            fatores_signif[f"F{i+1}"] = {"p": float(p), "significativo": bool(p < alfa)}

    # alternativa não-paramétrica (Kruskal) quando pressupostos seguem violados
    kruskal = None
    if not pressupostos_ok and len(nomes_fatores) == 1:
        try:
            H, pk = stats.kruskal(*grupos)
            kruskal = {"H": float(H), "p": float(pk), "significativo": bool(pk < alfa)}
        except Exception:
            pass

    return {
        "tipo_analise": "ANOVA" + (" fatorial" if len(nomes_fatores) > 1 else " (uma via)")
                        + (" em blocos" if tem_bloco else ""),
        "formula": formula,
        "transformacao": transformacao,
        "escala_usada": usada,
        "normalidade": norm,
        "homogeneidade": homog,
        "pressupostos_ok": pressupostos_ok,
        "tabela_anova": tabela,
        "fatores_significativos": fatores_signif,
        "mse": mse,
        "df_erro": df_erro,
        "kruskal": kruskal,
        "_modelo": modelo,
        "_df": df,
        "_nomes_fatores": nomes_fatores,
        "_inversa": inversa,
    }
