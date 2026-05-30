"""
Módulo "Mortalidade no tempo" — bioensaios de sobrevivência/eficácia ao longo
do tempo (espelha o pipeline R de Victor Chaves Machado).

Entrada (papéis das colunas):
    tratamento, tempo, n_total, n_vivos  (obrigatórios)
    repeticao, item_teste                (recomendados)
Opções:
    alfa (0.05), sk_threshold (6), controle_neg (rótulo do controle negativo),
    ctrl_mort_max (20), ctrl_estab_min (80)

Entrega: mortalidade %, correção de controle (Abbott/Schneider-Orelli quando a
base inicial é uniforme; Henderson-Tilton quando não é), eficácia, letras de
comparação por tempo (Scott-Knott se nº de tratamentos > limiar, senão Tukey;
Kruskal-Wallis se violar pressupostos), rankings, Kaplan-Meier (LT50/LT90
interpolados + log-rank), QA/QC e modelos (GLM binomial Trat×Tempo com erro
robusto por cluster; beta-regressão da eficácia).
"""

from __future__ import annotations

import re
import numpy as np
import pandas as pd
from scipy import stats

from . import posthoc, diagnostics as diag


# --------------------------------------------------------------------------- #
def _num(v):
    try:
        s = str(v).strip().replace(",", ".")
        if s == "" or s.lower() in ("na", "nan", "none", "null"):
            return np.nan
        return float(s)
    except Exception:
        return np.nan


def _ordem_tratamentos(trats):
    """Ordena tratamentos por número embutido (T1, T2, …) e depois alfabético."""
    def chave(t):
        m = re.search(r"\d+", str(t))
        return (int(m.group()) if m else 1e9, str(t))
    return sorted(set(trats), key=chave)


def _label_tempo(v, u):
    u = (u or "dia")
    return f"{u} {v:g}"


# --------------------------------------------------------------------------- #
# Decisão estatística por tempo: letras de comparação
# --------------------------------------------------------------------------- #
def _decisao_letras(valores, grupos, alfa=0.05, sk_threshold=6):
    valores = np.asarray(valores, float)
    grupos = np.asarray([str(g) for g in grupos])
    m = ~np.isnan(valores)
    valores, grupos = valores[m], grupos[m]
    niveis = list(dict.fromkeys(grupos))
    out = {"metodo": "—", "p_shapiro": None, "p_levene": None,
           "letras": {g: "" for g in niveis},
           "medias": {g: float(np.mean(valores[grupos == g])) for g in niveis
                      if np.any(grupos == g)}}
    if len(niveis) < 2 or valores.size < 3:
        out["metodo"] = "Sem teste (dados insuficientes)"
        return out
    # variância nula
    if np.nanstd(valores) == 0:
        out["metodo"] = "Sem teste (sem variância)"
        out["letras"] = {g: "a" for g in niveis}
        return out
    # repetição mínima
    reps = {g: int(np.sum(grupos == g)) for g in niveis}
    if any(r < 2 for r in reps.values()):
        out["metodo"] = "Sem teste (sem repetição)"
        return out

    gs = [valores[grupos == g] for g in niveis]
    # homogeneidade (Levene) e normalidade dos resíduos (Shapiro)
    try:
        out["p_levene"] = float(stats.levene(*gs, center="median")[1])
    except Exception:
        out["p_levene"] = None
    grand = np.concatenate([g - g.mean() for g in gs])
    try:
        out["p_shapiro"] = float(stats.shapiro(grand)[1]) if grand.size >= 3 else None
    except Exception:
        out["p_shapiro"] = None

    normal = (out["p_shapiro"] is not None and out["p_shapiro"] >= alfa and
              out["p_levene"] is not None and out["p_levene"] >= alfa)

    if normal:
        # MSE e gl do erro de uma ANOVA de uma via
        N = valores.size; k = len(niveis)
        sse = float(sum(np.sum((g - g.mean()) ** 2) for g in gs))
        df_err = N - k
        mse = sse / df_err if df_err > 0 else np.nan
        medias = {g: float(valores[grupos == g].mean()) for g in niveis}
        if k > sk_threshold:
            out["metodo"] = "ANOVA + Scott-Knott"
            try:
                sk = posthoc.scott_knott(medias, reps, mse, df_err, alfa)
                out["letras"] = sk["letras"]
            except Exception as e:
                out["metodo"] += f" (falhou: {e})"
        else:
            out["metodo"] = "ANOVA + Tukey (HSD)"
            try:
                tk = posthoc.tukey(valores, grupos, alfa)
                out["letras"] = tk["letras"]
            except Exception as e:
                out["metodo"] += f" (falhou: {e})"
    else:
        out["metodo"] = "Kruskal-Wallis + Dunn"
        try:
            dn = posthoc.dunn(valores, grupos, alfa)
            out["letras"] = dn["letras"]
        except Exception as e:
            out["metodo"] += f" (falhou: {e})"
    return out


