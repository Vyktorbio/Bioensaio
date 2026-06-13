/* BioEnsaio — lógica da interface + ponte com o motor Python (Pyodide) */
"use strict";

const ARQ_ENGINE = ["__init__.py","detect.py","diagnostics.py","doseresponse.py",
                    "posthoc.py","anova.py","glmcount.py","decide.py","tempo.py"];

const BRIDGE = `
import json, math
import numpy as np
from bioengine import analisar

def _clean(o):
    if o is None or isinstance(o,(bool,int,str)): return o
    if isinstance(o,(np.bool_,)): return bool(o)
    if isinstance(o,(np.integer,)): return int(o)
    if isinstance(o,(np.floating,float)):
        f=float(o); return f if math.isfinite(f) else None
    if isinstance(o,(np.str_,)): return str(o)
    if isinstance(o,np.ndarray): return [_clean(x) for x in o.tolist()]
    if isinstance(o,(set,frozenset)): return [_clean(x) for x in o]
    if isinstance(o,dict):
        return {(k if isinstance(k,str) else str(_clean(k))):_clean(v) for k,v in o.items()}
    if isinstance(o,(list,tuple)): return [_clean(x) for x in o]
    return str(o)

def _run_web(dados_json, papeis_json, opcoes_json):
    dados=json.loads(dados_json); papeis=json.loads(papeis_json); opcoes=json.loads(opcoes_json)
    papeis={k:v for k,v in papeis.items() if v not in (None,"",[])}
    if "fatores" in papeis and not papeis["fatores"]: del papeis["fatores"]
    try:
        rel=analisar(dados,papeis,opcoes)
    except Exception as e:
        import traceback
        rel={"ok":False,"erro":str(e),"trace":traceback.format_exc()}
    return json.dumps(_clean(rel))

def _run_tempo(dados_json, papeis_json, opcoes_json):
    from bioengine import tempo as _T
    dados=json.loads(dados_json); papeis=json.loads(papeis_json); opcoes=json.loads(opcoes_json)
    papeis={k:v for k,v in papeis.items() if v not in (None,"",[])}
    try:
        rel=_T.analisar_tempo(dados,papeis,opcoes)
    except Exception as e:
        import traceback
        rel={"ok":False,"erro":str(e),"trace":traceback.format_exc()}
    return json.dumps(_clean(rel))
`;

let pyodide = null;
let pyPronto = null;          // promessa de inicialização
let COLUNAS = [];             // [{nome, valores:[...]}]
let MODO = "analise";         // "analise" | "tempo"
let MATRIZ_IMPORT = null;     // linhas normalizadas da planilha exportada pelo Matriz

const $ = (s) => document.querySelector(s);
const el = (t, c, txt) => { const e=document.createElement(t); if(c)e.className=c; if(txt!=null)e.textContent=txt; return e; };
let toastTimer = null;

function esc(v){
  return String(v == null ? "" : v).replace(/[&<>"']/g, ch => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  }[ch]));
}
function avisar(msg, tipo="erro"){
  const box = $("#toast");
  if(!box) return;
  clearTimeout(toastTimer);
  box.textContent = msg;
  box.className = "toast " + (tipo === "ok" ? "toast-ok" : "toast-erro");
  toastTimer = setTimeout(()=>box.classList.add("oculto"), 4200);
}

/* ----------------------------------------------------------------------- */
/* Inicialização do Pyodide + motor                                        */
/* ----------------------------------------------------------------------- */
async function iniciarPyodide() {
  try {
    mostrarOverlay("Carregando motor estatístico…", "Inicializando bibliotecas científicas.");
    pyodide = await loadPyodide({ indexURL: "pyodide/" });
    window.__pyodide = pyodide;
    setOverlay("Carregando bibliotecas…", "numpy, scipy, pandas, statsmodels");
    await pyodide.loadPackage(["numpy", "scipy", "pandas", "statsmodels"]);
    setOverlay("Preparando o motor…", "");
    const arquivos = {};
    for (const f of ARQ_ENGINE) {
      const r = await fetch("bioengine/" + f, { cache: "no-store" });
      if (!r.ok) throw new Error("HTTP " + r.status + " em bioengine/" + f);
      arquivos[f] = await r.text();
    }
    const proxy = pyodide.toPy(arquivos);
    pyodide.globals.set("_engine_files", proxy);
    pyodide.runPython(`
import os, sys
os.makedirs("bioengine", exist_ok=True)
for _nome, _conteudo in dict(_engine_files).items():
    with open(os.path.join("bioengine", _nome), "w") as _fh:
        _fh.write(_conteudo)
if "" not in sys.path:
    sys.path.insert(0, "")
`);
    proxy.destroy();
    pyodide.runPython(BRIDGE);
    esconderOverlay();
  } catch (e) {
    console.error("iniciarPyodide:", e);
    setOverlay("Erro ao carregar o motor", String((e && e.message) || e));
    throw e;
  }
}
function garantirPyodide(){ if(!pyPronto) pyPronto = iniciarPyodide(); return pyPronto; }

/* ----------------------------------------------------------------------- */
/* Overlay                                                                 */
/* ----------------------------------------------------------------------- */
function mostrarOverlay(msg, sub){ $("#overlay-msg").textContent=msg; $("#overlay-sub").textContent=sub||""; $("#overlay").classList.remove("oculto"); }
function setOverlay(msg, sub){ $("#overlay-msg").textContent=msg; if(sub!=null)$("#overlay-sub").textContent=sub; }
function esconderOverlay(){ $("#overlay").classList.add("oculto"); }

/* ----------------------------------------------------------------------- */
/* Navegação principal                                                     */
/* ----------------------------------------------------------------------- */
function navItem(nome){ return document.querySelector(`.appnav-item[data-nav="${nome}"]`); }
function setNavAtivo(nome){
  document.querySelectorAll(".appnav-item").forEach(a=>a.classList.toggle("ativo", a.dataset.nav===nome));
}
function setNavTravado(nome, travado){
  const item=navItem(nome); if(!item) return;
  item.classList.toggle("travado", !!travado);
  item.setAttribute("aria-disabled", travado ? "true" : "false");
}
function atualizarNav(){
  const temDados = COLUNAS.length > 0;
  const temResultados = !$("#card-resultados").classList.contains("oculto") && $("#resultados").children.length > 0;
  setNavTravado("papeis", !temDados);
  setNavTravado("resultados", !temResultados);
}
function irPara(secao){
  if(secao==="dados"){
    setNavAtivo("dados");
    $("#card-dados").scrollIntoView({behavior:"smooth", block:"start"});
    return;
  }
  if(secao==="papeis"){
    if(!COLUNAS.length){ setNavAtivo("dados"); $("#card-dados").scrollIntoView({behavior:"smooth", block:"start"}); return; }
    setNavAtivo("papeis");
    $("#card-papeis").scrollIntoView({behavior:"smooth", block:"start"});
    return;
  }
  if(secao==="geral" || secao==="tempo"){
    setModo(secao==="tempo" ? "tempo" : "analise");
    setNavAtivo(secao);
    const alvo = secao==="tempo" ? $("#card-opcoes-tempo") : $("#card-opcoes");
    (COLUNAS.length ? alvo : $("#card-dados")).scrollIntoView({behavior:"smooth", block:"start"});
    return;
  }
  if(secao==="resultados"){
    if($("#card-resultados").classList.contains("oculto")) return;
    setNavAtivo("resultados");
    $("#card-resultados").scrollIntoView({behavior:"smooth", block:"start"});
  }
}
document.querySelectorAll(".appnav-item").forEach(a=>a.addEventListener("click", e=>{
  e.preventDefault();
  if(a.classList.contains("travado")){
    if(a.dataset.nav==="resultados" && COLUNAS.length){ irPara(MODO==="tempo" ? "tempo" : "geral"); return; }
    irPara("dados");
    return;
  }
  irPara(a.dataset.nav);
}));

/* ----------------------------------------------------------------------- */
/* Tabs                                                                    */
/* ----------------------------------------------------------------------- */
document.querySelectorAll(".tab").forEach(t => t.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach(x=>x.classList.remove("ativo"));
  t.classList.add("ativo");
  document.querySelectorAll(".painel").forEach(p=>p.classList.add("oculto"));
  document.querySelector(`.painel[data-painel="${t.dataset.modo}"]`).classList.remove("oculto");
}));

/* ----------------------------------------------------------------------- */
/* Modo: Análise geral × Mortalidade no tempo                              */
/* ----------------------------------------------------------------------- */
function setModo(m){
  MODO = m;
  document.querySelectorAll(".analysis-mode[data-modo]").forEach(a=>
    a.classList.toggle("ativo", a.dataset.modo===m));
  $("#card-opcoes").classList.toggle("oculto", m!=="analise");
  $("#card-opcoes-tempo").classList.toggle("oculto", m!=="tempo");
  $("#card-resultados").classList.add("oculto");
  setNavTravado("resultados", true);
  if(COLUNAS.length){ renderPapeis(MODO==="tempo"?adivinharPapeisTempo():adivinharPapeis()); }
  preencherExemplosPorModo();
  atualizarPipeline();
  if(navItem("geral")) setNavAtivo(m==="tempo" ? "tempo" : "geral");
}
document.querySelectorAll(".analysis-mode[data-modo]").forEach(a=>
  a.addEventListener("click", (e)=>{ e.preventDefault(); setModo(a.dataset.modo); }));
if(location.hash==="#tempo") setModo("tempo");
atualizarNav();

/* ----------------------------------------------------------------------- */
/* Parsing                                                                 */
/* ----------------------------------------------------------------------- */
function detectarSeparador(texto){
  const l = texto.split(/\r?\n/).find(x=>x.trim()!=="") || "";
  if (l.includes("\t")) return "\t";
  if ((l.match(/;/g)||[]).length >= (l.match(/,/g)||[]).length) return ";";
  return ",";
}
function parseTexto(texto){
  const sep = detectarSeparador(texto);
  const linhas = texto.split(/\r?\n/).filter(x=>x.trim()!=="");
  if (!linhas.length) throw new Error("Sem dados.");
  const matriz = linhas.map(l => l.split(sep).map(c=>c.trim()));
  return matriz;
}
function matrizParaColunas(matriz){
  const headers = matriz[0].map((h,i)=> h==="" ? `col${i+1}` : h);
  const corpo = matriz.slice(1);
  return headers.map((nome,i)=>({ nome, valores: corpo.map(l => l[i]!==undefined ? l[i] : "") }));
}

/* Colar */
$("#btn-colar").addEventListener("click", () => {
  try { carregarColunas(matrizParaColunas(parseTexto($("#entrada-colar").value))); }
  catch(e){ avisar("Não consegui ler: " + e.message); }
});

/* Arquivo */
$("#entrada-arquivo").addEventListener("change", async (ev) => {
  const file = ev.target.files[0]; if(!file) return;
  try {
    const buf = await file.arrayBuffer();
    const wb = XLSX.read(buf, {type:"array"});
    const ws = wb.Sheets[wb.SheetNames[0]];
    const aoa = XLSX.utils.sheet_to_json(ws, {header:1, blankrows:false, defval:""});
    if (!aoa.length) throw new Error("planilha vazia");
    carregarColunas(matrizParaColunas(aoa.map(r=>r.map(c=>c===null?"":String(c)))));
  } catch(e){ avisar("Erro ao ler arquivo: " + e.message); }
});

