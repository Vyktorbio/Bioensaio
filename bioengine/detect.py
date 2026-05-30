"""
Detecção do tipo de variável-resposta e do desenho experimental.

A partir das colunas que o usuário marca (resposta, fator(es), dose,
bloco, n_total / n_resposta), classificamos a resposta em uma de:

    - "binario"      : 0/1, vivo/morto, presença/ausência (linha = indivíduo)
    - "binomial"     : x mortos de n testados (linha = grupo, tem n_total)
    - "proporcao"    : proporção/porcentagem contínua (severidade %), 0..1 ou 0..100
    - "contagem"     : inteiros não-negativos (nº de colônias, nº de insetos)
    - "continua"     : medida contínua (diâmetro, peso, taxa de crescimento)

E o desenho em:

    - tem_dose       : existe preditor quantitativo (dose/concentração) -> dose-resposta
    - n_fatores      : quantidade de fatores categóricos
    - tem_bloco      : existe coluna de bloco
    - balanceado     : repetições iguais entre tratamentos
"""

from __future__ import annotations

import math
import numpy as np


def _numerico(serie):
    """Tenta converter para float; devolve array (com NaN) e fração convertida."""
    vals = []
    ok = 0
    for v in serie:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            vals.append(np.nan)
            continue
        s = str(v).strip().replace(",", ".")
        if s == "" or s.lower() in ("na", "nan", "null", "none"):
            vals.append(np.nan)
            continue
        try:
            vals.append(float(s))
            ok += 1
        except ValueError:
            vals.append(np.nan)
    arr = np.array(vals, dtype=float)
    n_validos = np.sum([1 for v in serie if str(v).strip() != ""])
    frac = ok / n_validos if n_validos else 0.0
    return arr, frac


# Vocabulário comum em bioensaios (PT/EN) para reconhecer respostas binárias
_VIVO = {"vivo", "vivos", "alive", "live", "sadio", "saudavel", "saudável",
         "ausente", "ausencia", "ausência", "negativo", "sem", "nao", "não",
         "n", "no", "0", "s", "sobrevivente"}
_MORTO = {"morto", "mortos", "dead", "morte", "doente", "presente", "presenca",
          "presença", "positivo", "com", "sim", "y", "yes", "1", "infectado"}


def _eh_binario_categorico(serie):
    """Detecta respostas tipo morto/vivo, sim/não, presença/ausência."""
    nivels = set()
    for v in serie:
        s = str(v).strip().lower()
        if s == "" or s in ("na", "nan", "none", "null"):
            continue
        nivels.add(s)
    if len(nivels) != 2:
        return False, None
    a, b = list(nivels)
    grupo_morto = _MORTO
    grupo_vivo = _VIVO
    if (a in grupo_morto and b in grupo_vivo) or (a in grupo_vivo and b in grupo_morto):
        positivo = a if a in grupo_morto else b
        return True, positivo
    return False, None


# Palavras que indicam que uma variável 0–100 é, de fato, porcentagem/proporção
_NOME_PROPORCAO = ("sever", "incid", "porc", "percent", "%", "mortal", "morte",
                   "infec", "germin", "viab", "efic", "control", "dano",
                   "desfolh", "necros", "esporul", "prop", "taxa")
# Palavras típicas de medidas contínuas (têm prioridade sobre proporção)
_NOME_CONTINUA = ("diam", "diâm", "compr", "larg", "altura", "peso", "massa",
                  "mm", "cm", "area", "área", "tamanho", "volume", "ph",
                  "temperatura", "umidade", "cresc", "biomassa", "comprimento")


def _nome_sugere(nome, palavras):
    if not nome:
        return False
    n = str(nome).lower()
    return any(p in n for p in palavras)


