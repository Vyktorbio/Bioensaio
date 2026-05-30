"""
Análise de dose-resposta (probit / logit) — núcleo "estilo PoloPlus".

Recursos:
  - ajuste binomial com ligação probit OU logit (escolha automática por AIC)
  - CLp / DLp (p = 0.5, 0.9, 0.95, 0.99 e personalizados)
  - intervalo de confiança das doses letais por teorema de Fieller
  - correção de Abbott para mortalidade natural (controle)
  - modelo de 3 parâmetros com mortalidade natural estimada (MLE)
  - qui-quadrado de aderência e fator de heterogeneidade (h)
  - inclinação (slope) ± erro-padrão

Convenção: por padrão o modelo é ajustado em log10(dose) (clássico em
bioensaios). As doses letais são devolvidas na escala original (10^x).
"""

from __future__ import annotations

import numpy as np
import patsy
from scipy import stats
from scipy.optimize import minimize
import statsmodels.api as sm
from statsmodels.genmod.families import links as L


_PROBS = [0.10, 0.25, 0.50, 0.90, 0.95, 0.99]


def _link_obj(nome):
    return L.Probit() if nome == "probit" else L.Logit()


def _quantil(nome, p):
    """Valor da função de ligação no ponto p: probit=Phi^-1(p); logit=log(p/(1-p))."""
    if nome == "probit":
        return stats.norm.ppf(p)
    return np.log(p / (1 - p))


def abbott(prop_obs, controle):
    """Correção de Abbott: p_corr = (p_obs - c)/(1 - c)."""
    c = float(controle)
    if c <= 0:
        return np.asarray(prop_obs, float)
    corr = (np.asarray(prop_obs, float) - c) / (1 - c)
    return np.clip(corr, 0.0, 1.0)


def _ajustar_glm(x, y, n, link):
    """Ajuste GLM binomial. Retorna params, cov, e o objeto de resultado."""
    X = sm.add_constant(np.asarray(x, float).reshape(-1, 1))
    endog = np.column_stack([np.asarray(y, float), np.asarray(n, float) - np.asarray(y, float)])
    modelo = sm.GLM(endog, X, family=sm.families.Binomial(link=_link_obj(link)))
    res = modelo.fit()
    return res


def _fieller(theta, b0, b1, cov, tcrit):
    """
    IC de Fieller para x_p = (theta - b0)/b1.

    N = theta - b0 ; D = b1
    Var(N)=Var(b0) ; Var(D)=Var(b1) ; Cov(N,D) = -Cov(b0,b1)
    """
    v_b0 = cov[0, 0]
    v_b1 = cov[1, 1]
    cov_b0b1 = cov[0, 1]

    N = theta - b0
    D = b1
    r = N / D
    vN = v_b0
    vD = v_b1
    cND = -cov_b0b1

    g = (tcrit ** 2) * vD / (D ** 2)
    if g >= 1:
        return r, None, None, g  # denominador não diferente de zero: IC ilimitado

    centro = (r - g * cND / vD) / (1 - g)
    sob = vN - 2 * r * cND + (r ** 2) * vD - g * (vN - (cND ** 2) / vD)
    sob = max(sob, 0.0)
    meia = (tcrit / abs(D)) * np.sqrt(sob) / (1 - g)
    return centro, centro - meia, centro + meia, g


def _mle_natural(x, y, n, link):
    """
    Modelo de 3 parâmetros (Finney): P = C + (1-C) F(b0 + b1 x),
    com C = mortalidade natural estimada. MLE via scipy.
    """
    F = stats.norm.cdf if link == "probit" else (lambda z: 1 / (1 + np.exp(-z)))
    y = np.asarray(y, float); n = np.asarray(n, float); x = np.asarray(x, float)

    def negll(par):
        C, b0, b1 = par
        eta = b0 + b1 * x
        P = C + (1 - C) * F(eta)
        P = np.clip(P, 1e-9, 1 - 1e-9)
        return -np.sum(y * np.log(P) + (n - y) * np.log(1 - P))

    # chute inicial: C pelo menor x, b por regressão simples
    C0 = max(min(float(y[np.argmin(x)] / max(n[np.argmin(x)], 1)), 0.3), 0.0)
    res = minimize(negll, x0=[C0, -2.0, 1.0],
                   bounds=[(0.0, 0.5), (-50, 50), (1e-4, 50)],
                   method="L-BFGS-B")
    C, b0, b1 = res.x
    return {"C": float(C), "b0": float(b0), "b1": float(b1),
            "loglik": float(-res.fun), "convergiu": bool(res.success)}