/* Importar planilha exportada pelo Matriz */
function normCab(s){
  return String(s||"").trim().toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g,"")
    .replace(/[^a-z0-9]+/g,"_").replace(/^_+|_+$/g,"");
}
function valorLinha(row, nomes){
  for(const nome of nomes){
    const k=normCab(nome);
    if(Object.prototype.hasOwnProperty.call(row,k)) return row[k];
  }
  return "";
}
function numBR(v){
  if(v==null || v==="") return NaN;
  if(typeof v==="number") return v;
  let s=String(v).trim();
  if(!s) return NaN;
  if(s.includes(",") && s.includes(".")) s=s.replace(/\./g,"").replace(",",".");
  else s=s.replace(",",".");
  const n=parseFloat(s);
  return Number.isFinite(n) ? n : NaN;
}
function textoLimpo(v){ return String(v==null?"":v).trim(); }
function linhasMatrizDeAoa(aoa){
  const idx=aoa.findIndex(r=>{
    const ns=(r||[]).map(normCab);
    return ns.includes("tratamento") && ns.includes("variavel") && ns.includes("valor");
  });
  if(idx<0) throw new Error("Não achei cabeçalho do Matriz. Preciso de Tratamento, Variavel e Valor.");
  const headers=aoa[idx].map(normCab);
  const linhas=[];
  aoa.slice(idx+1).forEach((r,i)=>{
    const obj={_linha:i+idx+2};
    headers.forEach((h,j)=>{ if(h) obj[h]=r[j]; });
    const valor=numBR(valorLinha(obj,["Valor"]));
    const trat=textoLimpo(valorLinha(obj,["Tratamento"]));
    const variavel=textoLimpo(valorLinha(obj,["Variavel","Variável"]));
    if(!trat || !variavel || !Number.isFinite(valor)) return;
    linhas.push({
      local:textoLimpo(valorLinha(obj,["Local"])),
      quadra:textoLimpo(valorLinha(obj,["Quadra"])),
      cultura:textoLimpo(valorLinha(obj,["Cultura"])),
      estudo:textoLimpo(valorLinha(obj,["Estudo"])),
      descricao:textoLimpo(valorLinha(obj,["Descricao","Descrição"])),
      data:textoLimpo(valorLinha(obj,["Data_avaliacao","Data avaliação","Data_avaliação"])),
      tipo:textoLimpo(valorLinha(obj,["Tipo"])),
      bbch:textoLimpo(valorLinha(obj,["BBCH"])),
      tratamento:trat,
      repeticao:textoLimpo(valorLinha(obj,["Repeticao","Repetição","Bloco"])) || "1",
      produto:textoLimpo(valorLinha(obj,["Produto"])),
      variavel:variavel,
      valor:valor
    });
  });
  return linhas;
}
function matrizKey(r){ return [r.local,r.quadra,r.estudo,r.descricao].join("||"); }
function matrizLabel(key){
  const r=(MATRIZ_IMPORT&&MATRIZ_IMPORT.linhas||[]).find(x=>matrizKey(x)===key);
  if(!r) return key || "(sem estudo)";
  const partes=[r.estudo||"(sem estudo)", r.quadra, r.local].filter(Boolean);
  return partes.join(" - ");
}
function unicoOrdenado(arr){
  return [...new Set(arr.filter(v=>String(v).trim()!==""))].sort((a,b)=>String(a).localeCompare(String(b), "pt-BR", {numeric:true}));
}
function addOpcao(sel, valor, texto){
  const o=el("option"); o.value=valor; o.textContent=texto==null?valor:texto; sel.appendChild(o);
}
function matrizLinhasFiltradas(){
  if(!MATRIZ_IMPORT) return [];
  const estudo=$("#matriz-estudo") ? $("#matriz-estudo").value : "";
  const data=$("#matriz-data") ? $("#matriz-data").value : "";
  const variavel=$("#matriz-variavel") ? $("#matriz-variavel").value : "";
  return MATRIZ_IMPORT.linhas.filter(r=>
    (!estudo || matrizKey(r)===estudo) &&
    (!data || r.data===data) &&
    (!variavel || r.variavel===variavel)
  );
}
function atualizarMatrizFiltros(){
  if(!MATRIZ_IMPORT) return;
  const linhas=MATRIZ_IMPORT.linhas;
  const estudoSel=$("#matriz-estudo"), dataSel=$("#matriz-data"), varSel=$("#matriz-variavel");
  if(!estudoSel || !dataSel || !varSel) return;

  const estudo=estudoSel.value;
  const datas=unicoOrdenado(linhas.filter(r=>!estudo || matrizKey(r)===estudo).map(r=>r.data));
  const dataAtual=dataSel.value;
  dataSel.innerHTML="";
  datas.forEach(d=>addOpcao(dataSel,d,d));
  if(datas.includes(dataAtual)) dataSel.value=dataAtual;

  const data=dataSel.value;
  const vars=unicoOrdenado(linhas.filter(r=>
    (!estudo || matrizKey(r)===estudo) && (!data || r.data===data)
  ).map(r=>r.variavel));
  const varAtual=varSel.value;
  varSel.innerHTML="";
  vars.forEach(v=>addOpcao(varSel,v,v));
  if(vars.includes(varAtual)) varSel.value=varAtual;
  atualizarMatrizPreview();
}
function atualizarMatrizPreview(){
  const out=$("#matriz-preview"); if(!out) return;
  const linhas=matrizLinhasFiltradas();
  const trats=unicoOrdenado(linhas.map(r=>r.tratamento));
  const reps=unicoOrdenado(linhas.map(r=>r.repeticao));
  out.innerHTML="";
  out.appendChild(el("p","dica",`${linhas.length} valores prontos - ${trats.length} tratamento(s) x ${reps.length} repetição(ões).`));
  if(linhas.length){
    const tab=el("table");
    const thead=el("thead"), htr=el("tr");
    ["tratamento","bloco","valor","produto"].forEach(h=>htr.appendChild(el("th",null,h)));
    thead.appendChild(htr); tab.appendChild(thead);
    const tb=el("tbody");
    linhas.slice(0,6).forEach(r=>{
      const tr=el("tr");
      [r.tratamento,r.repeticao,String(r.valor),r.produto].forEach(v=>tr.appendChild(el("td",null,v)));
      tb.appendChild(tr);
    });
    tab.appendChild(tb);
    const rol=el("div","tab-rolavel"); rol.appendChild(tab); out.appendChild(rol);
  }
}
function renderMatrizImportador(){
  const box=$("#matriz-importador"); if(!box || !MATRIZ_IMPORT) return;
  box.innerHTML=""; box.classList.remove("oculto");
  box.appendChild(el("p","dica",`${MATRIZ_IMPORT.linhas.length} linhas de avaliação encontradas na aba Dados.`));

  const grid=el("div","matriz-grid");
  const estudoWrap=el("label",null,"Estudo");
  const estudoSel=el("select"); estudoSel.id="matriz-estudo";
  unicoOrdenado(MATRIZ_IMPORT.linhas.map(matrizKey)).forEach(k=>addOpcao(estudoSel,k,matrizLabel(k)));
  estudoWrap.appendChild(estudoSel); grid.appendChild(estudoWrap);

  const dataWrap=el("label",null,"Data");
  const dataSel=el("select"); dataSel.id="matriz-data";
  dataWrap.appendChild(dataSel); grid.appendChild(dataWrap);

  const varWrap=el("label",null,"Variável");
  const varSel=el("select"); varSel.id="matriz-variavel";
  varWrap.appendChild(varSel); grid.appendChild(varWrap);

  const produtoWrap=el("label","matriz-check");
  const produto=el("input"); produto.type="checkbox"; produto.id="matriz-produto";
  produtoWrap.appendChild(produto);
  produtoWrap.appendChild(document.createTextNode(" Incluir produto no nome do tratamento"));
  grid.appendChild(produtoWrap);
  box.appendChild(grid);

  const preview=el("div","matriz-preview"); preview.id="matriz-preview"; box.appendChild(preview);
  const btn=el("button","btn","Usar no BioEnsaio"); btn.type="button"; btn.addEventListener("click", usarMatrizNoBioensaio); box.appendChild(btn);

  estudoSel.addEventListener("change", atualizarMatrizFiltros);
  dataSel.addEventListener("change", atualizarMatrizFiltros);
  varSel.addEventListener("change", atualizarMatrizPreview);
  produto.addEventListener("change", atualizarMatrizPreview);
  atualizarMatrizFiltros();
}
function colunasBioensaioDeMatriz(linhas, resposta, incluirProduto){
  return [
    {nome:"tratamento", valores:linhas.map(r=>(incluirProduto && r.produto) ? `${r.tratamento} - ${r.produto}` : r.tratamento)},
    {nome:"bloco", valores:linhas.map(r=>r.repeticao || "1")},
    {nome:resposta, valores:linhas.map(r=>String(r.valor))},
    {nome:"produto", valores:linhas.map(r=>r.produto)},
    {nome:"estudo", valores:linhas.map(r=>r.estudo)},
    {nome:"data_avaliacao", valores:linhas.map(r=>r.data)}
  ];
}
function usarMatrizNoBioensaio(){
  const linhas=matrizLinhasFiltradas();
  if(!linhas.length){ avisar("Escolha um estudo/data/variável com valores numéricos."); return; }
  const resposta=$("#matriz-variavel").value || "valor";
  const incluirProduto=$("#matriz-produto") && $("#matriz-produto").checked;
  const cols=colunasBioensaioDeMatriz(linhas, resposta, incluirProduto);
  setModo("analise");
  carregarColunas(cols, {resposta:resposta, fatores:["tratamento"], bloco:"bloco"});
}
const entradaMatriz=$("#entrada-matriz");
if(entradaMatriz){
  entradaMatriz.addEventListener("change", async (ev)=>{
    const file=ev.target.files[0]; if(!file) return;
    try{
      const buf=await file.arrayBuffer();
      const wb=XLSX.read(buf,{type:"array"});
      const sheetName=wb.SheetNames.includes("Dados") ? "Dados" : wb.SheetNames[0];
      const ws=wb.Sheets[sheetName];
      const aoa=XLSX.utils.sheet_to_json(ws,{header:1, blankrows:false, defval:""});
      const linhas=linhasMatrizDeAoa(aoa);
      if(!linhas.length) throw new Error("A aba Dados foi encontrada, mas não há linhas com Tratamento, Variavel e Valor numérico.");
      MATRIZ_IMPORT={arquivo:file.name, sheet:sheetName, linhas};
      renderMatrizImportador();
    }catch(e){
      MATRIZ_IMPORT=null;
      const box=$("#matriz-importador"); if(box){ box.innerHTML=""; box.classList.add("oculto"); }
      avisar("Não consegui importar a planilha do Matriz: " + e.message);
    }
  });
}
window.__bioensaioMatriz = { linhasMatrizDeAoa, matrizKey, colunasBioensaioDeMatriz, numBR, normCab };

/* Exemplos (mode-aware) */
function conjuntoExemplos(){ return MODO==="tempo" ? (window.EXEMPLOS_TEMPO||{}) : window.EXEMPLOS; }
function preencherExemplosPorModo(){
  const sel = $("#sel-exemplo"); if(!sel) return;
  sel.innerHTML="";
  Object.keys(conjuntoExemplos()).forEach(nome=>{
    const o = el("option"); o.value=nome; o.textContent=nome; sel.appendChild(o);
  });
}
preencherExemplosPorModo();
$("#btn-exemplo").addEventListener("click", () => {
  const ex = conjuntoExemplos()[$("#sel-exemplo").value];
  if(!ex) return;
  const cols = ex.colunas.map((nome,i)=>({ nome, valores: ex.linhas.map(l=>String(l[i])) }));
  carregarColunas(cols, Object.assign({}, ex.papeis, ex.papeis_extra||{}));
});

