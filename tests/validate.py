"""Validação do bioengine contra dados de referência."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from bioengine import analisar
from bioengine import doseresponse, posthoc, glmcount

GREEN = "\033[92m"; RED = "\033[91m"; END = "\033[0m"
def ok(msg):  print(f"{GREEN}OK{END}  {msg}")
def bad(msg): print(f"{RED}FALHA{END} {msg}")


def teste_dose_resposta():
    print("\n=== 1. Dose-resposta (besouros de Bliss 1935) ===")
    logdose = [1.6907,1.7242,1.7552,1.7842,1.8113,1.8369,1.8610,1.8839]
    n =       [59,60,62,56,63,59,62,60]
    mortos =  [6,13,18,28,52,53,61,60]
    dose = [10**x for x in logdose]
    r = doseresponse.analisar_dose_resposta(dose, mortos, n, link="auto")
    cl50 = [d for d in r["doses_letais"] if d["p"] == 0.5][0]
    print(f"   ligação escolhida: {r['link']}  (AIC {r['link_comparacao']})")
    print(f"   slope = {r['slope']:.3f} ± {r['slope_se']:.3f}")
    print(f"   CL50 = {cl50['dose']:.2f}  IC95% [{cl50['ic_inf']:.2f}, {cl50['ic_sup']:.2f}]")
    print(f"   log10(CL50) = {cl50['log_dose']:.4f}  (esperado ≈ 1.77)")
    print(f"   qui² = {r['qui_quadrado']:.2f} (gl={r['gl']}, p={r['p_qui_quadrado']:.3f}), h={r['heterogeneidade_h']:.2f}")
    assert 1.74 < cl50["log_dose"] < 1.80, "log10(CL50) fora do esperado"
    assert cl50["ic_inf"] < cl50["dose"] < cl50["ic_sup"], "IC não contém a estimativa"
    ok("dose-resposta: CL50 e IC coerentes com a literatura")


def teste_dose_via_orquestrador():
    print("\n=== 2. Dose-resposta via orquestrador (decisão automática) ===")
    logdose = [1.6907,1.7242,1.7552,1.7842,1.8113,1.8369,1.8610,1.8839]
    dados = {
        "dose": [10**x for x in logdose],
        "mortos": [6,13,18,28,52,53,61,60],
        "total": [59,60,62,56,63,59,62,60],
    }
    rel = analisar(dados, {"resposta":"mortos","n_total":"total","dose":"dose"})
    assert rel["ok"]
    print(f"   tipo detectado: {rel['deteccao']['tipo_resposta']}")
    print(f"   decisão: {rel['decisao'][:90]}...")
    assert "binomial" in rel["deteccao"]["tipo_resposta"]
    assert "Dose-resposta" in rel["analise"]["tipo_analise"]
    ok("orquestrador escolheu dose-resposta automaticamente")


def teste_anova_posthoc():
    print("\n=== 3. ANOVA + Tukey + Scott-Knott ===")
    dados = {
        "trat": (["A"]*4 + ["B"]*4 + ["C"]*4 + ["D"]*4),
        "y":    [10,11,12,11, 20,21,19,20, 21,22,20,21, 35,36,34,35],
    }
    rel = analisar(dados, {"resposta":"y","fatores":["trat"]})
    assert rel["ok"]
    print(f"   tipo detectado: {rel['deteccao']['tipo_resposta']}")
    print(f"   análise: {rel['analise']['tipo_analise']}")
    tk = rel["comparacao_medias"]["tukey"]["letras"]
    sk = rel["comparacao_medias"]["scott_knott"]["letras"]
    print(f"   Tukey:       {tk}")
    print(f"   Scott-Knott: {sk}")
    # A é claramente o menor (deve ter letra distinta), D o maior
    assert tk["A"] != tk["D"], "Tukey deveria separar A de D"
    assert sk["A"] != sk["D"], "Scott-Knott deveria separar A de D"
    assert rel["analise"]["normalidade"]["normal"] is not None
    ok("ANOVA detectada, letras Tukey e Scott-Knott geradas")


def teste_letras_cld():
    print("\n=== 4. Compact Letter Display (caso com sobreposição) ===")
    # B e C próximos (compartilham letra), A baixo, D alto
    dados = {
        "trat": (["A"]*5 + ["B"]*5 + ["C"]*5 + ["D"]*5),
        "y": [5,6,5,6,5,  14,15,15,14,16,  15,16,15,16,15,  30,31,30,29,31],
    }
    rel = analisar(dados, {"resposta":"y","fatores":["trat"]})
    sk = rel["comparacao_medias"]["scott_knott"]["letras"]
    tk = rel["comparacao_medias"]["tukey"]["letras"]
    print(f"   médias: {[(d['tratamento'], round(d['media'],1)) for d in rel['descritiva']]}")
    print(f"   Tukey:       {tk}")
    print(f"   Scott-Knott: {sk}")
    # B e C devem compartilhar letra no Tukey
    assert set(tk["B"]) & set(tk["C"]), "B e C deveriam compartilhar letra (Tukey)"
    ok("CLD agrupa corretamente tratamentos não diferentes")


def teste_glm_contagem():
    print("\n=== 5. GLM contagem (Poisson/Binomial Negativa) ===")
    rng = np.random.default_rng(42)
    a = rng.poisson(5, 8); b = rng.poisson(5, 8); c = rng.poisson(20, 8)
    dados = {"trat": (["A"]*8+["B"]*8+["C"]*8),
             "cont": list(a)+list(b)+list(c)}
    rel = analisar(dados, {"resposta":"cont","fatores":["trat"]})
    print(f"   tipo detectado: {rel['deteccao']['tipo_resposta']}")
    print(f"   análise: {rel['analise']['tipo_analise']}")
    print(f"   médias estimadas: { {k:round(v,1) for k,v in rel['analise']['medias_estimadas'].items()} }")
    print(f"   letras: {rel['analise']['letras']}")
    assert rel["deteccao"]["tipo_resposta"] == "contagem"
    assert rel["analise"]["letras"]["C"] != rel["analise"]["letras"]["A"]
    ok("contagem detectada e GLM aplicado com letras")


def teste_glm_proporcao():
    print("\n=== 6. GLM proporção x de n ===")
    dados = {"trat": ["Controle","Controle","Controle","P1","P1","P1","P2","P2","P2"],
             "mortos": [2,3,1, 18,17,19, 9,10,8],
             "total":  [20,20,20, 20,20,20, 20,20,20]}
    rel = analisar(dados, {"resposta":"mortos","n_total":"total","fatores":["trat"]})
    print(f"   tipo detectado: {rel['deteccao']['tipo_resposta']}")
    print(f"   análise: {rel['analise']['tipo_analise']}")
    print(f"   proporções estimadas: { {k:round(v,2) for k,v in rel['analise']['proporcoes_estimadas'].items()} }")
    print(f"   letras: {rel['analise']['letras']}")
    assert rel["deteccao"]["tipo_resposta"] == "binomial"
    assert rel["analise"]["letras"]["P1"] != rel["analise"]["letras"]["Controle"]
    ok("proporção x de n detectada e GLM binomial aplicado")


def teste_severidade_continua():
    print("\n=== 7. Severidade (%) contínua -> ANOVA com transformação ===")
    dados = {"trat": (["T1"]*5+["T2"]*5+["T3"]*5),
             "severidade": [5.2,4.8,6.1,5.5,5.0, 22.3,25.1,21.8,24.0,23.2, 80.1,78.5,82.0,79.3,81.0]}
    rel = analisar(dados, {"resposta":"severidade","fatores":["trat"]})
    print(f"   tipo detectado: {rel['deteccao']['tipo_resposta']}")
    print(f"   transformação: {rel['analise'].get('transformacao')}")
    print(f"   Scott-Knott: {rel['comparacao_medias']['scott_knott']['letras']}")
    assert rel["deteccao"]["tipo_resposta"] == "proporcao"
    ok("severidade % tratada como proporção contínua via ANOVA")


def teste_diametro_nao_e_proporcao():
    print("\n=== 8. Diâmetro 0–100 NÃO deve virar proporção ===")
    dados = {"isolado": (["Controle"]*4+["A"]*4+["B"]*4),
             "diametro": [85.2,84.1,86.0,85.5, 42.1,40.5,43.0,41.2, 15.2,16.1,14.8,15.9]}
    rel = analisar(dados, {"resposta":"diametro","fatores":["isolado"]})
    print(f"   tipo detectado: {rel['deteccao']['tipo_resposta']}")
    print(f"   análise: {rel['analise']['tipo_analise']}")
    assert rel["deteccao"]["tipo_resposta"] == "continua", "diâmetro deveria ser contínua"
    assert "ANOVA" in rel["analise"]["tipo_analise"]
    ok("diâmetro (0–100, mm) corretamente tratado como medida contínua")


def teste_potencia_paralelismo():
    print("\n=== 9. Razão de potência/resistência + paralelismo (RR conhecida = 5x) ===")
    def logistic(z): return 1/(1+np.exp(-z))
    b1 = 3.0
    # Suscetível CL50=10 (x50=1); Resistente CL50=50 (x50=1.699)
    dadosS = {"dose":[], "mortos":[], "total":[], "pop":[]}
    for grp, x50, doses in [("Suscetivel",1.0,[5,7.5,10,15,20]),
                            ("Resistente",np.log10(50),[25,37.5,50,75,100])]:
        for dconc in doses:
            x = np.log10(dconc); p = logistic(b1*(x-x50)); n=40
            dadosS["dose"].append(dconc); dadosS["total"].append(n)
            dadosS["mortos"].append(int(round(n*p))); dadosS["pop"].append(grp)
    rel = analisar(dadosS, {"resposta":"mortos","n_total":"total","dose":"dose","fatores":["pop"]})
    comp = rel["analise"]["comparacao"]
    print(f"   referência: {comp['referencia']}")
    print(f"   paralelismo: p={comp['paralelismo']['p']:.3f} (paralelo={comp['paralelismo']['paralelo']})")
    for r in comp["razoes"]:
        print(f"     {r['grupo']}: CL50={r['lc50']:.2f}, RR={r['rr']:.2f} "
              f"IC[{r['ic_inf']:.2f},{r['ic_sup']:.2f}] sig={r['significativo']}")
    rr_res = [r for r in comp["razoes"] if r["grupo"]=="Resistente"][0]
    assert 3.5 < rr_res["rr"] < 7.0, f"RR esperado ~5, obtido {rr_res['rr']:.2f}"
    assert comp["paralelismo"]["paralelo"], "curvas deveriam ser paralelas"
    assert rr_res["significativo"], "RR deveria ser significativo (IC exclui 1)"
    ok("razão de resistência ≈5x, paralelismo e significância corretos")


def teste_cl_personalizada_e_abbott():
    print("\n=== 10. CL personalizada + Abbott manual ===")
    dados = {"dose":[10,20,40,80,160], "mortos":[5,12,22,30,34], "total":[40,40,40,40,40]}
    rel = analisar(dados, {"resposta":"mortos","n_total":"total","dose":"dose"},
                   {"probs":[0.80,0.95], "controle_mort":0.10, "alfa":0.05})
    a = rel["analise"]
    niveis = sorted(round(d["p"],2) for d in a["doses_letais"])
    print(f"   níveis de CL/DL: {niveis}")
    print(f"   Abbott aplicado: {a['abbott_aplicado']} (controle {a['controle_mortalidade']*100:.0f}%)")
    assert 0.8 in niveis and 0.95 in niveis and 0.5 in niveis, "níveis personalizados ausentes"
    assert a["abbott_aplicado"], "Abbott deveria ter sido aplicado"
    ok("CL/DL personalizada (80,95) + CL50 e correção de Abbott manual OK")


def teste_mortalidade_no_tempo():
    print("\n=== 11. Mortalidade no tempo (KM, correção, QA) ===")
    from bioengine import tempo as T
    rng = np.random.default_rng(7)
    # vivos por (trat, dia): base 20; controle quase sem morte
    perfil = {"T1":[20,20,19], "T2":[20,16,12], "T3":[20,10,5], "T4":[20,6,2]}
    dias = [0,3,7]
    cols = {"trat":[], "rep":[], "dia":[], "ntotal":[], "nvivos":[]}
    for trat, vivos in perfil.items():
        for rep in [1,2,3]:
            for d,v in zip(dias, vivos):
                jitter = 0 if d==0 else int(rng.integers(-1,2))
                cols["trat"].append(trat); cols["rep"].append(rep); cols["dia"].append(d)
                cols["ntotal"].append(20); cols["nvivos"].append(max(min(v+jitter,20),0))
    rel = T.analisar_tempo(cols,
            {"tratamento":"trat","repeticao":"rep","tempo":"dia","n_total":"ntotal","n_vivos":"nvivos"},
            {"controle_neg":"T1"})
    assert rel["ok"], rel.get("erro")
    print(f"   correção: {rel['correcao']}")
    lm_final = [l for l in rel["letras_mortalidade"] if l["tempo"]==7][0]
    print(f"   método (dia 7): {lm_final['metodo']}; letras: {lm_final['letras']}")
    km = rel["kaplan_meier"]
    lts = {c['tratamento']: (round(c['LT50'],1) if c['LT50'] else None) for c in km["curvas"]}
    print(f"   LT50 por trat: {lts}")
    print(f"   log-rank p={km['logrank']['p']:.4f}")
    print(f"   QA controle OK: {rel['qa_qc']['controle_ok']}; ranking mort final 1º: {rel['rankings']['mort_final'][0]['tratamento']}")
    assert rel["correcao"].startswith("Abbott"), "base uniforme deveria usar Abbott/SO"
    assert lm_final["letras"]["T1"] != lm_final["letras"]["T4"], "T1 e T4 deveriam diferir"
    assert km["logrank"]["significativo"], "log-rank deveria ser significativo"
    assert rel["qa_qc"]["controle_ok"], "controle deveria passar no QA"
    assert rel["rankings"]["mort_final"][0]["tratamento"] == "T4", "T4 deveria liderar mortalidade"
    ok("mortalidade no tempo: correção, letras/tempo, KM LT50, log-rank e QA corretos")


if __name__ == "__main__":
    falhas = 0
    for t in [teste_dose_resposta, teste_dose_via_orquestrador, teste_anova_posthoc,
              teste_letras_cld, teste_glm_contagem, teste_glm_proporcao,
              teste_severidade_continua, teste_diametro_nao_e_proporcao,
              teste_potencia_paralelismo, teste_cl_personalizada_e_abbott,
              teste_mortalidade_no_tempo]:
        try:
            t()
        except AssertionError as e:
            bad(f"{t.__name__}: {e}"); falhas += 1
        except Exception as e:
            import traceback; traceback.print_exc(); bad(f"{t.__name__}: ERРО {e}"); falhas += 1
    print("\n" + ("="*50))
    print(f"{GREEN}TODOS OS TESTES PASSARAM{END}" if falhas == 0 else f"{RED}{falhas} teste(s) falharam{END}")
    sys.exit(1 if falhas else 0)
