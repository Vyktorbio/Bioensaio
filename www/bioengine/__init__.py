"""
BioEngine — motor estatístico para bioensaios.

Detecta o tipo de dado, escolhe a análise adequada (dose-resposta,
ANOVA, GLM de contagem/proporção) e devolve um relatório estruturado
com diagnósticos, modelo escolhido (e justificativa) e comparação de
médias com letras (Tukey / Scott-Knott).

O mesmo código roda em CPython (para validação) e no navegador/Android
via Pyodide.
"""

from .decide import analisar

__all__ = ["analisar"]
__version__ = "0.1.0"