/* Digitar — grade editável */
function montarGrade(nCols=3, nLin=4){
  const wrap = $("#grade-wrap"); wrap.innerHTML="";
  const tab = el("table","grade");
  const thead = el("thead"); const trh = el("tr");
  for(let c=0;c<nCols;c++){ const th=el("th"); const i=el("input"); i.value=["tratamento","x","y"][c]||`col${c+1}`; i.dataset.col=c; th.appendChild(i); trh.appendChild(th); }
  thead.appendChild(trh); tab.appendChild(thead);
  const tb = el("tbody");
  for(let r=0;r<nLin;r++){ const tr=el("tr"); for(let c=0;c<nCols;c++){ const td=el("td"); const i=el("input"); td.appendChild(i); tr.appendChild(td);} tb.appendChild(tr); }
  tab.appendChild(tb); wrap.appendChild(tab);
}
montarGrade();
$("#add-col").addEventListener("click", ()=>{
  const tab=$(".grade"); const c=tab.querySelectorAll("thead th").length;
  const th=el("th"); const i=el("input"); i.value=`col${c+1}`; th.appendChild(i); tab.querySelector("thead tr").appendChild(th);
  tab.querySelectorAll("tbody tr").forEach(tr=>{ const td=el("td"); td.appendChild(el("input")); tr.appendChild(td); });
});
$("#add-lin").addEventListener("click", ()=>{
  const tab=$(".grade"); const nc=tab.querySelectorAll("thead th").length;
  const tr=el("tr"); for(let c=0;c<nc;c++){ const td=el("td"); td.appendChild(el("input")); tr.appendChild(td);} tab.querySelector("tbody").appendChild(tr);
});
$("#btn-digitar").addEventListener("click", ()=>{
  const tab=$(".grade");
  const headers=[...tab.querySelectorAll("thead input")].map(i=>i.value.trim()||"col");
  const linhas=[...tab.querySelectorAll("tbody tr")].map(tr=>[...tr.querySelectorAll("input")].map(i=>i.value.trim()));
  const validas=linhas.filter(l=>l.some(c=>c!==""));
  if(!validas.length){ avisar("Preencha ao menos uma linha."); return; }
  carregarColunas(headers.map((nome,i)=>({nome, valores: validas.map(l=>l[i]||"")})));
});

/* ----------------------------------------------------------------------- */
/* Carregar colunas → preview + papéis                                     */
/* ----------------------------------------------------------------------- */
function ehNumerica(valores){
  let ok=0,tot=0;
  valores.forEach(v=>{ if(String(v).trim()===""){return;} tot++; if(!isNaN(parseFloat(String(v).replace(",",".")))) ok++; });
  return tot>0 && ok/tot>0.7;
}
function adivinharPapeis(){
  const papeis = {};
  const usado = {};
  COLUNAS.forEach(col=>{
    const n = col.nome.toLowerCase();
    let papel = "ignorar";
    if(/dose|dosagem|conc|ppm|concentra/.test(n)) papel="dose";
    else if(/^n$|total|testad|n_?test|num_?test|n_?total/.test(n)) papel="n_total";
    else if(/bloco|block|repet|^rep$|^rep\d/.test(n)) papel="bloco";
    else if(/trat|produto|isolad|meio|lote|cultivar|variedad|fungic|inset|herbic|fator|grupo|especie|esp\b/.test(n)) papel="fator";
    else if(/mort|afet|resp|incid|doente|germin|viv|event|sever|sobreviv|nota|diam|cresc|peso|altura|colon|conta|num/.test(n)) papel="resposta";
    papeis[col.nome]=papel; usado[papel]=(usado[papel]||0)+1;
  });
  // garante exatamente uma resposta: se nenhuma, usa a última coluna numérica livre
  if(!Object.values(papeis).includes("resposta")){
    for(let i=COLUNAS.length-1;i>=0;i--){
      const c=COLUNAS[i];
      if(["ignorar","fator"].includes(papeis[c.nome]) && ehNumerica(c.valores)){ papeis[c.nome]="resposta"; break; }
    }
  }
  // se há dose mas nenhum n_total e a resposta parece proporção pequena, mantém
  return papeis;
}
function carregarColunas(cols, papeisForcados){
  COLUNAS = cols;
  renderPreview();
  let papeis;
  if(MODO==="tempo") papeis = papeisForcados ? papeisDeExemploTempo(papeisForcados) : adivinharPapeisTempo();
  else papeis = papeisForcados ? papeisDeExemplo(papeisForcados) : adivinharPapeis();
  renderPapeis(papeis);
  $("#card-papeis").classList.remove("oculto");
  $("#card-opcoes").classList.toggle("oculto", MODO!=="analise");
  $("#card-opcoes-tempo").classList.toggle("oculto", MODO!=="tempo");
  $("#card-resultados").classList.add("oculto");
  setNavTravado("resultados", true);
  $(".acao-fixa").classList.remove("oculto");
  $("#btn-analisar").disabled = false;
  atualizarPipeline();
  atualizarNav();
  setNavAtivo("papeis");
  garantirPyodide().catch(e=>console.error(e));
  $("#card-papeis").scrollIntoView({behavior:"smooth", block:"start"});
}
function papeisDeExemplo(p){
  const map={};
  COLUNAS.forEach(c=>map[c.nome]="ignorar");
  if(p.resposta) map[p.resposta]="resposta";
  if(p.n_total) map[p.n_total]="n_total";
  if(p.dose) map[p.dose]="dose";
  if(p.bloco) map[p.bloco]="bloco";
  (p.fatores||[]).forEach(f=>map[f]="fator");
  return map;
}
function papeisDeExemploTempo(p){
  const map={};
  COLUNAS.forEach(c=>map[c.nome]="ignorar");
  ["tratamento","tempo","n_total","n_vivos","repeticao","item_teste"].forEach(k=>{
    if(p[k]) map[p[k]]=k;
  });
  return map;
}
function renderPreview(){
  const wrap=$("#preview"); wrap.innerHTML=""; wrap.classList.remove("oculto");
  const n = Math.min(6, COLUNAS[0]?.valores.length||0);
  const tab=el("table");
  const trh=el("tr"); COLUNAS.forEach(c=>trh.appendChild(el("th",null,c.nome)));
  const thead=el("thead"); thead.appendChild(trh); tab.appendChild(thead);
  const tb=el("tbody");
  for(let r=0;r<n;r++){ const tr=el("tr"); COLUNAS.forEach(c=>tr.appendChild(el("td",null,c.valores[r]??""))); tb.appendChild(tr); }
  tab.appendChild(tb);
  const cap=el("p","dica",`${COLUNAS[0]?.valores.length||0} linhas × ${COLUNAS.length} colunas (mostrando ${n})`);
  wrap.appendChild(cap);
  const rol=el("div","tab-rolavel"); rol.appendChild(tab); wrap.appendChild(rol);
}
const PAPEL_OPCOES = [["resposta","Resposta"],["dose","Dose/concentração"],["fator","Fator/tratamento"],["bloco","Bloco/repetição"],["n_total","n total (x de n)"],["ignorar","Ignorar"]];
const PAPEL_OPCOES_TEMPO = [["tratamento","Tratamento"],["tempo","Tempo (dia/hora)"],["n_total","N total (inicial)"],["n_vivos","N vivos"],["repeticao","Repetição"],["item_teste","Item/produto"],["ignorar","Ignorar"]];
function renderPapeis(papeis){
  const lista=$("#papeis-lista"); lista.innerHTML="";
  const opcoes = MODO==="tempo" ? PAPEL_OPCOES_TEMPO : PAPEL_OPCOES;
  COLUNAS.forEach(col=>{
    const item=el("div","papel-item");
    item.appendChild(el("span","papel-nome",col.nome));
    const sel=el("select"); sel.dataset.coluna=col.nome;
    opcoes.forEach(([v,t])=>{ const o=el("option"); o.value=v; o.textContent=t; if(papeis[col.nome]===v)o.selected=true; sel.appendChild(o); });
    sel.addEventListener("change", ()=>{
      if(MODO==="tempo") popularControleNeg();
      $("#card-resultados").classList.add("oculto");
      setNavTravado("resultados", true);
      atualizarPipeline();
    });
    item.appendChild(sel); lista.appendChild(item);
  });
  if(MODO==="tempo") popularControleNeg();
}
function adivinharPapeisTempo(){
  const papeis={};
  COLUNAS.forEach(col=>{
    const n=col.nome.toLowerCase(); let p="ignorar";
    if(/n[_\s]?vivo|vivos|alive|^live|sobreviv/.test(n)) p="n_vivos";
    else if(/n[_\s]?total|inicial|initial|^total$|^n$|n[_\s]?inicial/.test(n)) p="n_total";
    else if(/tempo|dia|hora|^dap$|day|hour|tempo[_\s]?valor/.test(n)) p="tempo";
    else if(/repet|^rep$|^rep\d|replic|bloco/.test(n)) p="repeticao";
    else if(/item|produto|test[_\s]?item|item[_\s]?teste/.test(n)) p="item_teste";
    else if(/trat|treatment$|^trat/.test(n)) p="tratamento";
    papeis[col.nome]=p;
  });
  if(!Object.values(papeis).includes("tratamento")){
    const c=COLUNAS.find(c=>papeis[c.nome]==="ignorar" && !ehNumerica(c.valores));
    if(c) papeis[c.nome]="tratamento";
  }
  return papeis;
}
function popularControleNeg(){
  const sel=$("#opt-controle-neg"); if(!sel) return;
  // acha a coluna marcada como tratamento
  let tratCol=null;
  document.querySelectorAll("#papeis-lista select").forEach(s=>{ if(s.value==="tratamento") tratCol=s.dataset.coluna; });
  const atual=sel.value;
  sel.innerHTML='<option value="">(1º tratamento)</option>';
  if(tratCol){
    const col=COLUNAS.find(c=>c.nome===tratCol);
    if(col){
      const niveis=[...new Set(col.valores.map(v=>String(v).trim()).filter(v=>v!==""))]
        .sort((a,b)=>{ const na=parseInt((a.match(/\d+/)||[1e9])[0]), nb=parseInt((b.match(/\d+/)||[1e9])[0]); return na-nb || a.localeCompare(b); });
      niveis.forEach(v=>{ const o=el("option"); o.value=v; o.textContent=v; if(v===atual)o.selected=true; sel.appendChild(o); });
    }
  }
}
function lerPapeis(){
  const r={ fatores:[] };
  document.querySelectorAll("#papeis-lista select").forEach(sel=>{
    const col=sel.dataset.coluna, p=sel.value;
    if(p==="resposta") r.resposta=col;
    else if(p==="dose") r.dose=col;
    else if(p==="bloco") r.bloco=col;
    else if(p==="n_total") r.n_total=col;
    else if(p==="fator") r.fatores.push(col);
  });
  const tipo=$("#opt-tipo").value; if(tipo) r.tipo_resposta=tipo;
  return r;
}
function montarDados(){
  const d={}; COLUNAS.forEach(c=>d[c.nome]=c.valores); return d;
}
function lerPapeisTempo(){
  const r={};
  document.querySelectorAll("#papeis-lista select").forEach(sel=>{
    const col=sel.dataset.coluna, p=sel.value;
    if(p!=="ignorar") r[p]=col;
  });
  return r;
}