# --------------------------------------------------------------------------- #
# Kaplan-Meier: LT50/LT90 (interpolado) e log-rank
# --------------------------------------------------------------------------- #
def _lt_interpolado(times, surv, target):
    t = np.concatenate([[0.0], np.asarray(times, float)])
    s = np.concatenate([[1.0], np.asarray(surv, float)])
    for i in range(1, len(s)):
        if s[i] <= target:
            if s[i - 1] == s[i]:
                return float(t[i])
            frac = (s[i - 1] - target) / (s[i - 1] - s[i])
            return float(t[i - 1] + frac * (t[i] - t[i - 1]))
    return None  # não atingiu o alvo no período observado


def _kaplan_meier(df, alfa=0.05):
    """df com colunas: Tratamento, Repeticao, Tempo, N_total, N_vivos."""
    from statsmodels.duration.survfunc import SurvfuncRight, survdiff

    eventos = []   # (trat, time, status)
    for (trat, rep), g in df.groupby(["Tratamento", "Repeticao"]):
        g = g.sort_values("Tempo")
        n_total0 = g["N_total"].iloc[0]
        vivos = g["N_vivos"].values
        tempos = g["Tempo"].values
        n_ant = n_total0
        for i, tv in enumerate(tempos):
            if tv <= 0:
                n_ant = vivos[i] if not np.isnan(vivos[i]) else n_ant
                continue
            cur = vivos[i]
            mortes = int(round(max((n_ant if not np.isnan(n_ant) else 0) -
                                   (cur if not np.isnan(cur) else 0), 0)))
            for _ in range(mortes):
                eventos.append((str(trat), float(tv), 1))
            n_ant = cur
        # sobreviventes no último tempo -> censurados
        ult = g[g["Tempo"] == tempos.max()]
        nv = ult["N_vivos"].iloc[-1]
        if not np.isnan(nv) and nv > 0:
            for _ in range(int(round(nv))):
                eventos.append((str(trat), float(tempos.max()), 0))

    if not eventos:
        return None
    ev = pd.DataFrame(eventos, columns=["Tratamento", "time", "status"])

    curvas = []
    for trat, g in ev.groupby("Tratamento"):
        try:
            sf = SurvfuncRight(g["time"].values, g["status"].values)
            lt50 = _lt_interpolado(sf.surv_times, sf.surv_prob, 0.5)
            lt90 = _lt_interpolado(sf.surv_times, sf.surv_prob, 0.1)
            curvas.append({"tratamento": trat,
                           "tempos": [float(x) for x in sf.surv_times],
                           "surv": [float(x) for x in sf.surv_prob],
                           "LT50": lt50, "LT90": lt90,
                           "n": int(g.shape[0]),
                           "mortes": int(g["status"].sum())})
        except Exception:
            pass

    logrank = None
    try:
        codes = ev["Tratamento"].astype("category").cat.codes.values
        if len(np.unique(codes)) >= 2:
            chi2, p = survdiff(ev["time"].values, ev["status"].values, codes)
            logrank = {"qui2": float(chi2), "gl": int(len(np.unique(codes)) - 1),
                       "p": float(p), "significativo": bool(p < alfa)}
    except Exception:
        pass

    return {"curvas": curvas, "logrank": logrank}


