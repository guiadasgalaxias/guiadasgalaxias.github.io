/**
 * Guia do Extensionista das Galáxias: backend em Apps Script, ligado a uma planilha Google.
 *
 * doGet  -> devolve só o que está com status "aprovado" (ou "removido"), sem nome nem data de ninguém.
 * doPost -> indicação de lugar e confirmação entram direto ("aprovado"); avaliação e correção
 *           ficam "pendente" para um mantenedor conferir.
 *
 * Confirmação: outro colega atesta que usou e recomenda. Cada nome conta uma vez por lugar,
 * e o site ordena os lugares pelos mais confirmados.
 *
 * Moderação: na planilha, troque a coluna "status" para "aprovado" ou "rejeitado".
 * Para tirar um lugar da lista (inclusive da base inicial), ponha uma linha na aba "lugares"
 * com o id dele e status "removido".
 */

const ABAS = {
  lugares: ["quando", "status", "id", "t", "n", "e", "m", "tel", "wa", "email", "ok", "valor", "almoco", "jantar", "lat", "lon", "proximos", "autor", "nota", "comentario"],
  avaliacoes: ["quando", "status", "id", "autor", "data", "limpeza", "atendimento", "conforto", "preco", "ok", "comentario", "remover"],
  correcoes: ["quando", "status", "id", "texto", "autor"],
  confirmacoes: ["quando", "status", "id", "autor", "ok", "nota", "comentario", "data", "remover"],
  vinculos: ["quando", "status", "m_a", "m_b", "autor"],
};
const TIPOS = ["hotel", "rest", "posto"];
const MAX_POR_HORA = 60; // ponytail: teto global contra spam; trocar por reCAPTCHA se abusarem
const CACHE_SEG = 300;
const PUBLICOS_LUGAR = ["id", "status", "t", "n", "e", "m", "tel", "wa", "email", "ok", "almoco", "jantar", "lat", "lon"];

/** Cria as abas com cabeçalho (roda sozinha na primeira chamada; pode rodar de novo sem perder dados). */
function setup() {
  const ss = SpreadsheetApp.getActive();
  Object.keys(ABAS).forEach((nome) => {
    const aba = ss.getSheetByName(nome) || ss.insertSheet(nome);
    aba.getRange(1, 1, 1, ABAS[nome].length).setValues([ABAS[nome]]).setFontWeight("bold");
    aba.setFrozenRows(1);
  });
}

/** Primeira chamada numa planilha nova cria as abas sozinha. */
function garanteAbas() {
  const ss = SpreadsheetApp.getActive();
  // Aba faltando ou com menos colunas que o esperado (versão antiga): recria os cabeçalhos, sem tocar nos dados.
  const desatualizada = (nome) => { const aba = ss.getSheetByName(nome); return !aba || aba.getLastColumn() < ABAS[nome].length; };
  if (Object.keys(ABAS).some(desatualizada)) setup();
}