/* ----------------------------------------------------------------------- */
/* Pipeline guiado + QA/QC                                                 */
/* ----------------------------------------------------------------------- */
function papelSelecoesAtuais(){
  const porColuna={}, porPapel={};
  document.querySelectorAll("#papeis-lista select").forEach(sel=>{
    const col=sel.dataset.coluna, papel=sel.value;
    porColuna[col]=papel;
    if(papel!=="ignorar"){
      if(!porPapel[papel]) porPapel[papel]=[];
      porPapel[papel].push(col);
    }
  });
  return {porColuna, porPapel};
}
function colunaPorNome(nome){ return COLUNAS.find(c=>c.nome===nome); }
function valoresColuna(nome){ return (colunaPorNome(nome)||{}).valores || []; }
function linhasAtuais(){
  const n=COLUNAS[0]?.valores.length || 0;
  return Array.from({length:n}, (_,i)=>{
    const row={};
    COLUNAS.forEach(c=>row[c.nome]=c.valores[i] ?? "");
    return row;
  });
}
function textoValor(v){ return String(v==null?"":v).trim(); }
function valoresValidos(arr){ return arr.map(textoValor).filter(v=>v!==""); }
function nUnicos(arr){ return new Set(valoresValidos(arr)).size; }
function taxaNumerica(arr){
  const vals=valoresValidos(arr);
  if(!vals.length) return {total:0, ok:0, taxa:0};
  const ok=vals.filter(v=>Number.isFinite(numBR(v))).length;
  return {total:vals.length, ok, taxa:ok/vals.length};
}
function numsColuna(nome){ return valoresColuna(nome).map(v=>numBR(v)); }
function pushCheck(checks, severidade, titulo, detalhe, bloqueia=false){
  checks.push({severidade, titulo, detalhe, bloqueia: !!bloqueia});
}
function nomeControleProvavel(v){
  return /controle|testemunha|control|check|sem\s*trat|negativo/i.test(String(v||""));
}
function inferirTipoResposta(papeis){
  if(papeis.tipo_resposta) return papeis.tipo_resposta;
  if(papeis.n_total) return "binomial";
  const resp=valoresValidos(valoresColuna(papeis.resposta));
  if(!resp.length) return "";
  const norm=resp.map(v=>v.toLowerCase());
  const palavrasBinarias=norm.every(v=>/^(sim|s|yes|y|true|1|nao|não|n|no|false|0|vivo|morto|germinou|nao germinou|não germinou)$/.test(v));
  if(palavrasBinarias) return "binario";
  const nums=resp.map(v=>numBR(v));
  const numericos=nums.filter(Number.isFinite);
  if(numericos.length/resp.length < .7) return "continua";
  const inteiros=numericos.every(v=>Number.isInteger(v) && v>=0);
  const nome=(papeis.resposta||"").toLowerCase();
  if(inteiros && /mort|vivo|afet|evento|germin|doente|colon|cont|n[ºo]?/i.test(nome)) return "contagem";
  if(numericos.every(v=>v>=0 && v<=100) && /sev|incid|porc|percent|%|efic|mortal/i.test(nome)) return "proporcao";
  return "continua";
}
function rotaGeral(papeis, tipo){
  const temDose=!!papeis.dose;
  const fatores=(papeis.fatores||[]).length;
  if(temDose && ["binario","binomial"].includes(tipo)){
    return {
      titulo:"Dose-resposta",
      descricao:"Ajustar curva logit/probit, estimar CL/DL e avaliar aderência/heterogeneidade.",
      chips:["curva","CL/DL","Abbott se informado"]
    };
  }
  if(temDose && !["binario","binomial"].includes(tipo)){
    return {
      titulo:"Dose como tratamento",
      descricao:"Resposta não-binomial com coluna de dose; comparar níveis de dose como tratamentos ou avançar para regressão.",
      chips:["dose","comparação"]
    };
  }
  if(tipo==="binomial" && fatores){
    return {titulo:"GLM binomial", descricao:"Comparar proporções x de n por tratamento, com letras por contrastes.", chips:["x de n","logístico"]};
  }
  if(tipo==="binario" && fatores){
    return {titulo:"GLM binomial agregado", descricao:"Agregar eventos individuais por tratamento e comparar proporções.", chips:["binário","agregação"]};
  }
  if(tipo==="contagem" && fatores){
    return {titulo:"GLM de contagem", descricao:"Usar Poisson e trocar para binomial negativa se houver sobredispersão.", chips:["Poisson","sobredispersão"]};
  }
  if(["continua","proporcao"].includes(tipo) && fatores){
    return {titulo:"ANOVA + pós-teste", descricao:"Checar pressupostos, transformar se necessário e comparar médias.", chips:["ANOVA","Tukey/Scott-Knott"]};
  }
  return {titulo:"Descritiva", descricao:"Sem fator/tratamento suficiente; apresentar estatística descritiva e normalidade.", chips:["resumo"]};
}
function checarDuplicatasGerais(checks){
  const rows=linhasAtuais();
  const vistos=new Set();
  let duplicatas=0;
  rows.forEach(r=>{
    const key=COLUNAS.map(c=>textoValor(r[c.nome])).join("||");
    if(vistos.has(key)) duplicatas++;
    else vistos.add(key);
  });
  if(duplicatas) pushCheck(checks,"aviso","Linhas duplicadas",`${duplicatas} linha(s) idêntica(s) no arquivo. Confira se não é lançamento repetido.`);
  else pushCheck(checks,"ok","Duplicatas exatas","Nenhuma linha idêntica encontrada.");
}
function avaliarPipelineGeral(){
  const checks=[];
  const sel=papelSelecoesAtuais();
  const papeis=lerPapeis();
  const nLin=COLUNAS[0]?.valores.length || 0;
  pushCheck(checks,"ok","Dados carregados",`${nLin} linha(s) e ${COLUNAS.length} coluna(s).`);

  ["resposta","dose","bloco","n_total"].forEach(p=>{
    if((sel.porPapel[p]||[]).length>1) pushCheck(checks,"critico","Papéis conflitantes",`Mais de uma coluna marcada como ${p}: ${sel.porPapel[p].join(", ")}.`, true);
  });
  if(!papeis.resposta) pushCheck(checks,"critico","Resposta ausente","Marque uma coluna como Resposta.", true);

  const tipo=papeis.resposta ? inferirTipoResposta(papeis) : "";
  const rota=rotaGeral(papeis, tipo);

  if(papeis.resposta){
    const resp=valoresColuna(papeis.resposta);
    const faltantes=resp.filter(v=>textoValor(v)==="").length;
    if(faltantes) pushCheck(checks,"aviso","Resposta com vazios",`${faltantes} linha(s) sem valor de resposta.`);
    const taxa=taxaNumerica(resp);
    if(!["binario"].includes(tipo) && taxa.total && taxa.taxa<.9){
      pushCheck(checks,"critico","Resposta não-numérica",`Apenas ${taxa.ok}/${taxa.total} valores da resposta são numéricos.`, true);
    } else {
      pushCheck(checks,"ok","Resposta compatível",`Tipo inferido: ${tipo || "a confirmar"}.`);
    }
  }

  if(papeis.n_total){
    const y=numsColuna(papeis.resposta), n=numsColuna(papeis.n_total);
    let invalidos=0, impossiveis=0;
    n.forEach((nn,i)=>{
      if(!Number.isFinite(nn) || nn<=0 || !Number.isFinite(y[i])) invalidos++;
      else if(y[i]<0 || y[i]>nn) impossiveis++;
    });
    if(invalidos) pushCheck(checks,"critico","Binomial incompleto",`${invalidos} linha(s) com resposta ou n total inválidos.`, true);
    if(impossiveis) pushCheck(checks,"critico","Eventos impossíveis",`${impossiveis} linha(s) com eventos < 0 ou eventos > n total.`, true);
    if(!invalidos && !impossiveis) pushCheck(checks,"ok","x de n válido","Eventos e totais passam na checagem básica.");
  }

  if(papeis.dose){
    const dose=numsColuna(papeis.dose);
    const invalidas=dose.filter(v=>!Number.isFinite(v)).length;
    const positivas=[...new Set(dose.filter(v=>Number.isFinite(v) && v>0).map(v=>String(v)))];
    if(invalidas) pushCheck(checks,"critico","Dose não-numérica",`${invalidas} linha(s) com dose inválida.`, true);
    else pushCheck(checks,"ok","Dose numérica",`${positivas.length} nível(is) positivo(s) de dose.`);
    if(["binario","binomial"].includes(tipo) && positivas.length<3){
      pushCheck(checks,"critico","Poucos níveis de dose","Dose-resposta precisa de pelo menos 3 doses positivas para estimar curva com segurança.", true);
    }
  }

  const fatores=papeis.fatores||[];
  if(fatores.length){
    const chave=fatores.map(f=>valoresColuna(f));
    const grupos=new Map();
    for(let i=0;i<nLin;i++){
      const g=fatores.map((f,j)=>textoValor(chave[j][i])).join(" / ");
      if(!g.trim()) continue;
      grupos.set(g,(grupos.get(g)||0)+1);
    }
    if(grupos.size<2 && !papeis.dose) pushCheck(checks,"critico","Poucos tratamentos","É preciso ao menos 2 tratamentos/grupos para comparação.", true);
    else pushCheck(checks,"ok","Tratamentos detectados",`${grupos.size} tratamento(s)/grupo(s).`);
    const poucos=[...grupos.entries()].filter(([,n])=>n<2).map(([g])=>g);
    if(poucos.length) pushCheck(checks,"aviso","Repetição baixa",`${poucos.slice(0,4).join(", ")}${poucos.length>4?"...":""} com menos de 2 repetição(ões).`);
  } else if(!papeis.dose){
    pushCheck(checks,"aviso","Sem fator/tratamento","A rota ficará limitada a descritiva se nenhum fator for marcado.");
  }

  if(papeis.bloco){
    const vazios=valoresColuna(papeis.bloco).filter(v=>textoValor(v)==="").length;
    if(vazios) pushCheck(checks,"aviso","Bloco incompleto",`${vazios} linha(s) sem bloco/repetição.`);
    else pushCheck(checks,"ok","Blocos preenchidos",`${nUnicos(valoresColuna(papeis.bloco))} bloco(s)/repetição(ões).`);
  }

  if(papeis.n_total && papeis.resposta){
    const rows=linhasAtuais();
    const y=numsColuna(papeis.resposta), n=numsColuna(papeis.n_total);
    const controle=rows.map((r,i)=>({r,i})).filter(({r})=>
      (papeis.dose && Number.isFinite(numBR(r[papeis.dose])) && numBR(r[papeis.dose])===0) ||
      (papeis.fatores||[]).some(f=>nomeControleProvavel(r[f]))
    );
    if(controle.length){
      const mortalidades=controle.map(({i})=>Number.isFinite(y[i])&&Number.isFinite(n[i])&&n[i]>0 ? (y[i]/n[i])*100 : NaN).filter(Number.isFinite);
      const media=mortalidades.reduce((a,b)=>a+b,0)/(mortalidades.length||1);
      if(mortalidades.length && media>20) pushCheck(checks,"aviso","Controle alto",`Mortalidade/evento médio do controle: ${fmt(media,1)}%.`);
      else if(mortalidades.length) pushCheck(checks,"ok","Controle dentro do esperado",`Média do controle: ${fmt(media,1)}%.`);
    } else {
      pushCheck(checks,"aviso","Controle não identificado","Não encontrei dose 0 nem nome de controle/testemunha.");
    }
  }

  checarDuplicatasGerais(checks);
  return montarInfoPipeline("analise", rota, tipo, checks);
}
function avaliarPipelineTempo(){
  const checks=[];
  const papeis=lerPapeisTempo();
  const nLin=COLUNAS[0]?.valores.length || 0;
  const obrig=["tratamento","tempo","n_total","n_vivos"];
  pushCheck(checks,"ok","Dados carregados",`${nLin} linha(s) e ${COLUNAS.length} coluna(s).`);
  obrig.forEach(k=>{ if(!papeis[k]) pushCheck(checks,"critico","Papel obrigatório ausente",`Marque a coluna de ${k}.`, true); });
  const rota={titulo:"Mortalidade no tempo", descricao:"Checar sobrevivência por avaliação, correção do controle, letras por tempo, LT50/LT90 e modelos de tempo.", chips:["QA/QC","Kaplan-Meier","GLM tempo"]};

  if(obrig.every(k=>papeis[k])){
    const tempo=numsColuna(papeis.tempo), nt=numsColuna(papeis.n_total), nv=numsColuna(papeis.n_vivos);
    let invalidos=0, impossiveis=0;
    for(let i=0;i<nLin;i++){
      if(!Number.isFinite(tempo[i]) || !Number.isFinite(nt[i]) || !Number.isFinite(nv[i]) || nt[i]<=0) invalidos++;
      else if(nv[i]<0 || nv[i]>nt[i]) impossiveis++;
    }
    if(invalidos) pushCheck(checks,"critico","Valores inválidos",`${invalidos} linha(s) com tempo, n total ou n vivos inválidos.`, true);
    if(impossiveis) pushCheck(checks,"critico","Vivos impossíveis",`${impossiveis} linha(s) com n vivos < 0 ou maior que n total.`, true);
    if(!invalidos && !impossiveis) pushCheck(checks,"ok","Contagens válidas","n vivos e n total passam na checagem básica.");

    const tratamentos=valoresColuna(papeis.tratamento);
    const temposUnicos=[...new Set(tempo.filter(Number.isFinite).map(v=>String(v)))];
    if(nUnicos(tratamentos)<2) pushCheck(checks,"critico","Poucos tratamentos","É preciso ao menos 2 tratamentos para mortalidade no tempo.", true);
    else pushCheck(checks,"ok","Tratamentos detectados",`${nUnicos(tratamentos)} tratamento(s).`);
    if(temposUnicos.length<2) pushCheck(checks,"critico","Poucos tempos","É preciso ao menos 2 tempos de avaliação.", true);
    else pushCheck(checks,"ok","Tempos detectados",`${temposUnicos.length} tempo(s) de avaliação.`);

    const rep= papeis.repeticao ? valoresColuna(papeis.repeticao) : Array.from({length:nLin},()=> "1");
    const vistos=new Set(); let duplicatas=0;
    const series=new Map();
    for(let i=0;i<nLin;i++){
      const key=[textoValor(tratamentos[i]), textoValor(rep[i]), String(tempo[i])].join("||");
      if(vistos.has(key)) duplicatas++; else vistos.add(key);
      const skey=[textoValor(tratamentos[i]), textoValor(rep[i])].join("||");
      if(!series.has(skey)) series.set(skey,[]);
      series.get(skey).push({tempo:tempo[i], vivos:nv[i]});
    }
    if(duplicatas) pushCheck(checks,"critico","Avaliações duplicadas",`${duplicatas} combinação(ões) tratamento/repetição/tempo repetidas.`, true);
    else pushCheck(checks,"ok","Sem duplicatas por tempo","Tratamento + repetição + tempo está único.");

    let aumentos=0;
    series.forEach(lista=>{
      lista.filter(x=>Number.isFinite(x.tempo)&&Number.isFinite(x.vivos)).sort((a,b)=>a.tempo-b.tempo)
        .forEach((x,i,arr)=>{ if(i && x.vivos>arr[i-1].vivos) aumentos++; });
    });
    if(aumentos) pushCheck(checks,"aviso","N vivos aumentou no tempo",`${aumentos} aumento(s) detectado(s). Pode ser erro de lançamento ou reposição de indivíduos.`);
    else pushCheck(checks,"ok","Monotonicidade","n vivos não aumenta ao longo do tempo nas séries.");

    const controle=$("#opt-controle-neg")?.value || textoValor([...new Set(tratamentos.map(textoValor).filter(Boolean))][0]||"");
    const ctrlMax=parseFloat(($("#opt-ctrlmax")?.value||"20").replace(",",".")) || 20;
    if(controle){
      const mortCtrl=[];
      for(let i=0;i<nLin;i++){
        if(textoValor(tratamentos[i])===controle && Number.isFinite(nt[i]) && nt[i]>0 && Number.isFinite(nv[i])){
          mortCtrl.push(((nt[i]-nv[i])/nt[i])*100);
        }
      }
      if(mortCtrl.length){
        const max=Math.max(...mortCtrl);
        if(max>ctrlMax) pushCheck(checks,"aviso","Controle acima do critério",`Controle ${controle}: mortalidade máxima ${fmt(max,1)}% (critério ${fmt(ctrlMax,1)}%).`);
        else pushCheck(checks,"ok","Controle dentro do critério",`Controle ${controle}: mortalidade máxima ${fmt(max,1)}%.`);
      }
    }
  }
  return montarInfoPipeline("tempo", rota, "tempo", checks);
}
function montarInfoPipeline(modo, rota, tipo, checks){
  const criticos=checks.filter(c=>c.severidade==="critico").length;
  const avisos=checks.filter(c=>c.severidade==="aviso").length;
  const oks=checks.filter(c=>c.severidade==="ok").length;
  return {modo, rota, tipo, checks, criticos, avisos, oks, bloqueia: checks.some(c=>c.bloqueia)};
}
function avaliarPipelineAtual(){
  if(!COLUNAS.length) return null;
  return MODO==="tempo" ? avaliarPipelineTempo() : avaliarPipelineGeral();
}
function pipelineHtml(info, compacto=false){
  if(!info) return "";
  const chips=(info.rota.chips||[]).map(c=>chip(esc(c),"chip-info")).join("");
  const status=info.criticos ? chip(`${info.criticos} crítico(s)`,"chip-alerta") : chip("sem críticos","chip-ok");
  const resumo=`<div class="pipeline-resumo">`+
    `<span>${status}</span><span>${chip(info.avisos+" aviso(s)", info.avisos?"chip-alerta":"chip-ok")}</span><span>${chip(info.oks+" OK","chip-ok")}</span>`+
    `</div>`;
  const checks=info.checks.map(c=>
    `<li class="qa-item qa-${c.severidade}"><b>${esc(c.titulo)}</b><span>${esc(c.detalhe||"")}</span></li>`
  ).join("");
  return `<div class="pipeline-panel">`+
    `<div class="pipeline-head"><div><span class="pipeline-kicker">Rota recomendada</span><h3>${esc(info.rota.titulo)}</h3><p>${esc(info.rota.descricao)}</p></div><div class="pipeline-chipset">${chips}</div></div>`+
    resumo+
    (compacto ? "" : `<ul class="qa-list">${checks}</ul>`)+
    `</div>`;
}
function renderPipelineStatus(info){
  const card=$("#card-pipeline"), box=$("#pipeline-status");
  if(!card || !box) return;
  if(!info){ card.classList.add("oculto"); box.innerHTML=""; return; }
  card.classList.remove("oculto");
  box.innerHTML=pipelineHtml(info);
  const btn=$("#btn-analisar");
  if(btn) btn.disabled=!!info.bloqueia;
}
function atualizarPipeline(){
  const info=avaliarPipelineAtual();
  renderPipelineStatus(info);
  return info;
}
function validarPipelineAntesDeAnalisar(){
  const info=atualizarPipeline();
  if(info && info.bloqueia){
    avisar("Corrija os pontos críticos da conferência antes de analisar.");
    $("#card-pipeline").scrollIntoView({behavior:"smooth", block:"start"});
    return false;
  }
  return true;
}
function renderPipelineRelatorio(out){
  const info=avaliarPipelineAtual();
  if(info) out.appendChild(secao("Pipeline guiado", pipelineHtml(info, true)));
}
["#opt-tipo","#opt-alfa","#opt-unidade","#opt-niveis","#opt-controle","#opt-logdose",
 "#opt-controle-neg","#opt-sk","#opt-alfa-tempo","#opt-ctrlmax"].forEach(sel=>{
  const node=$(sel);
  if(node){
    node.addEventListener("change", atualizarPipeline);
    node.addEventListener("input", atualizarPipeline);
  }
});