# --------------------------------------------------------------------------- #
# QA/QC
# --------------------------------------------------------------------------- #
def _qa_qc(df, controle, ctrl_mort_max=20.0, ctrl_estab_min=80.0):
    qa = {}
    imposs = df[(df["N_total"] < 0) | (df["N_vivos"] < 0) |
                (df["N_vivos"] > df["N_total"]) |
                df["N_total"].isna() | df["N_vivos"].isna() |
                df["Tempo"].isna()]
    qa["impossiveis"] = int(imposs.shape[0])

    dup = df.groupby(["Item_teste", "Tratamento", "Repeticao", "Tempo",
                      "N_total", "N_vivos"]).size()
    qa["duplicatas"] = int((dup > 1).sum())

    mono = 0
    for _, g in df.groupby(["Tratamento", "Repeticao"]):
        g = g.sort_values("Tempo")
        d = np.diff(g["N_vivos"].values)
        mono += int(np.nansum(d > 0))
    qa["monotonicidade"] = int(mono)

    # controle por tempo
    ctrl = df[df["Tratamento"] == controle]
    ctab = []
    for tv, g in ctrl[ctrl["Tempo"] > 0].groupby("Tempo"):
        mort = g["Mort_pct"].mean()
        est = 100 - mort
        ctab.append({"tempo": float(tv), "mort_media": float(mort),
                     "estabilidade": float(est),
                     "ok_mort": bool(mort <= ctrl_mort_max),
                     "ok_estab": bool(est >= ctrl_estab_min)})
    qa["controle"] = ctab
    qa["controle_ok"] = all(c["ok_mort"] and c["ok_estab"] for c in ctab) if ctab else None
    return qa


# --------------------------------------------------------------------------- #
# Modelos (GLM binomial robusto; beta-regressão) — guardados
# --------------------------------------------------------------------------- #
def _modelos(df, controle):
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    res = {}
    d = df[df["Tempo"] > 0].copy()
    d["mortos"] = np.clip(np.round(d["N_total"] - d["N_vivos"]), 0, None)
    d["vivos"] = np.clip(np.round(d["N_vivos"]), 0, None)
    d["TempoF"] = d["Tempo"].astype(str)
    d["RepID"] = d["Tratamento"].astype(str) + ":" + d["Repeticao"].astype(str)

    # GLM binomial Trat*Tempo, erro-padrão por cluster (RepID)
    try:
        if d["Tratamento"].nunique() >= 2:
            endog = d[["mortos", "vivos"]].values
            import patsy
            X = patsy.dmatrix("C(Tratamento) * C(TempoF)", d, return_type="dataframe")
            mod = sm.GLM(endog, X, family=sm.families.Binomial())
            fit = mod.fit(cov_type="cluster", cov_kwds={"groups": d["RepID"].values})
            wt = fit.wald_test_terms(skip_single=False)
            tab = wt.table
            def _p(term):
                for idx in tab.index:
                    if term in str(idx):
                        return float(tab.loc[idx, "pvalue"])
                return None
            res["glm_robusto"] = {
                "convergiu": True,
                "p_tratamento": _p("C(Tratamento)") ,
                "p_tempo": _p("C(TempoF)") if "TempoF" in " ".join(map(str, tab.index)) else None,
                "nota": "GLM binomial Trat×Tempo com erro-padrão robusto por cluster (RepID)",
            }
    except Exception as e:
        res["glm_robusto"] = {"convergiu": False, "erro": str(e)}

    # Beta-regressão da eficácia (no tempo final), se houver eficácia
    try:
        from statsmodels.othermod.betareg import BetaModel
        if "Efic_pct" in d.columns:
            tf = d["Tempo"].max()
            b = d[(d["Tempo"] == tf) & d["Efic_pct"].notna() &
                  (d["Tratamento"] != controle)].copy()
            if b["Tratamento"].nunique() >= 2 and b.shape[0] >= 6:
                n = b.shape[0]
                y = np.clip(b["Efic_pct"].values / 100.0, 1e-6, 1 - 1e-6)
                b["y_adj"] = (y * (n - 1) + 0.5) / n
                bm = BetaModel.from_formula("y_adj ~ C(Tratamento)", b).fit()
                wt = bm.wald_test_terms(skip_single=False)
                ptrat = None
                for idx in wt.table.index:
                    if "Tratamento" in str(idx):
                        ptrat = float(wt.table.loc[idx, "pvalue"])
                res["beta_eficacia"] = {"convergiu": True, "tempo": float(tf),
                                        "p_tratamento": ptrat,
                                        "nota": "Beta-regressão da eficácia no tempo final"}
    except Exception as e:
        res["beta_eficacia"] = {"convergiu": False, "erro": str(e)}
    return res


