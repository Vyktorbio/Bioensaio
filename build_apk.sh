#!/usr/bin/env bash
# Build do APK do BioEnsaio em macOS, instalando o toolchain isoladamente.
# Uso: ./build_apk.sh        (operação pesada: ~2-3 GB de download na 1ª vez)
set -euo pipefail

PROJ="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$HOME/.bioensaio-toolchain"
mkdir -p "$TOOLS"
ARCH="$(uname -m)"   # arm64 ou x86_64

say(){ printf "\n\033[1;32m▶ %s\033[0m\n" "$*"; }

# ---------- Node ----------
if ! command -v node >/dev/null 2>&1; then
  say "Instalando Node.js…"
  NODE_V="20.17.0"
  case "$ARCH" in arm64) NA=darwin-arm64;; *) NA=darwin-x64;; esac
  curl -fsSL "https://nodejs.org/dist/v${NODE_V}/node-v${NODE_V}-${NA}.tar.gz" -o "$TOOLS/node.tgz"
  rm -rf "$TOOLS/node" && mkdir -p "$TOOLS/node"
  tar -xzf "$TOOLS/node.tgz" -C "$TOOLS/node" --strip-components=1
  export PATH="$TOOLS/node/bin:$PATH"
fi
say "node $(node -v)"

# ---------- JDK 17 ----------
if ! /usr/libexec/java_home -v 17 >/dev/null 2>&1; then
  say "Instalando JDK 17 (Temurin)…"
  case "$ARCH" in arm64) JA=aarch64;; *) JA=x64;; esac
  curl -fsSL "https://api.adoptium.net/v3/binary/latest/17/ga/mac/${JA}/jdk/hotspot/normal/eclipse" -o "$TOOLS/jdk.tgz"
  rm -rf "$TOOLS/jdk" && mkdir -p "$TOOLS/jdk"
  tar -xzf "$TOOLS/jdk.tgz" -C "$TOOLS/jdk" --strip-components=1
  export JAVA_HOME="$TOOLS/jdk/Contents/Home"
else
  export JAVA_HOME="$(/usr/libexec/java_home -v 17)"
fi
export PATH="$JAVA_HOME/bin:$PATH"
say "java $(java -version 2>&1 | head -1)"

# ---------- Android SDK ----------
export ANDROID_HOME="$TOOLS/android-sdk"
if [ ! -d "$ANDROID_HOME/cmdline-tools/latest" ]; then
  say "Instalando Android SDK (command-line tools)…"
  curl -fsSL "https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip" -o "$TOOLS/cmdtools.zip"
  rm -rf "$TOOLS/cmdtools" && unzip -q "$TOOLS/cmdtools.zip" -d "$TOOLS/cmdtools"
  mkdir -p "$ANDROID_HOME/cmdline-tools/latest"
  cp -r "$TOOLS/cmdtools/cmdline-tools/"* "$ANDROID_HOME/cmdline-tools/latest/"
fi
export PATH="$ANDROID_HOME/cmdline-tools/latest/bin:$ANDROID_HOME/platform-tools:$PATH"
say "Aceitando licenças e instalando pacotes do SDK…"
yes | sdkmanager --licenses >/dev/null 2>&1 || true
sdkmanager "platform-tools" "platforms;android-34" "build-tools;34.0.0" >/dev/null

# ---------- Capacitor build ----------
cd "$PROJ"
say "npm install…"
npm install
if [ ! -d "$PROJ/android" ]; then
  say "npx cap add android…"
  npx cap add android
fi
say "npx cap sync android…"
npx cap sync android
say "Gerando APK (gradlew assembleDebug)…"
cd "$PROJ/android"
./gradlew assembleDebug

APK="$PROJ/android/app/build/outputs/apk/debug/app-debug.apk"
say "PRONTO! APK gerado em:"
echo "$APK"
ls -lh "$APK" || true