/* ----------------------------------------------------------------------- */
/* Analisar                                                                */
/* ----------------------------------------------------------------------- */
async function rodarPython(fnNome, papeis, opcoes){
  await garantirPyodide();
  mostrarOverlay("Analisando…","");
  await new Promise(r=>setTimeout(r,30));
  const fn = pyodide.globals.get(fnNome);
  const json = fn(JSON.stringify(montarDados()), JSON.stringify(papeis), JSON.stringify(opcoes));
  fn.destroy();
  esconderOverlay();
  return JSON.parse(json);
}

$("#btn-analisar").addEventListener("click", async () => {
  if(MODO==="tempo") return analisarTempo();
  if(!validarPipelineAntesDeAnalisar()) return;
  const papeis = lerPapeis();
  if(!papeis.resposta){ avisar("Defina qual coluna é a Resposta."); return; }
  const opcoes = { alfa: parseFloat($("#opt-alfa").value), log_dose: $("#opt-logdose").checked };
  const uni = ($("#opt-unidade").value||"").trim(); if(uni) opcoes.unidade_dose = uni;
  const niveisStr = ($("#opt-niveis").value||"").trim();
  if(niveisStr){
    const probs = niveisStr.split(/[;,]/).map(s=>parseFloat(s.replace(",","."))/100)
                           .filter(p=>p>0 && p<1);
    if(probs.length) opcoes.probs = probs;
  }
  const ctrlStr = ($("#opt-controle").value||"").trim();
  if(ctrlStr){ const c=parseFloat(ctrlStr.replace(",","."))/100; if(c>0 && c<1) opcoes.controle_mort = c; }
  try{
    renderRelatorio(await rodarPython("_run_web", papeis, opcoes));
  }catch(e){ esconderOverlay(); renderRelatorio({ok:false, erro:e.message}); console.error(e); }
});

async function analisarTempo(){
  if(!validarPipelineAntesDeAnalisar()) return;
  const papeis = lerPapeisTempo();
  const falta = ["tratamento","tempo","n_total","n_vivos"].filter(k=>!papeis[k]);
  if(falta.length){ avisar("Defina as colunas: "+falta.join(", ")); return; }
  const opcoes = {
    alfa: parseFloat($("#opt-alfa-tempo").value),
    sk_threshold: parseInt($("#opt-sk").value),
    ctrl_mort_max: parseFloat(($("#opt-ctrlmax").value||"20").replace(",",".")) || 20,
  };
  const cn = $("#opt-controle-neg").value; if(cn) opcoes.controle_neg = cn;
  try{
    renderRelatorioTempo(await rodarPython("_run_tempo", papeis, opcoes));
  }catch(e){ esconderOverlay(); renderRelatorioTempo({ok:false, erro:e.message}); console.error(e); }
}

