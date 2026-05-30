"""
Comparação múltipla de médias com letras (compact letter display).

  - Tukey HSD          (paramétrico clássico)
  - Scott-Knott        (agrupamento por razão de verossimilhança; sem ambiguidade)
  - Dunn               (não-paramétrico, pós Kruskal-Wallis)
  - Duncan / LSD       (opcionais)

As letras seguem a convenção: tratamentos que compartilham ao menos uma
letra NÃO diferem significativamente. Por padrão 'a' é o maior grupo.
"""

from __future__ import annotations

import numpy as np
from scipy import stats
from statsmodels.stats.multicomp import pairwise_tukeyhsd


# --------------------------------------------------------------------------- #
# Compact Letter Display (algoritmo insere-e-absorve, Piepho 2004)
# --------------------------------------------------------------------------- #
def compact_letters(ordem, difere):
    """
    ordem  : lista de tratamentos já ordenada (ex.: por média decrescente)
    difere : conjunto de frozenset({a,b}) dos pares que DIFEREM significativamente
    Retorna dict tratamento -> string de letras.
    """
    colunas = [set(ordem)]  # cada coluna = um grupo que compartilha uma letra

    def absorver(cols):
        cols = [c for c in cols if c]
        final = []
        for c in cols:
            if any(c < o for o in cols if o is not c and c != o):
                # c é subconjunto próprio de outra coluna -> absorvido
                if any(c < o for o in cols if o is not c):
                    continue
            final.append(c)
        # remove duplicatas
        unicas = []
        for c in final:
            if not any(c == u for u in unicas):
                unicas.append(c)
        return unicas

    for par in difere:
        a, b = tuple(par)
        novas = []
        for col in colunas:
            if a in col and b in col:
                novas.append(col - {a})
                novas.append(col - {b})
            else:
                novas.append(col)
        colunas = absorver(novas)

    # ordena colunas para que 'a' fique no topo (maior média = primeiro em 'ordem')
    idx = {t: i for i, t in enumerate(ordem)}
    colunas.sort(key=lambda c: min(idx[t] for t in c))

    letras_de = {t: "" for t in ordem}
    abc = "abcdefghijklmnopqrstuvwxyz"
    for j, col in enumerate(colunas):
        letra = abc[j] if j < 26 else f"({j+1})"
        for t in ordem:
            if t in col:
                letras_de[t] += letra
    return letras_de


def _ordenar_por_media(medias):
    return [t for t, _ in sorted(medias.items(), key=lambda kv: kv[1], reverse=True)]


# --------------------------------------------------------------------------- #
# Tukey HSD
# --------------------------------------------------------------------------- #
def tukey(valores, grupos, alfa=0.05):
    """
    valores : array 1d de todas as observações
    grupos  : array 1d (mesmo tamanho) com o rótulo do tratamento de cada obs
    """
    valores = np.asarray(valores, float)
    grupos = np.asarray([str(g) for g in grupos])
    m = ~np.isnan(valores)
    valores, grupos = valores[m], grupos[m]

    res = pairwise_tukeyhsd(valores, grupos, alpha=alfa)
    nomes = list(res.groupsunique)
    difere = set()
    detalhes = []
    for i, rej in enumerate(res.reject):
        g1 = str(res._results_table.data[i + 1][0])
        g2 = str(res._results_table.data[i + 1][1])
        diff = float(res.meandiffs[i])
        p = float(res.pvalues[i])
        detalhes.append({"g1": g1, "g2": g2, "diferenca": diff, "p": p,
                         "significativo": bool(rej)})
        if rej:
            difere.add(frozenset({g1, g2}))

    medias = {g: float(np.mean(valores[grupos == g])) for g in nomes}
    ordem = _ordenar_por_media(medias)
    letras = compact_letters(ordem, difere)
    return {"metodo": "Tukey HSD", "alfa": alfa, "medias": medias,
            "letras": letras, "comparacoes": detalhes, "ordem": ordem}


# --------------------------------------------------------------------------- #
# Scott-Knott
# --------------------------------------------------------------------------- #
def _b0_max(med_ordenadas):
    """Melhor partição em dois grupos -> maior soma de quadrados entre grupos."""
    k = len(med_ordenadas)
    total = np.sum(med_ordenadas)
    melhor_b0, melhor_i = -np.inf, None
    for i in range(1, k):
        t1 = np.sum(med_ordenadas[:i]); t2 = total - t1
        b0 = (t1 ** 2) / i + (t2 ** 2) / (k - i) - (total ** 2) / k
        if b0 > melhor_b0:
            melhor_b0, melhor_i = b0, i
    return melhor_b0, melhor_i


