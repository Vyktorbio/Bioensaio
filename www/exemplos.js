// Conjuntos de exemplo (cobrem os principais cenários de bioensaio).
window.EXEMPLOS = {
  "Dose-resposta (mortalidade, inseticida)": {
    papeis: { resposta: "mortos", n_total: "total", dose: "dose_ppm" },
    colunas: ["dose_ppm", "total", "mortos"],
    linhas: [
      [49, 59, 6], [53, 60, 13], [57, 62, 18], [61, 56, 28],
      [65, 63, 52], [69, 59, 53], [73, 62, 61], [77, 60, 60],
    ],
    obs: "Curva clássica (Bliss 1935). CL50 ≈ 59 ppm. Calcula CL50/CL90, IC de Fieller, qui², heterogeneidade.",
  },
  "Dose-resposta: 2 populações (resistência)": {
    papeis: { resposta: "mortos", n_total: "total", dose: "dose_ppm", fatores: ["populacao"] },
    colunas: ["populacao", "dose_ppm", "total", "mortos"],
    linhas: [
      ["Suscetivel", 5, 40, 6], ["Suscetivel", 7.5, 40, 14], ["Suscetivel", 10, 40, 20],
      ["Suscetivel", 15, 40, 28], ["Suscetivel", 20, 40, 33],
      ["Resistente", 25, 40, 6], ["Resistente", 37.5, 40, 14], ["Resistente", 50, 40, 20],
      ["Resistente", 75, 40, 28], ["Resistente", 100, 40, 33],
    ],
    obs: "Duas curvas → razão de resistência (CL50 Resistente / Suscetível ≈ 5×), IC, paralelismo.",
  },
  "Eficácia de fungicidas (mortos de n)": {
    papeis: { resposta: "afetados", n_total: "n", fatores: ["produto"] },
    colunas: ["produto", "n", "afetados"],
    linhas: [
      ["Testemunha", 25, 3], ["Testemunha", 25, 4], ["Testemunha", 25, 2],
      ["Fung_A", 25, 20], ["Fung_A", 25, 22], ["Fung_A", 25, 19],
      ["Fung_B", 25, 12], ["Fung_B", 25, 14], ["Fung_B", 25, 11],
    ],
    obs: "Proporção x de n por produto → GLM binomial com letras de comparação.",
  },
  "Severidade (%) de doença em campo": {
    papeis: { resposta: "severidade", fatores: ["tratamento"] },
    colunas: ["tratamento", "bloco", "severidade"],
    papeis_extra: { bloco: "bloco" },
    linhas: [
      ["Testemunha", 1, 78.5], ["Testemunha", 2, 82.1], ["Testemunha", 3, 80.0], ["Testemunha", 4, 79.3],
      ["T1", 1, 45.2], ["T1", 2, 48.1], ["T1", 3, 44.0], ["T1", 4, 46.7],
      ["T2", 1, 12.3], ["T2", 2, 14.0], ["T2", 3, 11.8], ["T2", 4, 13.1],
      ["T3", 1, 9.5], ["T3", 2, 8.2], ["T3", 3, 10.1], ["T3", 4, 7.9],
    ],
    obs: "Severidade % (proporção contínua) em blocos → ANOVA + Tukey/Scott-Knott.",
  },
  "Diâmetro de colônia (mm) — laboratório": {
    papeis: { resposta: "diametro", fatores: ["isolado"] },
    colunas: ["isolado", "diametro"],
    linhas: [
      ["Controle", 85.2], ["Controle", 84.1], ["Controle", 86.0], ["Controle", 85.5],
      ["Trat_A", 42.1], ["Trat_A", 40.5], ["Trat_A", 43.0], ["Trat_A", 41.2],
      ["Trat_B", 38.5], ["Trat_B", 39.1], ["Trat_B", 37.8], ["Trat_B", 38.9],
      ["Trat_C", 15.2], ["Trat_C", 16.1], ["Trat_C", 14.8], ["Trat_C", 15.9],
    ],
    obs: "Medida contínua → ANOVA, normalidade, homogeneidade, Tukey e Scott-Knott.",
  },
  "Nº de colônias / contagem": {
    papeis: { resposta: "colonias", fatores: ["meio"] },
    colunas: ["meio", "colonias"],
    linhas: [
      ["BDA", 45], ["BDA", 52], ["BDA", 48], ["BDA", 50], ["BDA", 47],
      ["Aveia", 30], ["Aveia", 28], ["Aveia", 33], ["Aveia", 29], ["Aveia", 31],
      ["V8", 62], ["V8", 58], ["V8", 65], ["V8", 60], ["V8", 63],
    ],
    obs: "Contagem (inteiros) → GLM Poisson / Binomial Negativa se sobredisperso.",
  },
  "Germinação (vivo/morto por indivíduo)": {
    papeis: { resposta: "germinou", fatores: ["lote"] },
    colunas: ["lote", "germinou"],
    linhas: (() => {
      const r = [];
      const add = (lote, sim, nao) => { for (let i=0;i<sim;i++) r.push([lote,"sim"]); for (let i=0;i<nao;i++) r.push([lote,"nao"]); };
      add("L1", 45, 5); add("L2", 30, 20); add("L3", 38, 12);
      return r;
    })(),
    obs: "Binária por semente (sim/não) → agrega em proporção e aplica GLM binomial.",
  },
};

// Exemplos do módulo "Mortalidade no tempo"
window.EXEMPLOS_TEMPO = {
  "Inseticidas — mortalidade em 0/3/7 dias": {
    papeis: { tratamento:"trat", item_teste:"item", repeticao:"rep", tempo:"dia", n_total:"n_inicial", n_vivos:"n_vivos" },
    colunas: ["item","trat","rep","dia","n_inicial","n_vivos"],
    linhas: (() => {
      const perfil = {
        "T1": {item:"Testemunha",        v:[20,20,19]},
        "T2": {item:"Inseticida A 100 mL/ha", v:[20,16,11]},
        "T3": {item:"Inseticida B 150 mL/ha", v:[20,10,5]},
        "T4": {item:"Inseticida C 200 mL/ha", v:[20,6,2]},
      };
      const dias=[0,3,7], out=[];
      Object.entries(perfil).forEach(([t,info])=>{
        for(let rep=1;rep<=3;rep++){
          dias.forEach((d,k)=>{
            let v=info.v[k];
            if(d>0) v=Math.max(0,Math.min(20, v + (rep-2))); // pequena variação por rep
            out.push([info.item, t, rep, d, 20, v]);
          });
        }
      });
      return out;
    })(),
    obs: "Mortalidade ao longo do tempo → correção de Abbott, letras por dia, LT50/LT90 (Kaplan-Meier), log-rank, QA do controle.",
  },
};