/* ----------------------------------------------------------------------- */
/* Render do relatório                                                     */
/* ----------------------------------------------------------------------- */
function fmt(x, d=3){ if(x==null||x===undefined) return "—"; if(typeof x!=="number") return String(x); if(!isFinite(x)) return "∞"; return x.toLocaleString("pt-BR",{maximumFractionDigits:d, minimumFractionDigits:0}); }
function p_chip(p){ if(p==null) return ""; const sig=p<0.05; return `<span class="chip ${sig?'chip-ok':'chip-info'}">p=${fmt(p,4)}</span>`; }

function renderRelatorio(rel){
  const out=$("#resultados"); out.innerHTML="";
  $("#card-resultados").classList.remove("oculto");
  setNavTravado("resultados", false);
  setNavAtivo("resultados");
  if(!rel.ok){
    out.appendChild(renderErroRelatorio(rel));
    $("#card-resultados").scrollIntoView({behavior:"smooth"}); return;
  }
  renderPipelineRelatorio(out);
  // Detecção
  const det=rel.deteccao;
  out.appendChild(secao("Detecção",
    `<div>${chip(det.tipo_resposta,"chip-ok")} ${det.desenho.tem_dose?chip("dose-resposta","chip-info"):""} `+
    `${det.desenho.n_fatores?chip(det.desenho.n_fatores+" fator(es)","chip-info"):""} `+
    `${det.desenho.tem_bloco?chip("com bloco","chip-info"):""}</div>`+
    `<p class="dica">${det.detalhe_resposta||""}</p>`));

  if(rel.decisao) out.appendChild(htmlBloco(`<div class="decisao"><b>Decisão do app:</b> ${rel.decisao}</div>`));
  (rel.avisos||[]).forEach(a=> out.appendChild(htmlBloco(`<div class="aviso"><b>Aviso:</b> ${a}</div>`)));

  if(rel.descritiva) out.appendChild(secao("Estatística descritiva", tabelaDescritiva(rel.descritiva)));

  const a = rel.analise || {};
  if(a.doses_letais || a.curvas) renderDose(out, a);
  else if(a.tabela_anova) renderAnova(out, rel);
  else if(a.medias_estimadas || a.proporcoes_estimadas) renderGlm(out, a);
  else if(a.normalidade) out.appendChild(secao("Normalidade", tabelaNormalidade(a.normalidade)));

  $("#card-resultados").scrollIntoView({behavior:"smooth"});
}

function secao(titulo, htmlInterno){ const b=el("div","bloco"); b.innerHTML=`<h3>${titulo}</h3>`+htmlInterno; return b; }
function htmlBloco(html){ const b=el("div","bloco"); b.innerHTML=html; return b; }
function chip(t,c="chip-info"){ return `<span class="chip ${c}">${t}</span>`; }
function renderErroRelatorio(rel){
  const detalhe = rel.trace ? `<details class="trace-box"><summary>Detalhes técnicos</summary><pre>${esc(rel.trace)}</pre></details>` : "";
  return htmlBloco(`<div class="erro-box"><b>Não foi possível analisar.</b><br>${esc(rel.erro||"Verifique os dados e os papéis das colunas.")}</div>${detalhe}`);
}

function tabelaDescritiva(desc){
  const temProp = desc[0] && ("proporcao" in desc[0]);
  let h=`<div class="tab-rolavel"><table><thead><tr><th>Tratamento</th><th>n</th>`;
  h += temProp ? `<th>Eventos</th><th>Proporção</th>` : `<th>Média</th><th>DP</th><th>EP</th><th>CV%</th><th>Mín</th><th>Máx</th>`;
  h += `</tr></thead><tbody>`;
  desc.forEach(d=>{
    h += `<tr><td>${d.tratamento}</td><td>${d.n}</td>`;
    h += temProp ? `<td>${d.eventos}</td><td>${fmt(d.proporcao,3)}</td>`
                 : `<td>${fmt(d.media)}</td><td>${fmt(d.dp)}</td><td>${fmt(d.ep)}</td><td>${fmt(d.cv,1)}</td><td>${fmt(d.min)}</td><td>${fmt(d.max)}</td>`;
    h += `</tr>`;
  });
  return h+`</tbody></table></div>`;
}
function tabelaNormalidade(n){
  return `<div class="kv"><dt>Teste</dt><dd>${n.teste}</dd>`+
    `<dt>Estatística</dt><dd>${fmt(n.estatistica,4)}</dd>`+
    `<dt>p-valor</dt><dd>${fmt(n.p,4)} ${n.normal?chip("normal","chip-ok"):chip("não-normal","chip-alerta")}</dd>`+
    (n.assimetria!=null?`<dt>Assimetria</dt><dd>${fmt(n.assimetria,3)}</dd>`:"")+
    (n.curtose!=null?`<dt>Curtose</dt><dd>${fmt(n.curtose,3)}</dd>`:"")+`</div>`;
}

/* ---- Dose-resposta ---- */
function renderDose(out, a){
  const curvas = a.curvas ? a.curvas : [a];
  const uni = (document.getElementById('opt-unidade')?.value || "").trim();
  const sufUni = uni ? " " + uni : "";
  curvas.forEach(c=>{
    const titulo = c.grupo && c.grupo!=="(único)" ? `Dose-resposta — ${c.grupo}` : "Dose-resposta";
    let h = `<div class="kv">`+
      `<dt>Modelo</dt><dd>${c.tipo_analise} ${chip("ligação: "+c.link,"chip-info")}</dd>`+
      `<dt>Inclinação (slope)</dt><dd>${fmt(c.slope,3)} ± ${fmt(c.slope_se,3)}</dd>`+
      `<dt>χ² aderência</dt><dd>${fmt(c.qui_quadrado,2)} (gl=${c.gl}) ${p_chip(c.p_qui_quadrado)}</dd>`+
      `<dt>Heterogeneidade (h)</dt><dd>${fmt(c.heterogeneidade_h,2)} ${c.heterogeneo?chip("heterogêneo → IC por t","chip-alerta"):chip("homogêneo","chip-ok")}</dd>`+
      (c.abbott_aplicado?`<dt>Abbott</dt><dd>${chip("corrigido (controle "+fmt(c.controle_mortalidade*100,1)+"%)","chip-info")}</dd>`:"")+
      `</div>`;
    const colDose = "Dose" + (uni ? ` (${uni})` : "");
    h += `<div class="tab-rolavel"><table><thead><tr><th>Letal</th><th>${colDose}</th><th>IC95% inf.</th><th>IC95% sup.</th></tr></thead><tbody>`;
    c.doses_letais.forEach(dl=>{
      h += `<tr><td>CL/DL${Math.round(dl.p*100)}</td><td><b>${fmt(dl.dose,3)}${sufUni}</b></td><td>${fmt(dl.ic_inf,3)}</td><td>${fmt(dl.ic_sup,3)}</td></tr>`;
    });
    h += `</tbody></table></div>`;
    if(c.modelo_natural_mle) h += `<p class="dica">Modelo com mortalidade natural estimada (Finney): C=${fmt(c.modelo_natural_mle.C*100,1)}%.</p>`;
    const b = secao(titulo, h);
    const cv = el("canvas"); cv.width=600; cv.height=320; b.appendChild(cv);
    out.appendChild(b);
    desenharDose(cv, c, uni);
  });
  if(a.comparacao) renderComparacaoCurvas(out, a.comparacao, uni);
}

function renderComparacaoCurvas(out, comp, uni){
  const sufUni = uni ? " "+uni : "";
  let h = "";
  const par = comp.paralelismo || {};
  if(par.erro){
    h += `<div class="aviso">Não foi possível testar paralelismo: ${par.erro}</div>`;
  } else {
    h += `<div style="margin-bottom:8px">`+
      (par.paralelo ? chip("curvas paralelas (p="+fmt(par.p,3)+")","chip-ok")
                    : chip("inclinações diferem (p="+fmt(par.p,3)+") — potência varia com a dose","chip-alerta"));
    if(comp.diferenca_potencia){
      const dp=comp.diferenca_potencia;
      h += dp.difere ? chip("potências diferem (p="+fmt(dp.p,3)+")","chip-info")
                     : chip("sem diferença de potência (p="+fmt(dp.p,3)+")","chip-ok");
    }
    h += `</div>`;
  }
  h += `<p class="dica">Referência (RR=1): <b>${comp.referencia||"—"}</b> — menor CL50 (mais sensível/potente). `+
       `RR &gt; 1 = menos sensível (mais resistente / menos potente).</p>`;
  h += `<div class="tab-rolavel"><table><thead><tr><th>Produto/Pop.</th><th>CL50${uni?" ("+uni+")":""}</th>`+
       `<th>Razão (RR)</th><th>IC95%</th></tr></thead><tbody>`;
  (comp.razoes||[]).forEach(r=>{
    const sig = r.significativo && !r.referencia ? " significativo" : "";
    const tag = r.referencia ? ` <span class="op-tag">ref</span>` : "";
    h += `<tr><td>${r.grupo}${tag}</td><td>${fmt(r.lc50,3)}${sufUni}</td>`+
         `<td><b>${fmt(r.rr,2)}×</b>${sig}</td>`+
         `<td>${r.referencia?"—":fmt(r.ic_inf,2)+" – "+fmt(r.ic_sup,2)}</td></tr>`;
  });
  h += `</tbody></table></div><p class="dica">Significativo = RR significativamente diferente de 1 (IC não inclui 1).</p>`;
  out.appendChild(secao("Comparação de potência / resistência", h));
}

/* ---- ANOVA ---- */
function renderAnova(out, rel){
  const a = rel.analise;
  let diag = `<div>`+
    (a.normalidade? (a.normalidade.normal?chip("resíduos normais","chip-ok"):chip("resíduos não-normais (p="+fmt(a.normalidade.p,3)+")","chip-alerta")) : "")+
    (a.homogeneidade? (a.homogeneidade.homogenea?chip("variâncias homogêneas","chip-ok"):chip("variâncias heterogêneas","chip-alerta")) : "")+
    (a.transformacao?chip("transformação: "+a.transformacao,"chip-info"):"")+
    (a.pressupostos_ok?chip("pressupostos OK","chip-ok"):chip("pressupostos violados","chip-alerta"))+
    `</div>`;
  out.appendChild(secao(a.tipo_analise, diag));

  let h=`<div class="tab-rolavel"><table><thead><tr><th>Fonte</th><th>GL</th><th>SQ</th><th>QM</th><th>F</th><th>p</th></tr></thead><tbody>`;
  a.tabela_anova.forEach(l=>{
    h+=`<tr><td>${l.fonte}</td><td>${fmt(l.gl,0)}</td><td>${fmt(l.sq,2)}</td><td>${fmt(l.qm,2)}</td><td>${fmt(l.F,2)}</td><td>${l.p!=null?fmt(l.p,4):"—"} ${l.p!=null&&l.p<0.05?"significativo":""}</td></tr>`;
  });
  h+=`</tbody></table></div>`;
  if(a.kruskal) h+=`<p class="dica">Kruskal-Wallis (não-paramétrico): H=${fmt(a.kruskal.H,2)}, p=${fmt(a.kruskal.p,4)}.</p>`;
  out.appendChild(secao("Tabela da ANOVA", h));

  const cm = rel.comparacao_medias || {};
  renderComparacoes(out, cm, rel.descritiva);
}

