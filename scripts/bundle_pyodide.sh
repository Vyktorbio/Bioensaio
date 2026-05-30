#!/usr/bin/env bash
# Baixa o Pyodide + os pacotes científicos para www/pyodide/ (offline total).
# Depois, em app.js, troque  loadPyodide()  por  loadPyodide({ indexURL: "pyodide/" }).
set -euo pipefail
V="0.26.2"
DEST="$(cd "$(dirname "$0")/.." && pwd)/www/pyodide"
mkdir -p "$DEST"
BASE="https://cdn.jsdelivr.net/pyodide/v${V}/full"

# arquivos núcleo + pacotes necessários (numpy/scipy/pandas/statsmodels e dependências)
ARQ=(
  pyodide.js pyodide.asm.js pyodide.asm.wasm pyodide.mjs
  python_stdlib.zip pyodide-lock.json
)
echo "Baixando núcleo do Pyodide v$V…"
for f in "${ARQ[@]}"; do
  echo "  $f"; curl -fsSL "$BASE/$f" -o "$DEST/$f"
done

# Os wheels (.whl/.zip) são listados em pyodide-lock.json; baixe os necessários.
echo "Baixando pacotes (numpy, scipy, pandas, statsmodels, patsy, openblas…)…"
PKGS=$(python3 - "$DEST/pyodide-lock.json" <<'PY'
import json,sys
lock=json.load(open(sys.argv[1]))
alvo={"numpy","scipy","pandas","statsmodels","patsy","openblas","python-dateutil","pytz","six","packaging"}
seen=set()
def add(name):
    name=name.lower()
    if name in seen: return
    seen.add(name)
    info=lock["packages"].get(name)
    if not info: return
    print(info["file_name"])
    for d in info.get("depends",[]): add(d)
for a in alvo: add(a)
PY
)
for w in $PKGS; do
  echo "  $w"; curl -fsSL "$BASE/$w" -o "$DEST/$w"
done
echo "Pronto. Pyodide offline em: $DEST"
echo "Edite www/app.js: loadPyodide({ indexURL: \"pyodide/\" })"
