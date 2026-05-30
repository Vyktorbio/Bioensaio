"""
Diagnósticos estatísticos que alimentam a decisão do motor:

    - normalidade dos resíduos (Shapiro-Wilk; D'Agostino como apoio)
    - homogeneidade de variância (Levene robusto e Bartlett)
    - sobredispersão (para contagem/proporção)
    - assimetria / curtose (apoio à escolha de transformação)
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def normalidade(residuos):
    """Shapiro-Wilk (principal) + D'Agostino-Pearson (apoio)."""
    r = np.asarray(residuos, dtype=float)
    r = r[~np.isnan(r)]
    out = {"n": int(r.size)}
    if r.size < 3:
        out.update({"teste": "Shapiro-Wilk", "p": None, "normal": None,
                    "nota": "amostra pequena demais (n<3)"})
        return out
    try:
        W, p = stats.shapiro(r)
        out.update({"teste": "Shapiro-Wilk", "estatistica": float(W), "p": float(p),
                    "normal": bool(p > 0.05)})
    except Exception as e:  # pragma: no cover
        out.update({"teste": "Shapiro-Wilk", "p": None, "normal": None, "erro": str(e)})
    if r.size >= 8:
        try:
            k2, p2 = stats.normaltest(r)
            out["dagostino_p"] = float(p2)
        except Exception:
            pass
    out["assimetria"] = float(stats.skew(r))
    out["curtose"] = float(stats.kurtosis(r))
    return out


def homogeneidade(grupos):
    """
    Homogeneidade de variância entre grupos.
    grupos: lista de arrays (um por tratamento).
    Levene (centrado na mediana) é o principal por ser robusto à não-normalidade.
    """
    gs = [np.asarray(g, dtype=float) for g in grupos]
    gs = [g[~np.isnan(g)] for g in gs if np.sum(~np.isnan(g)) >= 2]
    out = {"k_grupos": len(gs)}
    if len(gs) < 2:
        out.update({"teste": "Levene", "p": None, "homogenea": None,
                    "nota": "poucos grupos válidos"})
        return out
    try:
        W, p = stats.levene(*gs, center="median")
        out.update({"teste": "Levene (mediana)", "estatistica": float(W),
                    "p": float(p), "homogenea": bool(p > 0.05)})
    except Exception as e:  # pragma: no cover
        out.update({"teste": "Levene", "p": None, "homogenea": None, "erro": str(e)})
    try:
        Wb, pb = stats.bartlett(*gs)
        out["bartlett_p"] = float(pb)
    except Exception:
        pass
    return out


def sobredispersao_poisson(y, mu, n_par):
    """
    Razão de sobredispersão para um ajuste de Poisson:
        phi = sum((y - mu)^2 / mu) / (n - p)
    phi >> 1 indica sobredispersão (use binomial negativa / quasi-Poisson).
    """
    y = np.asarray(y, dtype=float)
    mu = np.asarray(mu, dtype=float)
    mu = np.where(mu <= 0, 1e-9, mu)
    pearson = np.sum((y - mu) ** 2 / mu)
    gl = max(len(y) - n_par, 1)
    phi = pearson / gl
    return {"phi": float(phi), "gl": int(gl), "pearson": float(pearson),
            "sobredisperso": bool(phi > 1.5)}


def sobredispersao_binomial(y, n, mu_prop, n_par):
    """
    Sobredispersão para dados binomiais (x de n):
        phi = sum((y - n*p)^2 / (n*p*(1-p))) / (gl)
    """
    y = np.asarray(y, dtype=float)
    n = np.asarray(n, dtype=float)
    p = np.clip(np.asarray(mu_prop, dtype=float), 1e-9, 1 - 1e-9)
    var = n * p * (1 - p)
    var = np.where(var <= 0, 1e-9, var)
    pearson = np.sum((y - n * p) ** 2 / var)
    gl = max(len(y) - n_par, 1)
    phi = pearson / gl
    return {"phi": float(phi), "gl": int(gl), "pearson": float(pearson),
            "sobredisperso": bool(phi > 1.5)}


def sugerir_transformacao(grupos, tipo):
    """
    Sugere transformação quando a normalidade/homogeneidade falham.
    Devolve (nome, funcao, inversa) ou (None, ...).
    """
    todos = np.concatenate([np.asarray(g, float) for g in grupos])
    todos = todos[~np.isnan(todos)]
    if todos.size == 0:
        return None, None, None
    minimo = float(np.min(todos))

    if tipo == "proporcao":
        # arco-seno da raiz é clássico para proporções; logit é alternativa
        def asin(x):
            x = np.clip(np.asarray(x, float), 0, 1)
            return np.arcsin(np.sqrt(x))
        return ("arcsen√ (proporção)", asin, lambda z: np.sin(z) ** 2)

    if tipo == "contagem":
        # √(x + 3/8) estabiliza variância de contagens (Anscombe)
        return ("√(x+3/8) (contagem)",
                lambda x: np.sqrt(np.asarray(x, float) + 0.375),
                lambda z: z ** 2 - 0.375)

    # contínua: log se tudo positivo e assimétrico à direita
    if minimo > 0:
        return ("log(x)", lambda x: np.log(np.asarray(x, float)), np.exp)
    if minimo > -1:
        return ("log(x+1)",
                lambda x: np.log1p(np.asarray(x, float)),
                lambda z: np.expm1(z))
    return None, None, None