/* ---- GLM contagem/proporção ---- */
function renderGlm(out, a){
  const medias = a.medias_estimadas || a.proporcoes_estimadas;
  const rotulo = a.proporcoes_estimadas ? "Proporção estimada" : "Média estimada";
  let head = `<div>${chip(a.familia,"chip-info")} ${a.sobredispersao?chip("φ="+fmt(a.sobredispersao.phi,2),(a.sobredispersao.sobredisperso?"chip-alerta":"chip-ok")):""}</div>`;
  if(a.nota_modelo) head += `<p class="dica">${a.nota_modelo}</p>`;
  out.appendChild(secao(a.tipo_analise, head));

  let h=`<div class="tab-rolavel"><table><thead><tr><th>Tratamento</th><th>${rotulo}</th><th>Grupo</th></tr></thead><tbody>`;
  a.ordem.forEach(t=> h+=`<tr><td>${t}</td><td>${fmt(medias[t],3)}</td><td><span class="letra">${a.letras[t]||""}</span></td></tr>`);
  h+=`</tbody></table></div><p class="dica">Tratamentos com a mesma letra não diferem (α=${a.alfa}).</p>`;
  const b=secao("Comparação de tratamentos", h);
  const cv=el("canvas"); cv.width=600; cv.height=300; b.appendChild(cv);
  out.appendChild(b);
  desenharBarras(cv, a.ordem, medias, a.letras, rotulo);
}

function renderComparacoes(out, cm, descritiva){
  const medias={}, erros={};
  (descritiva||[]).forEach(d=>{ medias[d.tratamento]=d.media; if(d.ep!=null) erros[d.tratamento]=d.ep; });
  ["tukey","scott_knott","dunn"].forEach(metodo=>{
    const r=cm[metodo]; if(!r) return;
    const ordem = r.ordem || Object.keys(r.letras);
    const valores = r.medias || r.medianas || medias;
    let h=`<div class="tab-rolavel"><table><thead><tr><th>Tratamento</th><th>${r.medianas?"Mediana":"Média"}</th>${r.medianas?"":"<th>± EP</th>"}<th>Grupo</th></tr></thead><tbody>`;
    ordem.forEach(t=> h+=`<tr><td>${t}</td><td>${fmt(valores[t],3)}</td>${r.medianas?"":`<td>${erros[t]!=null?"± "+fmt(erros[t],2):"—"}</td>`}<td><span class="letra">${r.letras[t]||""}</span></td></tr>`);
    h+=`</tbody></table></div><p class="dica">Mesma letra = não diferem (α=${r.alfa}).${r.medianas?"":" Barras = média ± erro-padrão."}</p>`;
    const b=secao(r.metodo, h);
    const cv=el("canvas"); cv.width=600; cv.height=300; b.appendChild(cv);
    out.appendChild(b);
    desenharBarras(cv, ordem, valores, r.letras, r.medianas?"Mediana":"Média", r.medianas?null:erros);
  });
}

/* ----------------------------------------------------------------------- */
/* Render — Mortalidade no tempo                                           */
/* ----------------------------------------------------------------------- */
function renderRelatorioTempo(rel){
  const out=$("#resultados"); out.innerHTML="";
  $("#card-resultados").classList.remove("oculto");
  setNavTravado("resultados", false);
  setNavAtivo("resultados");
  if(!rel.ok){
    out.appendChild(renderErroRelatorio(rel));
    $("#card-resultados").scrollIntoView({behavior:"smooth"}); return;
  }
  renderPipelineRelatorio(out);
  // Cabeçalho
  out.appendChild(secao(rel.tipo_analise,
    `<div>${chip(rel.n_tratamentos+" tratamentos","chip-info")} ${chip(rel.tempos.length+" tempos","chip-info")} `+
    `${chip("controle: "+rel.controle,"chip-info")} ${chip("correção: "+rel.correcao,"chip-ok")}</div>`));
  (rel.avisos||[]).forEach(a=> out.appendChild(htmlBloco(`<div class="aviso"><b>Aviso:</b> ${a}</div>`)));

  // QA/QC
  const qa=rel.qa_qc||{};
  let qah=`<div>`+
    (qa.controle_ok===true?chip("controle OK","chip-ok"):qa.controle_ok===false?chip("controle FORA do critério","chip-alerta"):"")+
    chip("impossíveis: "+qa.impossiveis, qa.impossiveis?"chip-alerta":"chip-ok")+
    chip("duplicatas: "+qa.duplicatas, qa.duplicatas?"chip-alerta":"chip-ok")+
    chip("vivos↑ no tempo: "+qa.monotonicidade, qa.monotonicidade?"chip-alerta":"chip-ok")+`</div>`;
  if((qa.controle||[]).length){
    qah+=`<div class="tab-rolavel"><table><thead><tr><th>Tempo</th><th>Mort. controle</th><th>Estabilidade</th><th>OK?</th></tr></thead><tbody>`;
    qa.controle.forEach(c=> qah+=`<tr><td>${fmt(c.tempo,0)}</td><td>${fmt(c.mort_media,1)}%</td><td>${fmt(c.estabilidade,1)}%</td><td>${c.ok_mort&&c.ok_estab?"sim":"não"}</td></tr>`);
    qah+=`</tbody></table></div>`;
  }
  out.appendChild(secao("QA/QC", qah));

  // Curva de mortalidade no tempo
  if((rel.tempos||[]).length>=2){
    const bc=secao("Mortalidade (%) ao longo do tempo","");
    const cv=el("canvas"); cv.width=600; cv.height=300; bc.appendChild(cv);
    out.appendChild(bc);
    desenharLinhasTempo(cv, rel.letras_mortalidade, rel.tratamentos, "mortalidade (%)");
  }

  // Letras por tempo
  out.appendChild(secao("Mortalidade (%) por tempo — letras",
    tabelaLetrasTempo(rel.letras_mortalidade, rel.tratamentos)));
  if((rel.letras_eficacia||[]).some(l=>Object.keys(l.medias||{}).length))
    out.appendChild(secao("Eficácia (%) por tempo — letras",
      tabelaLetrasTempo(rel.letras_eficacia, rel.tratamentos.filter(t=>t!==rel.controle))));

  // Rankings
  const rk=rel.rankings||{};
  out.appendChild(secao("Rankings",
    `<div class="grid-rank">`+
    blocoRanking("Mortalidade — média no tempo", rk.mort_global, "%")+
    blocoRanking("Mortalidade — tempo final", rk.mort_final, "%")+
    blocoRanking("Eficácia — média no tempo", rk.efic_global, "%")+
    blocoRanking("Eficácia — tempo final", rk.efic_final, "%")+`</div>`));

  // Kaplan-Meier
  const km=rel.kaplan_meier;
  if(km && (km.curvas||[]).length){
    let kh=`<div class="tab-rolavel"><table><thead><tr><th>Tratamento</th><th>LT50</th><th>LT90</th><th>n</th><th>mortes</th></tr></thead><tbody>`;
    km.curvas.forEach(c=> kh+=`<tr><td>${c.tratamento}</td><td>${c.LT50!=null?fmt(c.LT50,2):"—"}</td><td>${c.LT90!=null?fmt(c.LT90,2):"—"}</td><td>${c.n}</td><td>${c.mortes}</td></tr>`);
    kh+=`</tbody></table></div>`;
    if(km.logrank) kh+=`<p class="dica">Log-rank: χ²=${fmt(km.logrank.qui2,2)} (gl=${km.logrank.gl}), `+
      `${km.logrank.significativo?chip("p="+fmt(km.logrank.p,4)+" — diferem","chip-ok"):chip("p="+fmt(km.logrank.p,4)+" — não diferem","chip-info")}</p>`;
    kh+=`<p class="dica">LT50/LT90 = tempo para 50%/90% de mortalidade (interpolado; "—" = não atingido no período).</p>`;
    const b=secao("Kaplan-Meier (sobrevivência) + LT50/LT90", kh);
    const cv=el("canvas"); cv.width=600; cv.height=320; b.appendChild(cv);
    out.appendChild(b);
    desenharKM(cv, km.curvas, rel.tempos);
  }

  // Modelos
  const mo=rel.modelos||{};
  let moh="";
  if(mo.glm_robusto){
    moh+= mo.glm_robusto.convergiu
      ? `<div class="kv"><dt>GLM binomial (cluster)</dt><dd>efeito de tratamento ${p_chip(mo.glm_robusto.p_tratamento)} ${mo.glm_robusto.p_tempo!=null?"• tempo "+p_chip(mo.glm_robusto.p_tempo):""}</dd></div><p class="dica">${mo.glm_robusto.nota||""}</p>`
      : `<p class="dica">GLM robusto não convergiu.</p>`;
  }
  if(mo.beta_eficacia && mo.beta_eficacia.convergiu){
    moh+= `<div class="kv"><dt>Beta-regressão (eficácia, tempo ${fmt(mo.beta_eficacia.tempo,0)})</dt><dd>efeito de tratamento ${p_chip(mo.beta_eficacia.p_tratamento)}</dd></div>`;
  }
  if(moh) out.appendChild(secao("Modelos (inferência)", moh));

  $("#card-resultados").scrollIntoView({behavior:"smooth"});
}

function tabelaLetrasTempo(linhas, tratamentos){
  if(!linhas || !linhas.length) return `<p class="dica">Sem dados.</p>`;
  let h=`<div class="tab-rolavel"><table><thead><tr><th>Tratamento</th>`;
  linhas.forEach(l=> h+=`<th>t=${fmt(l.tempo,0)}</th>`);
  h+=`</tr></thead><tbody>`;
  tratamentos.forEach(tr=>{
    h+=`<tr><td>${tr}</td>`;
    linhas.forEach(l=>{
      const m=(l.medias||{})[tr], ltr=(l.letras||{})[tr]||"";
      h+= m!=null ? `<td>${fmt(m,1)} <span class="letra">${ltr}</span></td>` : `<td>—</td>`;
    });
    h+=`</tr>`;
  });
  h+=`</tbody></table></div>`;
  h+=`<p class="dica">Método por tempo: `+linhas.map(l=>`t=${fmt(l.tempo,0)}: ${l.metodo}`).join(" • ")+`</p>`;
  return h;
}
function blocoRanking(titulo, lista, suf){
  if(!lista || !lista.length) return "";
  let h=`<div class="rank-card"><b>${titulo}</b><ol>`;
  lista.slice(0,8).forEach(r=> h+=`<li>${r.item||r.tratamento} — <b>${fmt(r.valor,1)}${suf}</b></li>`);
  h+=`</ol></div>`;
  return h;
}
function desenharKM(cv, curvas, tempos){
  const ctx=cv.getContext("2d"); const W=cv.width,H=cv.height; ctx.clearRect(0,0,W,H);
  const ml=46,mr=120,mt=14,mb=40, pw=W-ml-mr, ph=H-mt-mb;
  const tmax=Math.max(...tempos,1);
  const X=t=> ml+(t/tmax)*pw, Y=s=> mt+ph-s*ph;
  ctx.strokeStyle="#cbd5e1"; ctx.beginPath(); ctx.moveTo(ml,mt); ctx.lineTo(ml,mt+ph); ctx.lineTo(ml+pw,mt+ph); ctx.stroke();
  ctx.fillStyle="#64748b"; ctx.font="11px sans-serif"; ctx.textAlign="right";
  [0,.25,.5,.75,1].forEach(s=>{ const y=Y(s); ctx.fillText((s*100)+"%",ml-5,y+4); ctx.strokeStyle="#eef2f7"; ctx.beginPath(); ctx.moveTo(ml,y); ctx.lineTo(ml+pw,y); ctx.stroke(); });
  const cores=["#0d9488","#0891b2","#4338ca","#b45309","#9333ea","#0e7490","#be123c","#15803d"];
  curvas.forEach((c,i)=>{
    const col=cores[i%cores.length]; ctx.strokeStyle=col; ctx.lineWidth=2; ctx.beginPath();
    let px=X(0), py=Y(1); ctx.moveTo(px,py);
    for(let k=0;k<c.tempos.length;k++){ const nx=X(c.tempos[k]); ctx.lineTo(nx,py); const ny=Y(c.surv[k]); ctx.lineTo(nx,ny); py=ny; px=nx; }
    ctx.stroke(); ctx.lineWidth=1;
    ctx.fillStyle=col; ctx.textAlign="left"; ctx.font="11px sans-serif";
    ctx.fillText(String(c.tratamento).slice(0,12), ml+pw+6, mt+12+i*15);
  });
  // linha 50%
  ctx.strokeStyle="rgba(198,40,40,.5)"; ctx.setLineDash([4,3]); ctx.beginPath(); ctx.moveTo(ml,Y(0.5)); ctx.lineTo(ml+pw,Y(0.5)); ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle="#475569"; ctx.textAlign="center"; ctx.font="12px sans-serif";
  ctx.fillText("tempo", ml+pw/2, mt+ph+30);
  ctx.save(); ctx.translate(13,mt+ph/2); ctx.rotate(-Math.PI/2); ctx.fillText("sobrevivência", 0, 0); ctx.restore();
}