def detectar_resposta(serie, n_total=None, nome=None):
    """
    Classifica a variável-resposta.

    serie    : lista de valores da coluna resposta
    n_total  : lista (opcional) com o nº de indivíduos testados por linha
               (quando presente e a resposta é contagem de "sucessos",
               trata-se de dados binomiais x/n).
    nome     : nome da coluna (usado para desambiguar 0–100: porcentagem vs
               medida contínua como diâmetro/peso).

    Retorna dict com chaves: tipo, detalhe, valores (np.array float quando
    aplicável), positivo (rótulo tido como "evento" em dados binários).
    """
    # 1) binário categórico (texto morto/vivo, sim/não)
    eh_bin, positivo = _eh_binario_categorico(serie)
    if eh_bin:
        vals = np.array(
            [1.0 if str(v).strip().lower() == positivo else
             (np.nan if str(v).strip().lower() in ("", "na", "nan", "none", "null")
              else 0.0)
             for v in serie],
            dtype=float,
        )
        return {"tipo": "binario", "detalhe": f"resposta binária (evento = '{positivo}')",
                "valores": vals, "positivo": positivo}

    arr, frac = _numerico(serie)
    validos = arr[~np.isnan(arr)]

    if validos.size == 0:
        return {"tipo": "desconhecido", "detalhe": "coluna sem valores numéricos válidos",
                "valores": arr, "positivo": None}

    # 2) com n_total -> dados binomiais x de n
    if n_total is not None:
        nt, _ = _numerico(n_total)
        return {"tipo": "binomial",
                "detalhe": "sucessos de um total (x de n) -> regressão binomial",
                "valores": arr, "n_total": nt, "positivo": "evento"}

    todos_inteiros = np.all(np.isclose(validos, np.round(validos)))
    minimo, maximo = float(np.min(validos)), float(np.max(validos))
    distintos = np.unique(validos)

    # 3) binário 0/1 numérico
    if set(distintos.tolist()).issubset({0.0, 1.0}):
        return {"tipo": "binario", "detalhe": "resposta binária 0/1",
                "valores": arr, "positivo": "1"}

    # 4) proporção / porcentagem (severidade)
    nome_continua = _nome_sugere(nome, _NOME_CONTINUA)
    nome_proporcao = _nome_sugere(nome, _NOME_PROPORCAO)

    #    - 0..1 contínuo é forte indício de proporção (a menos que o nome diga o contrário)
    if (0.0 <= minimo and maximo <= 1.0 and not todos_inteiros and distintos.size > 2
            and not nome_continua):
        return {"tipo": "proporcao", "detalhe": "proporção contínua (0–1), ex.: severidade",
                "valores": arr, "escala": "0-1", "positivo": None}
    #    - 0..100: só é porcentagem se o NOME sugerir (severidade, %, mortalidade…).
    #      Caso contrário (ex.: diâmetro em mm) é medida contínua.
    if (0.0 <= minimo and maximo <= 100.0 and maximo > 1.0 and not todos_inteiros
            and nome_proporcao and not nome_continua):
        return {"tipo": "proporcao", "detalhe": "porcentagem (0–100), ex.: % de severidade",
                "valores": arr, "escala": "0-100", "positivo": None}

    # 5) contagem (inteiros >= 0)
    if todos_inteiros and minimo >= 0 and maximo > 1:
        return {"tipo": "contagem",
                "detalhe": "contagem (inteiros ≥ 0), ex.: nº de colônias/insetos",
                "valores": arr, "positivo": None}

    # 6) contínua
    return {"tipo": "continua",
            "detalhe": "medida contínua, ex.: diâmetro, peso, taxa de crescimento",
            "valores": arr, "positivo": None}


def _parece_percentual(validos):
    """Heurística: dados entre 0 e 100 que provavelmente são porcentagem."""
    # se há valores acima de 1 e até 100, e a amplitude sugere escala percentual
    return np.max(validos) <= 100.0 and np.max(validos) > 1.0


def detectar_desenho(dose=None, fatores=None, bloco=None):
    """
    Classifica o desenho experimental.

    dose    : lista (opcional) de doses/concentrações (preditor quantitativo)
    fatores : lista de listas (cada uma é um fator categórico) OU None
    bloco   : lista (opcional) com identificação de bloco
    """
    info = {"tem_dose": False, "n_fatores": 0, "tem_bloco": bloco is not None,
            "n_niveis": [], "balanceado": None}

    if dose is not None:
        d, frac = _numerico(dose)
        d = d[~np.isnan(d)]
        if frac > 0.8 and np.unique(d).size >= 3:
            info["tem_dose"] = True
            info["n_doses"] = int(np.unique(d).size)

    if fatores:
        info["n_fatores"] = len(fatores)
        contagens = []
        for f in fatores:
            niveis = {}
            for v in f:
                s = str(v).strip()
                if s == "":
                    continue
                niveis[s] = niveis.get(s, 0) + 1
            info["n_niveis"].append(len(niveis))
            contagens.append(sorted(niveis.values()))
        # balanceado se todas as contagens do(s) fator(es) forem iguais
        bal = all(len(set(c)) <= 1 for c in contagens) if contagens else None
        info["balanceado"] = bal

    return info