def analisar_dose_resposta(dose, y, n, controle_mort=None, log_dose=True,
                           link="auto", probs=None, alfa=0.05):
    """
    Parâmetros
    ----------
    dose : doses/concentrações (uma por grupo)
    y    : nº de respostas (mortos/afetados) por grupo
    n    : nº total testado por grupo
    controle_mort : mortalidade natural (proporção 0–1) ou None.
                    Se houver dose 0 nos dados, é estimada automaticamente.
    log_dose : ajustar em log10(dose) (recomendado)
    link : "probit", "logit" ou "auto" (escolhe menor AIC)
    """
    dose = np.asarray(dose, float)
    y = np.asarray(y, float)
    n = np.asarray(n, float)
    probs = probs or _PROBS

    # separa controle (dose 0) se existir
    mask_ctrl = dose <= 0
    c_auto = None
    if np.any(mask_ctrl):
        yc = y[mask_ctrl].sum(); nc = n[mask_ctrl].sum()
        c_auto = float(yc / nc) if nc > 0 else 0.0
    controle = controle_mort if controle_mort is not None else c_auto

    # dados tratados (dose > 0)
    m = dose > 0
    d = dose[m]; yt = y[m].copy(); nt = n[m]
    x = np.log10(d) if log_dose else d

    # correção de Abbott na proporção (se houver mortalidade natural)
    abbott_aplicado = False
    prop = yt / nt
    if controle and controle > 0:
        prop_corr = abbott(prop, controle)
        yt = np.round(prop_corr * nt)
        abbott_aplicado = True

    # escolha de ligação
    candidatos = ["probit", "logit"] if link == "auto" else [link]
    ajustes = {}
    for lk in candidatos:
        try:
            res = _ajustar_glm(x, yt, nt, lk)
            ajustes[lk] = res
        except Exception as e:  # pragma: no cover
            ajustes[lk] = e
    validos = {k: v for k, v in ajustes.items() if not isinstance(v, Exception)}
    if not validos:
        raise RuntimeError("Falha ao ajustar o modelo de dose-resposta.")
    melhor = min(validos, key=lambda k: validos[k].aic)
    res = validos[melhor]

    b0, b1 = float(res.params[0]), float(res.params[1])
    cov = np.asarray(res.cov_params(), float)
    se_b1 = float(np.sqrt(cov[1, 1]))

    # qui-quadrado de aderência e heterogeneidade
    mu = res.fittedvalues  # proporções ajustadas
    pearson = float(np.sum((yt - nt * mu) ** 2 / (nt * mu * (1 - mu) + 1e-12)))
    gl = int(len(x) - 2)
    h = pearson / gl if gl > 0 else float("nan")
    p_qui = float(1 - stats.chi2.cdf(pearson, gl)) if gl > 0 else None
    heterogeneo = gl > 0 and h > 1.0

    # PoloPlus: se heterogêneo, infla a variância por h e usa t com gl
    if heterogeneo:
        cov = cov * h
        tcrit = float(stats.t.ppf(1 - alfa / 2, gl))
    else:
        tcrit = float(stats.norm.ppf(1 - alfa / 2))

    # doses letais
    letais = []
    for p in probs:
        theta = _quantil(melhor, p)
        xp, lo, hi, g = _fieller(theta, b0, b1, cov, tcrit)
        registro = {"p": p, "log_dose": float(xp)}
        if log_dose:
            registro["dose"] = float(10 ** xp)
            registro["ic_inf"] = float(10 ** lo) if lo is not None else None
            registro["ic_sup"] = float(10 ** hi) if hi is not None else None
        else:
            registro["dose"] = float(xp)
            registro["ic_inf"] = float(lo) if lo is not None else None
            registro["ic_sup"] = float(hi) if hi is not None else None
        letais.append(registro)

    # log10(CL50) e sua variância (método delta) — base para razão de potência
    x50 = -b0 / b1                       # = log10(CL50) quando log_dose
    var_x50 = (cov[0, 0] / b1 ** 2
               + (b0 ** 2) * cov[1, 1] / b1 ** 4
               - 2 * b0 * cov[0, 1] / b1 ** 3)
    var_x50 = float(max(var_x50, 0.0))
    if log_dose:
        log_lc50, var_log_lc50 = float(x50), var_x50
    else:
        lc50_lin = x50
        log_lc50 = float(np.log10(lc50_lin)) if lc50_lin > 0 else float("nan")
        var_log_lc50 = float(var_x50 / (lc50_lin * np.log(10)) ** 2) if lc50_lin > 0 else float("nan")

    # modelo com mortalidade natural estimada (informativo)
    natural = None
    if controle is None or controle == 0:
        try:
            nat = _mle_natural(x, y[m], n[m], melhor)
            if nat["convergiu"] and nat["C"] > 0.01:
                natural = nat
        except Exception:
            pass

    return {
        "tipo_analise": "Dose-resposta (regressão " + melhor + ")",
        "link": melhor,
        "link_comparacao": {k: float(v.aic) for k, v in validos.items()},
        "escala_dose": "log10" if log_dose else "linear",
        "n_grupos": int(len(x)),
        "intercepto": b0,
        "slope": b1,
        "slope_se": se_b1,
        "slope_t": float(b1 / se_b1) if se_b1 else None,
        "controle_mortalidade": float(controle) if controle else 0.0,
        "abbott_aplicado": abbott_aplicado,
        "qui_quadrado": pearson,
        "gl": gl,
        "p_qui_quadrado": p_qui,
        "heterogeneidade_h": float(h) if gl > 0 else None,
        "heterogeneo": bool(heterogeneo),
        "criterio_ic": "t de Student (g.l.) por heterogeneidade" if heterogeneo
                       else "normal (z)",
        "doses_letais": letais,
        "modelo_natural_mle": natural,
        "log_lc50": log_lc50,
        "var_log_lc50": var_log_lc50,
        "aic": float(res.aic),
        "deviance": float(res.deviance),
    }


