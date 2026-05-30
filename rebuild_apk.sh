#!/usr/bin/env bash
# Recompila o APK reaproveitando o toolchain já instalado por build_apk.sh.
# Mais rápido (não baixa nada). Uso: ./rebuild_apk.sh
set -euo pipefail
PROJ="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$HOME/.bioensaio-toolchain"

export PATH="$TOOLS/node/bin:$PATH"
export JAVA_HOME="${JAVA_HOME:-$TOOLS/jdk/Contents/Home}"
export PATH="$JAVA_HOME/bin:$PATH"
export ANDROID_HOME="$TOOLS/android-sdk"
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"

cd "$PROJ"
echo "▶ Sincronizando www → android…"
npx cap sync android
echo "▶ Compilando APK…"
cd android && ./gradlew assembleDebug
APK="$PROJ/android/app/build/outputs/apk/debug/app-debug.apk"
cp "$APK" "$PROJ/dist/BioEnsaio.apk"
echo "✅ APK atualizado: $PROJ/dist/BioEnsaio.apk"
ls -lh "$PROJ/dist/BioEnsaio.apk"
