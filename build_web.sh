#!/usr/bin/env bash
# Gera uma versão WEB leve (Pyodide via CDN, sem o bundle de 115 MB) pronta para
# publicar (Netlify Drop, GitHub Pages, Vercel…). Saída: web-deploy/ + dist/BioEnsaio-web.zip
set -euo pipefail
PROJ="$(cd "$(dirname "$0")" && pwd)"
SRC="$PROJ/www"; OUT="$PROJ/web-deploy"
V="0.26.2"

rm -rf "$OUT"; mkdir -p "$OUT" "$PROJ/dist"
# copia tudo menos o bundle pesado do Pyodide
rsync -a --exclude 'pyodide' "$SRC/" "$OUT/"

# index.html: Pyodide local -> CDN  (perl = portável mac/Linux p/ o CI)
perl -0pi -e "s#<script src=\"pyodide/pyodide\.js\"></script>#<script src=\"https://cdn.jsdelivr.net/pyodide/v${V}/full/pyodide.js\"></script>#" "$OUT/index.html"

# app.js: loadPyodide local -> CDN (sem indexURL)
perl -0pi -e 's#loadPyodide\(\{ indexURL: "pyodide/" \}\)#loadPyodide()#' "$OUT/app.js"

# evita o Jekyll do GitHub Pages mexer nos arquivos
touch "$OUT/.nojekyll"

# zip para arrastar no Netlify Drop
rm -f "$PROJ/dist/BioEnsaio-web.zip"
( cd "$OUT" && zip -qr "$PROJ/dist/BioEnsaio-web.zip" . )

echo "✅ web-deploy pronto: $OUT  ($(du -sh "$OUT" | cut -f1))"
echo "✅ zip: $PROJ/dist/BioEnsaio-web.zip  ($(du -h "$PROJ/dist/BioEnsaio-web.zip" | cut -f1))"