def comparar_curvas(curvas, dados_grupos, link, alfa=0.05, unidade=""):
    """
    Compara várias curvas de dose-resposta (produtos/populações):
      - teste de PARALELISMO (slope comum vs separado, por razão de verossimilhança)
      - teste de diferença de POTÊNCIA (linhas iguais vs paralelas distintas)
      - RAZÃO DE POTÊNCIA / RESISTÊNCIA (RR = CL50_i / CL50_ref) com IC

    curvas        : lista de resultados de analisar_dose_resposta (cada um com grupo,
                    doses_letais, log_lc50, var_log_lc50)
    dados_grupos  : lista de (grupo, x_logdose, y, n) com os dados de cada curva
    """
    # ----- modelos combinados p/ paralelismo e diferença de potência -----
    linhas = []
    for grp, x, y, n in dados_grupos:
        x = np.asarray(x, float); y = np.asarray(y, float); n = np.asarray(n, float)
        for xi, yi, ni in zip(x, y, n):
            linhas.append({"grupo": str(grp), "x": float(xi),
                           "suc": float(yi), "fal": float(ni - yi)})
    import pandas as pd
    df = pd.DataFrame(linhas)
    fam = sm.families.Binomial(link=_link_obj(link))
    endog = df[["suc", "fal"]].values

    def ajusta(formula):
        X = patsy.dmatrix(formula, df, return_type="dataframe")
        return sm.GLM(endog, X, family=fam).fit(), X.shape[1]

    paralelismo = potencia = None
    try:
        m_eq, k_eq = ajusta("x")                 # mesma linha p/ todos
        m_par, k_par = ajusta("C(grupo) + x")    # paralelas (slope comum)
        m_full, k_full = ajusta("C(grupo) * x")  # slopes separados

        lr_par = float(m_par.deviance - m_full.deviance)
        gl_par = int(k_full - k_par)
        p_par = float(stats.chi2.sf(lr_par, gl_par)) if gl_par > 0 else None
        paralelismo = {"qui2": lr_par, "gl": gl_par, "p": p_par,
                       "paralelo": bool(p_par is not None and p_par > alfa)}

        lr_eq = float(m_eq.deviance - m_par.deviance)
        gl_eq = int(k_par - k_eq)
        p_eq = float(stats.chi2.sf(lr_eq, gl_eq)) if gl_eq > 0 else None
        potencia = {"qui2": lr_eq, "gl": gl_eq, "p": p_eq,
                    "difere": bool(p_eq is not None and p_eq < alfa)}
    except Exception as e:  # pragma: no cover
        paralelismo = {"erro": str(e)}

    # ----- razão de potência / resistência (referência = menor CL50) -----
    info = []
    for c in curvas:
        cl50 = next((d for d in c["doses_letais"] if abs(d["p"] - 0.5) < 1e-9), None)
        info.append({"grupo": c["grupo"], "lc50": cl50["dose"] if cl50 else None,
                     "loglc50": c.get("log_lc50"), "var": c.get("var_log_lc50")})
    validos = [it for it in info if it["lc50"] and it["loglc50"] is not None]
    razoes, referencia = [], None
    if validos:
        ref = min(validos, key=lambda z: z["lc50"])
        referencia = ref["grupo"]
        zc = float(stats.norm.ppf(1 - alfa / 2))
        for it in info:
            if it["loglc50"] is None or it["var"] is None:
                continue
            diff = it["loglc50"] - ref["loglc50"]
            se = float(np.sqrt(max(it["var"] + ref["var"], 0.0)))
            lo, hi = diff - zc * se, diff + zc * se
            razoes.append({
                "grupo": it["grupo"], "lc50": it["lc50"],
                "rr": float(10 ** diff),
                "ic_inf": float(10 ** lo), "ic_sup": float(10 ** hi),
                "referencia": it["grupo"] == ref["grupo"],
                "significativo": not (lo <= 0 <= hi),  # IC da razão exclui 1
            })
        razoes.sort(key=lambda r: r["rr"])

    return {"link": link, "unidade": unidade, "referencia": referencia,
            "paralelismo": paralelismo, "diferenca_potencia": potencia,
            "razoes": razoes}
