# Gerar o app Android (.apk) do BioEnsaio

O app já é uma **PWA** completa e offline. Para transformá-lo num arquivo **.apk**
(instalável/compartilhável), há três caminhos — do mais fácil ao mais flexível.

---

## Caminho 1 — PWABuilder (sem instalar nada) ⭐ recomendado para um APK rápido

1. Publique a pasta `www/` em qualquer hospedagem estática grátis (precisa ser **https**):
   - **Netlify Drop**: arraste a pasta `www/` em https://app.netlify.com/drop
   - ou **GitHub Pages**, **Vercel**, **Cloudflare Pages**…
2. Abra **https://www.pwabuilder.com**, cole a URL publicada e clique em **Start**.
3. Em **Android** → **Generate Package**. Baixe o `.zip`.
4. Dentro vem o **`app-release-signed.apk`** (e a chave de assinatura — guarde-a).
5. Envie o `.apk` para o celular e instale (permita "fontes desconhecidas").

> Vantagem: zero instalação local. Gera um APK assinado, baseado em Trusted Web Activity.
> O app abre em tela cheia e funciona offline depois do primeiro acesso com internet.

---

## Caminho 2 — Capacitor (controle total, gera projeto Android nativo)

Pré-requisitos (uma vez):
- **Node.js 18+**, **JDK 17**, **Android SDK** (platform-tools, platform android-34,
  build-tools 34). Defina `ANDROID_HOME` e `JAVA_HOME`.

Passos (na raiz do projeto):
```bash
npm install                 # instala @capacitor/*
npx cap add android         # cria a pasta android/ (projeto Gradle)
npx cap sync android        # copia www/ para o projeto
cd android
./gradlew assembleDebug     # gera o APK de depuração
# APK em: android/app/build/outputs/apk/debug/app-debug.apk
```
Para um APK de release assinado, gere uma keystore e use `assembleRelease`
(veja a doc do Capacitor / Android).

---

## Caminho 3 — Script automatizado `build_apk.sh`

Para macOS **sem** as ferramentas instaladas, o script baixa Node, JDK 17 e o Android
SDK (em `~/.bioensaio-toolchain`), aceita as licenças e roda o build do Capacitor:
```bash
./build_apk.sh
```
> É uma operação pesada (~2–3 GB de download na 1ª vez). Use uma boa conexão.
> Ao final, informa o caminho do `.apk`.

---

## Offline 100% desde a instalação (avançado)

Por padrão o app baixa as bibliotecas do Pyodide (numpy/scipy/statsmodels) na **primeira
abertura com internet** e as guarda em cache para uso offline. Para embutir tudo no APK
(funcionar offline já na 1ª abertura), baixe a distribuição do Pyodide para `www/pyodide/`
e aponte `loadPyodide({ indexURL: "pyodide/" })` em `app.js`. Veja `scripts/bundle_pyodide.sh`.
```