function responde(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/** Texto seguro para célula: corta tamanho e impede que vire fórmula. */
function limpa(valor, max) {
  const texto = String(valor == null ? "" : valor).replace(/[\u0000-\u001f]+/g, " ").trim().slice(0, max);
  return /^[=+\-@]/.test(texto) ? "'" + texto : texto;
}
/** Só DDD + número (10 ou 11 dígitos): tira zero inicial e o DDI 55, que o site já acrescenta nos links. */
function soDigitos(valor) {
  const d = String(valor || "").replace(/\D/g, "").replace(/^0+/, "").replace(/^55(?=\d{10,11}$)/, "");
  return /^\d{10,11}$/.test(d) ? d : "";
}
function nota(valor) {
  const n = Number(valor);
  if (!(n >= 1 && n <= 5)) throw new Error("dê uma nota de 1 a 5 estrelas");
  return Math.round(n);
}
function linhas(nome) {
  const aba = SpreadsheetApp.getActive().getSheetByName(nome);
  if (!aba) return []; // aba ainda não criada: rode setup()
  const dados = aba.getDataRange().getValues();
  const cab = dados.shift();
  return dados.map((l) => Object.fromEntries(cab.map((c, i) => [c, l[i]])));
}

function doGet() {
  try {
    garanteAbas();
    const cache = CacheService.getScriptCache();
    const pronto = cache.get("publico");
    if (pronto) return ContentService.createTextOutput(pronto).setMimeType(ContentService.MimeType.JSON);

    const todosLugares = linhas("lugares");
    const lugares = todosLugares
      .filter((l) => l.status === "aprovado" || l.status === "removido")
      .map((l) => Object.fromEntries(PUBLICOS_LUGAR.map((c) => [c, l[c]])));

    const notas = {};
    const eSim = (v) => v === true || v === 1 || v === "1";
    /** Soma uma nota (1 a 5) ao lugar; o comentário sai com a nota de quem escreveu, sem o nome. */
    const pontua = (id, valor, ok, comentario) => {
      if (!(valor >= 1 && valor <= 5)) return;
      const n = notas[id] || (notas[id] = { n: 0, soma: 0, ok: false, comentarios: [] });
      n.n += 1;
      n.soma += valor;
      n.ok = n.ok || eSim(ok);
      if (comentario) n.comentarios.push({ nota: Math.round(valor), texto: String(comentario) });
    };
    todosLugares.filter((l) => l.status === "aprovado").forEach((l) => pontua(l.id, Number(l.nota), l.ok, l.comentario));
    const confirmacoes = linhas("confirmacoes").filter((c) => c.status === "aprovado");
    // Cada colega pontua um lugar uma vez: se confirmar de novo, vale a nota mais recente.
    const ultima = {};
    confirmacoes.forEach((c) => { if (c.nota !== "") ultima[c.id + "|" + String(c.autor).trim().toLowerCase()] = c; });
    Object.keys(ultima).forEach((k) => pontua(ultima[k].id, Number(ultima[k].nota), ultima[k].ok, ultima[k].comentario));
    linhas("avaliacoes").filter((a) => a.status === "aprovado").forEach((a) =>
      pontua(a.id, (Number(a.limpeza) + Number(a.atendimento) + Number(a.conforto) + Number(a.preco)) / 4, a.ok, a.comentario));
    Object.keys(notas).forEach((id) => {
      notas[id].media = Math.round((notas[id].soma / notas[id].n) * 10) / 10;
      delete notas[id].soma;
    });

    // Confirmações: conta nomes distintos por lugar; o nome em si não sai daqui.
    const confirma = {};
    const jaContou = {};
    confirmacoes.forEach((c) => {
      const quem = c.id + "|" + String(c.autor).trim().toLowerCase();
      const item = confirma[c.id] || (confirma[c.id] = { n: 0, ok: false });
      // Quem pede a remoção deixa nota e comentário, mas não soma como confirmação.
      if (!jaContou[quem] && c.remover !== "SIM") { jaContou[quem] = true; item.n += 1; }
      item.ok = item.ok || eSim(c.ok);
    });

    const vinculos = linhas("vinculos").filter((v) => v.status === "aprovado").map((v) => [Number(v.m_a), Number(v.m_b)]);

    const saida = JSON.stringify({ success: true, data: { lugares, notas, confirma, vinculos }, error: null });
    try { cache.put("publico", saida, CACHE_SEG); } catch (_) { /* passou de 100 KB: segue sem cache */ }
    return ContentService.createTextOutput(saida).setMimeType(ContentService.MimeType.JSON);
  } catch (erro) {
    console.error(erro);
    return responde({ success: false, data: null, error: "não foi possível ler a lista" });
  }
}

function doPost(e) {
  const trava = LockService.getScriptLock();
  try {
    garanteAbas();
    const d = JSON.parse(e.postData.contents);
    if (d.site) return responde({ success: true, data: null, error: null }); // campo-isca preenchido: robô

    const autor = limpa(d.autor, 80);
    if (!autor) throw new Error("informe seu nome");
    const agora = new Date();
    // Texto em horário de Brasília: não depende do fuso configurado na planilha.
    const quando = Utilities.formatDate(agora, "America/Sao_Paulo", "yyyy-MM-dd HH:mm:ss");
    let aba;
    let registro;

    if (d.tipo === "lugar") {
      if (TIPOS.indexOf(d.t) < 0) throw new Error("tipo inválido");
      const m = Number(d.m);
      if (!Number.isInteger(m) || !(m > 4100000 && m < 4200000)) throw new Error("município inválido");
      const n = limpa(d.n, 120);
      const end = limpa(d.e, 200);
      const tel = soDigitos(d.tel);
      const wa = soDigitos(d.wa);
      const email = limpa(d.email, 120);
      if (!n || !end || !tel) throw new Error("nome, endereço e telefone com DDD são obrigatórios");
      if (!wa && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new Error("informe WhatsApp ou e-mail");
      if (d.t === "hotel" && !d.ok) throw new Error("só entram hotéis cujo valor cabe na diária");
      aba = "lugares";
      registro = { quando, status: "aprovado", id: "c" + Utilities.getUuid().slice(0, 8), t: d.t, n, e: end, m, tel, wa, email,
        ok: d.ok ? 1 : "", valor: limpa(d.valor, 12), almoco: d.almoco ? 1 : "", jantar: d.jantar ? 1 : "", proximos: limpa(d.proximos, 200), autor,
        nota: d.nota ? nota(d.nota) : "", comentario: limpa(d.comentario, 500) };
    } else if (d.tipo === "avaliacao") {
      const id = limpa(d.id, 40);
      if (!/^[a-z0-9]+$/i.test(id)) throw new Error("lugar inválido");
      if (!/^\d{4}-\d{2}-\d{2}$/.test(d.data) || new Date(d.data) > agora) throw new Error("data inválida");
      aba = "avaliacoes";
      registro = { quando, status: "pendente", id, autor, data: d.data, limpeza: nota(d.limpeza), atendimento: nota(d.atendimento),
        conforto: nota(d.conforto), preco: nota(d.preco), ok: d.ok ? 1 : "", comentario: limpa(d.comentario, 500), remover: d.remover ? "SIM" : "" };
    } else if (d.tipo === "confirmacao") {
      const id = limpa(d.id, 40);
      if (!/^[a-z0-9]+$/i.test(id)) throw new Error("lugar inválido");
      aba = "confirmacoes";
      const data = /^\d{4}-\d{2}-\d{2}$/.test(d.data) && new Date(d.data) <= agora ? d.data : "";
      registro = { quando, status: "aprovado", id, autor, ok: d.ok ? 1 : "", nota: d.nota ? nota(d.nota) : "", comentario: limpa(d.comentario, 500),
        data, remover: d.remover ? "SIM" : "" };
    } else if (d.tipo === "correcao") {
      const id = limpa(d.id, 40);
      const texto = limpa(d.texto, 600);
      if (!/^[a-z0-9]+$/i.test(id) || !texto) throw new Error("correção vazia");
      aba = "correcoes";
      registro = { quando, status: "pendente", id, texto, autor };
    } else {
      throw new Error("tipo de envio desconhecido");
    }

    // Só envio válido conta no teto por hora, para lixo não bloquear os colegas.
    trava.waitLock(10000);
    const cache = CacheService.getScriptCache();
    const hora = "envios-" + Utilities.formatDate(new Date(), "GMT-3", "yyyyMMddHH");
    const envios = Number(cache.get(hora) || 0);
    if (envios >= MAX_POR_HORA) throw new Error("muitos envios agora, tente daqui a uma hora");
    cache.put(hora, String(envios + 1), 3700);

    const planilha = SpreadsheetApp.getActive().getSheetByName(aba);
    if (!planilha) throw new Error("planilha não configurada, avise um mantenedor");
    planilha.appendRow(ABAS[aba].map((c) => (registro[c] === undefined ? "" : registro[c])));
    cache.remove("publico"); // o que entra direto precisa aparecer já na próxima leitura
    return responde({ success: true, data: { id: registro.id }, error: null });
  } catch (erro) {
    console.error(erro);
    // Só mensagens nossas (minúsculas, em português) vão ao visitante; erro interno não vaza.
    const msg = String(erro.message || "");
    return responde({ success: false, data: null, error: /^[a-zçãéóí]/.test(msg) && !/ is | of |timeout/i.test(msg) ? msg.slice(0, 120) : "erro interno, tente de novo" });
  } finally {
    try { trava.releaseLock(); } catch (_) { /* não chegou a travar */ }
  }
}