def scott_knott(medias, reps, mse, df_erro, alfa=0.05):
    """
    medias  : dict tratamento -> média
    reps    : repetições por tratamento (escalar; usa média se desbalanceado)
    mse     : quadrado médio do erro (QME) da ANOVA
    df_erro : graus de liberdade do erro
    """
    r = float(np.mean(list(reps.values()))) if isinstance(reps, dict) else float(reps)
    itens = sorted(medias.items(), key=lambda kv: kv[1])  # crescente
    nomes = [t for t, _ in itens]
    vals = np.array([v for _, v in itens], float)
    k = len(vals)

    # sigma0^2 = [ Σ(ȳ_i - ȳ..)^2 + ν·(QME/r) ] / (k + ν)
    var_media = mse / r
    sigma0 = (np.sum((vals - vals.mean()) ** 2) + df_erro * var_media) / (k + df_erro)
    fator = np.pi / (2 * (np.pi - 2))

    grupos = []  # lista de listas de índices (em 'nomes')

    def dividir(idxs):
        sub = vals[idxs]
        if len(sub) == 1:
            grupos.append(idxs); return
        b0, i = _b0_max(sub)
        lam = fator * (b0 / sigma0) if sigma0 > 0 else 0.0
        gl = len(sub) / (np.pi - 2)
        crit = stats.chi2.ppf(1 - alfa, gl)
        if lam > crit:  # diferença significativa -> divide
            dividir(idxs[:i]); dividir(idxs[i:])
        else:
            grupos.append(idxs)

    dividir(list(range(k)))

    # atribui letras: grupos com maior média recebem 'a'
    grupos.sort(key=lambda g: -np.mean([vals[j] for j in g]))
    abc = "abcdefghijklmnopqrstuvwxyz"
    letras = {}
    for j, g in enumerate(grupos):
        L = abc[j] if j < 26 else f"({j+1})"
        for idx in g:
            letras[nomes[idx]] = L

    medias_ord = {t: float(medias[t]) for t in
                  sorted(medias, key=lambda t: medias[t], reverse=True)}
    return {"metodo": "Scott-Knott", "alfa": alfa, "medias": medias_ord,
            "letras": letras, "n_grupos": len(grupos),
            "ordem": list(medias_ord.keys())}


# --------------------------------------------------------------------------- #
# Dunn (não-paramétrico)
# --------------------------------------------------------------------------- #
def dunn(valores, grupos, alfa=0.05, ajuste="holm"):
    """Teste de Dunn com correção de múltiplas comparações (Holm por padrão)."""
    valores = np.asarray(valores, float)
    grupos = np.asarray([str(g) for g in grupos])
    m = ~np.isnan(valores)
    valores, grupos = valores[m], grupos[m]

    nomes = sorted(set(grupos))
    N = len(valores)
    ranks = stats.rankdata(valores)
    # correção de empates
    _, counts = np.unique(valores, return_counts=True)
    tie = np.sum(counts ** 3 - counts)
    sigma2 = (N * (N + 1) / 12.0) - tie / (12.0 * (N - 1))

    rbar, ni = {}, {}
    for g in nomes:
        sel = grupos == g
        rbar[g] = ranks[sel].mean()
        ni[g] = int(np.sum(sel))

    pares, pvals = [], []
    for a in range(len(nomes)):
        for b in range(a + 1, len(nomes)):
            ga, gb = nomes[a], nomes[b]
            se = np.sqrt(sigma2 * (1.0 / ni[ga] + 1.0 / ni[gb]))
            z = (rbar[ga] - rbar[gb]) / se if se > 0 else 0.0
            p = 2 * (1 - stats.norm.cdf(abs(z)))
            pares.append((ga, gb)); pvals.append(p)

    # ajuste de múltiplas comparações
    pvals_aj = _ajuste_p(pvals, ajuste)
    difere, detalhes = set(), []
    for (ga, gb), p, paj in zip(pares, pvals, pvals_aj):
        sig = paj < alfa
        detalhes.append({"g1": ga, "g2": gb, "p": float(p), "p_ajustado": float(paj),
                         "significativo": bool(sig)})
        if sig:
            difere.add(frozenset({ga, gb}))

    medianas = {g: float(np.median(valores[grupos == g])) for g in nomes}
    ordem = [t for t, _ in sorted(medianas.items(), key=lambda kv: kv[1], reverse=True)]
    letras = compact_letters(ordem, difere)
    return {"metodo": f"Dunn ({ajuste})", "alfa": alfa, "medianas": medianas,
            "letras": letras, "comparacoes": detalhes, "ordem": ordem}


def _ajuste_p(pvals, metodo):
    p = np.asarray(pvals, float)
    n = len(p)
    if metodo == "bonferroni":
        return np.minimum(p * n, 1.0)
    # Holm
    ordem = np.argsort(p)
    aj = np.empty(n)
    corr_max = 0.0
    for rank, idx in enumerate(ordem):
        val = (n - rank) * p[idx]
        corr_max = max(corr_max, val)
        aj[idx] = min(corr_max, 1.0)
    return aj