const CORES_CAT=["#0d9488","#0891b2","#4338ca","#b45309","#9333ea","#0e7490","#be123c","#15803d"];
function desenharLinhasTempo(cv, linhas, tratamentos, ylabel){
  const ctx=cv.getContext("2d"); const W=cv.width,H=cv.height; ctx.clearRect(0,0,W,H);
  const ml=46,mr=120,mt=14,mb=40, pw=W-ml-mr, ph=H-mt-mb;
  const tempos=linhas.map(l=>l.tempo); const tmin=Math.min(...tempos), tmax=Math.max(...tempos);
  let vmax=0; linhas.forEach(l=>tratamentos.forEach(t=>{ const m=(l.medias||{})[t]; if(m!=null&&m>vmax)vmax=m; }));
  vmax=Math.max(vmax*1.1,1);
  const X=t=> ml+(tmax===tmin?0.5:(t-tmin)/(tmax-tmin))*pw, Y=v=> mt+ph-(v/vmax)*ph;
  ctx.strokeStyle="#cbd5e1"; ctx.beginPath(); ctx.moveTo(ml,mt); ctx.lineTo(ml,mt+ph); ctx.lineTo(ml+pw,mt+ph); ctx.stroke();
  ctx.fillStyle="#64748b"; ctx.font="11px sans-serif"; ctx.textAlign="right";
  for(let i=0;i<=4;i++){ const v=vmax*i/4, y=Y(v); ctx.fillText(fmt(v,0),ml-5,y+4); ctx.strokeStyle="#eef2f7"; ctx.beginPath(); ctx.moveTo(ml,y); ctx.lineTo(ml+pw,y); ctx.stroke(); }
  ctx.textAlign="center"; ctx.fillStyle="#64748b";
  tempos.forEach(t=> ctx.fillText("t="+fmt(t,0), X(t), mt+ph+16));
  tratamentos.forEach((t,i)=>{
    const col=CORES_CAT[i%CORES_CAT.length]; ctx.strokeStyle=col; ctx.fillStyle=col; ctx.lineWidth=2.2; ctx.beginPath();
    let started=false;
    linhas.forEach(l=>{ const m=(l.medias||{})[t]; if(m==null)return; const px=X(l.tempo),py=Y(m); started?ctx.lineTo(px,py):ctx.moveTo(px,py); started=true; });
    ctx.stroke(); ctx.lineWidth=1;
    linhas.forEach(l=>{ const m=(l.medias||{})[t]; if(m==null)return; ctx.beginPath(); ctx.arc(X(l.tempo),Y(m),3,0,6.28); ctx.fill(); });
    ctx.textAlign="left"; ctx.font="11px sans-serif"; ctx.fillText(String(t).slice(0,12), ml+pw+6, mt+12+i*15);
  });
  ctx.save(); ctx.translate(13,mt+ph/2); ctx.rotate(-Math.PI/2); ctx.textAlign="center"; ctx.fillStyle="#475569"; ctx.font="12px sans-serif"; ctx.fillText(ylabel,0,0); ctx.restore();
}

/* ----------------------------------------------------------------------- */
/* Gráficos (canvas)                                                       */
/* ----------------------------------------------------------------------- */
function desenharBarras(cv, ordem, valores, letras, ylabel){
  const ctx=cv.getContext("2d"); const W=cv.width,H=cv.height;
  ctx.clearRect(0,0,W,H); ctx.font="13px sans-serif";
  const ml=46,mr=14,mt=22,mb=64; const pw=W-ml-mr, ph=H-mt-mb;
  const vals=ordem.map(t=>valores[t]||0);
  const erros=arguments[5]||null;  // map trat -> erro-padrão (opcional)
  const topo=ordem.map(t=>(valores[t]||0)+(erros&&erros[t]?erros[t]:0));
  const vmax=Math.max(...topo,0.0001)*1.16, vmin=Math.min(0,...vals);
  const y0=v=> mt+ph-(v-vmin)/(vmax-vmin)*ph;
  // eixos
  ctx.strokeStyle="#cbd5e1"; ctx.beginPath(); ctx.moveTo(ml,mt); ctx.lineTo(ml,mt+ph); ctx.lineTo(ml+pw,mt+ph); ctx.stroke();
  ctx.fillStyle="#64748b"; ctx.textAlign="right"; ctx.font="11px sans-serif";
  for(let i=0;i<=4;i++){ const v=vmin+(vmax-vmin)*i/4; const y=y0(v); ctx.fillText(fmt(v,1),ml-5,y+4); ctx.strokeStyle="#eef2f7"; ctx.beginPath(); ctx.moveTo(ml,y); ctx.lineTo(ml+pw,y); ctx.stroke(); }
  const bw=pw/ordem.length*0.62;
  ordem.forEach((t,i)=>{
    const cx=ml+pw*(i+0.5)/ordem.length; const v=valores[t]||0; const y=y0(v);
    // barra (degradê teal)
    const grad=ctx.createLinearGradient(0,y,0,mt+ph); grad.addColorStop(0,"#14b8a6"); grad.addColorStop(1,"#0d9488");
    ctx.fillStyle=grad; ctx.fillRect(cx-bw/2,y,bw,mt+ph-y);
    // barra de erro (média ± EP)
    const se=erros&&erros[t]?erros[t]:0;
    if(se>0){ const yt=y0(v+se), yb=y0(v-se); ctx.strokeStyle="#0f766e"; ctx.lineWidth=1.5;
      ctx.beginPath(); ctx.moveTo(cx,yt); ctx.lineTo(cx,yb); ctx.moveTo(cx-5,yt); ctx.lineTo(cx+5,yt); ctx.moveTo(cx-5,yb); ctx.lineTo(cx+5,yb); ctx.stroke(); ctx.lineWidth=1; }
    ctx.fillStyle="#0f766e"; ctx.textAlign="center"; ctx.font="bold 13px sans-serif";
    ctx.fillText(letras[t]||"", cx, y0(v+se)-6);
    ctx.fillStyle="#334155"; ctx.font="11px sans-serif";
    ctx.save(); ctx.translate(cx,mt+ph+8); ctx.rotate(-Math.PI/7); ctx.textAlign="right";
    ctx.fillText(String(t).slice(0,14),0,6); ctx.restore();
  });
  ctx.save(); ctx.translate(13,mt+ph/2); ctx.rotate(-Math.PI/2); ctx.textAlign="center"; ctx.fillStyle="#475569"; ctx.font="12px sans-serif"; ctx.fillText(ylabel,0,0); ctx.restore();
}

function desenharDose(cv, c, uni){
  uni = (uni||"").trim();
  const ctx=cv.getContext("2d"); const W=cv.width,H=cv.height;
  ctx.clearRect(0,0,W,H);
  const ml=48,mr=16,mt=16,mb=46; const pw=W-ml-mr, ph=H-mt-mb;
  // domínio em log10(dose) a partir das doses letais (usa CL10..CL99 p/ amplitude)
  const dls=c.doses_letais; const xs=dls.map(d=>d.log_dose);
  let xmin=Math.min(...xs), xmax=Math.max(...xs); const pad=(xmax-xmin)*0.25||0.5; xmin-=pad; xmax+=pad;
  const X=x=> ml+(x-xmin)/(xmax-xmin)*pw;
  const Y=p=> mt+ph-p*ph;
  ctx.strokeStyle="#cbd5e1"; ctx.beginPath(); ctx.moveTo(ml,mt); ctx.lineTo(ml,mt+ph); ctx.lineTo(ml+pw,mt+ph); ctx.stroke();
  ctx.fillStyle="#64748b"; ctx.textAlign="right"; ctx.font="11px sans-serif";
  [0,.25,.5,.75,1].forEach(p=>{ const y=Y(p); ctx.fillText((p*100)+"%",ml-5,y+4); ctx.strokeStyle="#eef2f7"; ctx.beginPath(); ctx.moveTo(ml,y); ctx.lineTo(ml+pw,y); ctx.stroke(); });
  // curva ajustada
  const b0=c.intercepto,b1=c.slope, probit=(c.link==="probit");
  const F = probit ? (z=>0.5*(1+erf(z/Math.SQRT2))) : (z=>1/(1+Math.exp(-z)));
  ctx.strokeStyle="#0f766e"; ctx.lineWidth=2.2; ctx.beginPath();
  for(let i=0;i<=120;i++){ const x=xmin+(xmax-xmin)*i/120; const p=F(b0+b1*x); const px=X(x),py=Y(p); i?ctx.lineTo(px,py):ctx.moveTo(px,py); }
  ctx.stroke(); ctx.lineWidth=1;
  // linha CL50
  const cl50=dls.find(d=>d.p===0.5);
  if(cl50){ const x=cl50.log_dose; ctx.strokeStyle="#b91c1c"; ctx.setLineDash([5,4]); ctx.beginPath(); ctx.moveTo(X(x),Y(0.5)); ctx.lineTo(X(x),mt+ph); ctx.moveTo(ml,Y(0.5)); ctx.lineTo(X(x),Y(0.5)); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle="#b91c1c"; ctx.textAlign="left"; ctx.fillText("CL50 = "+fmt(cl50.dose,2)+(uni?" "+uni:""), X(x)+4, mt+12); }
  // rótulo eixo x
  ctx.fillStyle="#475569"; ctx.textAlign="center"; ctx.font="12px sans-serif";
  const eixoX = (c.escala_dose==="log10"?"log₁₀(dose)":"dose") + (uni?" — "+uni:"");
  ctx.fillText(eixoX, ml+pw/2, mt+ph+34);
  ctx.fillText("mortalidade", 12, mt+ph/2);
}
// erf para a curva probit
function erf(x){ const t=1/(1+0.3275911*Math.abs(x)); const y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t*Math.exp(-x*x); return x>=0?y:-y; }

/* ----------------------------------------------------------------------- */
/* Exportar                                                                */
/* ----------------------------------------------------------------------- */
$("#btn-imprimir").addEventListener("click", ()=>window.print());
$("#btn-copiar").addEventListener("click", ()=>{
  navigator.clipboard.writeText($("#resultados").innerText).then(()=>avisar("Relatório copiado.", "ok"));
});

/* Service worker */
if("serviceWorker" in navigator){ navigator.serviceWorker.register("sw.js").catch(()=>{}); }
