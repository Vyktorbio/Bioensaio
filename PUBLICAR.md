# Publicar o BioEnsaio no GitHub Pages

O projeto já está com git inicializado, commit feito na branch `main`, e um
workflow de deploy automático (`.github/workflows/deploy.yml`). Falta só você
criar o repositório no GitHub e dar `push`.

## Passo a passo (≈ 3 minutos)

1. **Crie um repositório vazio** em https://github.com/new
   - Nome sugerido: `bioensaio`
   - **Não** marque "Add README/.gitignore/license" (deixe vazio)
   - Pode ser **público** (Pages grátis) ou privado (Pages exige conta paga em alguns casos)

2. **Conecte e envie** (troque `SEU_USUARIO`):
   ```bash
   cd "/Users/victorchavesmachado/Documents/Claude/Projects/bioestat"
   git remote add origin https://github.com/SEU_USUARIO/bioensaio.git
   git push -u origin main
   ```

3. **Ative o Pages**: no repositório → **Settings → Pages** →
   em **Build and deployment → Source**, escolha **GitHub Actions**.
   (O workflow já está no repo; ele roda sozinho a cada push.)

4. **Aguarde ~1–2 min** (aba **Actions** mostra o progresso). Ao terminar, seu
   site fica em:
   ```
   https://SEU_USUARIO.github.io/bioensaio/
   ```

5. **Atualizar no futuro**: é só `git commit` + `git push` — o site se atualiza
   sozinho.

## O que é publicado
A versão **web leve** (`web-deploy/`, ~1,6 MB): carrega o Pyodide do CDN
(numpy/scipy/statsmodels) na 1ª visita e guarda em cache. Funciona em qualquer
navegador, instala como PWA ("Adicionar à tela inicial") e funciona offline
depois do primeiro acesso. O bundle pesado (`www/pyodide/`, 115 MB) **não** vai
para o repositório — ele só é usado para gerar o APK offline localmente.

## Bônus: gerar APK a partir do site (sem ferramentas locais)
Com o site no ar, abra **https://www.pwabuilder.com**, cole a URL
`https://SEU_USUARIO.github.io/bioensaio/`, e gere um **APK assinado** em Android →
Generate Package.

## Rodar a versão web localmente (teste)
```bash
cd web-deploy && python3 -m http.server 8000   # abra http://localhost:8000
```