# --------------------------------------------------------------------------- #
# Função principal
# --------------------------------------------------------------------------- #
def analisar_tempo(dados, papeis, opcoes=None):
    opcoes = opcoes or {}
    alfa = float(opcoes.get("alfa", 0.05))
    sk_threshold = int(opcoes.get("sk_threshold", 6))
    ctrl_mort_max = float(opcoes.get("ctrl_mort_max", 20))
    ctrl_estab_min = float(opcoes.get("ctrl_estab_min", 80))
    avisos = []

    req = ["tratamento", "tempo", "n_total", "n_vivos"]
    falta = [r for r in req if not papeis.get(r) or papeis[r] not in dados]
    if falta:
        return {"ok": False, "erro": "Faltam colunas: " + ", ".join(falta) +
                ". Necessário: tratamento, tempo, n_total, n_vivos."}

    n = len(dados[papeis["tratamento"]])
    df = pd.DataFrame({
        "Tratamento": [str(v) for v in dados[papeis["tratamento"]]],
        "Tempo": [_num(v) for v in dados[papeis["tempo"]]],
        "N_total": [_num(v) for v in dados[papeis["n_total"]]],
        "N_vivos": [_num(v) for v in dados[papeis["n_vivos"]]],
    })
    df["Repeticao"] = ([str(v) for v in dados[papeis["repeticao"]]]
                       if papeis.get("repeticao") in dados else ["1"] * n)
    df["Item_teste"] = ([str(v) for v in dados[papeis["item_teste"]]]
                        if papeis.get("item_teste") in dados else df["Tratamento"])

    df = df.dropna(subset=["Tempo", "N_total", "N_vivos"], how="all")
    df["Mort_pct"] = np.where(df["N_total"] > 0,
                              (df["N_total"] - df["N_vivos"]) / df["N_total"] * 100, np.nan)

    trat_levels = _ordem_tratamentos(df["Tratamento"])
    controle = opcoes.get("controle_neg") or trat_levels[0]
    if controle not in trat_levels:
        avisos.append(f"Controle '{controle}' não encontrado; usando '{trat_levels[0]}'.")
        controle = trat_levels[0]

    tem_t0 = bool(np.any(df["Tempo"] == 0))
    tempos = sorted(t for t in df["Tempo"].dropna().unique() if t > 0)
    if not tempos:
        return {"ok": False, "erro": "Não há avaliações com tempo > 0."}

    # ---------- correção de controle: Abbott/SO (uniforme) ou Henderson-Tilton ----------
    correcao = "—"
    df["Efic_pct"] = np.nan
    base0 = df[df["Tempo"] == 0].groupby(["Tratamento", "Repeticao"])["N_total"].first()
    uniforme = (base0.nunique() == 1) if len(base0) else False

    if uniforme:
        correcao = "Abbott / Schneider-Orelli"
        mc = df[df["Tratamento"] == controle].groupby("Tempo")["Mort_pct"].mean()
        def efic_row(r):
            if r["Tratamento"] == controle or r["Tempo"] <= 0:
                return np.nan
            MC = mc.get(r["Tempo"], np.nan)
            if np.isnan(MC) or MC >= 100:
                return np.nan
            return min(max((r["Mort_pct"] - MC) / (100 - MC) * 100, 0), 100)
        df["Efic_pct"] = df.apply(efic_row, axis=1)
    else:
        correcao = "Henderson-Tilton"
        T0 = df[df["Tempo"] == 0].groupby("Tratamento")["N_vivos"].mean()
        Ct = df[df["Tratamento"] == controle].groupby("Tempo")["N_vivos"].mean()
        C0v = df[(df["Tratamento"] == controle) & (df["Tempo"] == 0)]["N_vivos"].mean()
        def efic_ht(r):
            if r["Tratamento"] == controle or r["Tempo"] <= 0:
                return np.nan
            t0 = T0.get(r["Tratamento"], np.nan); ct = Ct.get(r["Tempo"], np.nan)
            if np.isnan(t0) or t0 <= 0 or np.isnan(ct) or ct <= 0 or np.isnan(C0v) or C0v <= 0:
                return np.nan
            return min(max((1 - (r["N_vivos"] / t0) / (ct / C0v)) * 100, 0), 100)
        df["Efic_pct"] = df.apply(efic_ht, axis=1)
        if not tem_t0:
            avisos.append("Sem tempo 0: Henderson-Tilton fica limitado; "
                          "inclua a avaliação inicial para correção completa.")

    # ---------- letras por tempo (mortalidade e eficácia) ----------
    def letras_por_tempo(coluna, excluir_controle=False):
        linhas = []
        for tv in tempos:
            sub = df[df["Tempo"] == tv]
            if excluir_controle:
                sub = sub[sub["Tratamento"] != controle]
            sub = sub.dropna(subset=[coluna])
            dec = _decisao_letras(sub[coluna].values, sub["Tratamento"].values,
                                  alfa, sk_threshold)
            linhas.append({"tempo": float(tv), **dec})
        return linhas

    letras_mort = letras_por_tempo("Mort_pct")
    letras_efic = letras_por_tempo("Efic_pct", excluir_controle=True)

    # ---------- rankings ----------
    item_de = df.drop_duplicates("Tratamento").set_index("Tratamento")["Item_teste"].to_dict()
    mort_series = df[df["Tempo"] > 0].groupby(["Tratamento", "Tempo"])["Mort_pct"].mean()
    efic_series = df[df["Tempo"] > 0].groupby(["Tratamento", "Tempo"])["Efic_pct"].mean()
    t_final = max(tempos)

    def ranking(series, ascending, no_tempo=None):
        if no_tempo is not None:
            s = series[series.index.get_level_values("Tempo") == no_tempo]
            g = s.groupby("Tratamento").mean()
        else:
            g = series.groupby("Tratamento").mean()
        g = g.dropna().sort_values(ascending=ascending)
        return [{"tratamento": t, "item": item_de.get(t, t), "valor": float(v)}
                for t, v in g.items()]

    rankings = {
        "mort_global": ranking(mort_series, ascending=False),
        "mort_final": ranking(mort_series, ascending=False, no_tempo=t_final),
        "efic_global": ranking(efic_series, ascending=False),
        "efic_final": ranking(efic_series, ascending=False, no_tempo=t_final),
    }

    # ---------- Kaplan-Meier ----------
    km = None
    try:
        km = _kaplan_meier(df, alfa)
    except Exception as e:
        avisos.append(f"Kaplan-Meier falhou: {e}")

    # ---------- QA/QC ----------
    qa = _qa_qc(df, controle, ctrl_mort_max, ctrl_estab_min)

    # ---------- modelos ----------
    modelos = {}
    try:
        modelos = _modelos(df, controle)
    except Exception as e:
        avisos.append(f"Modelos falharam: {e}")

    return {
        "ok": True,
        "tipo_analise": "Mortalidade / sobrevivência no tempo",
        "controle": controle,
        "correcao": correcao,
        "tem_tempo0": tem_t0,
        "n_tratamentos": len(trat_levels),
        "tempos": [float(t) for t in tempos],
        "tratamentos": trat_levels,
        "letras_mortalidade": letras_mort,
        "letras_eficacia": letras_efic,
        "rankings": rankings,
        "kaplan_meier": km,
        "qa_qc": qa,
        "modelos": modelos,
        "avisos": avisos,
    }
