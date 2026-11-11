"use strict";
(() => {
  const API = window.GUIA_API || "";
  const PAGINA = 60;
  const MAX_ICONES = 400; // acima disso o mapa usa círculos em canvas (leve no celular)
  const ROTULO = { hotel: "Hotel", rest: "Restaurante", posto: "Posto" };
  const ORDEM = { hotel: 0, rest: 1, posto: 2 };

  const $ = (s, raiz = document) => raiz.querySelector(s);
  const chave = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase().replace(/[^A-Z0-9 ]/g, " ").replace(/\s+/g, " ").trim();

  /** Cria elemento sem innerHTML: todo dado externo entra como texto. */
  function el(tag, attrs = {}, ...filhos) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v == null || v === false) continue;
      if (k === "class") node.className = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    node.append(...filhos.filter((f) => f != null && f !== false));
    return node;
  }
  function icone(tipo) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `assets/sprites.svg#i-${tipo}`);
    svg.setAttribute("class", "px");
    svg.setAttribute("aria-hidden", "true");
    svg.append(use);
    return svg;
  }
  function km(a, b) {
    const r = Math.PI / 180;
    const h = Math.sin(((b.lat - a.lat) * r) / 2) ** 2 + Math.cos(a.lat * r) * Math.cos(b.lat * r) * Math.sin(((b.lon - a.lon) * r) / 2) ** 2;
    return 12742 * Math.asin(Math.sqrt(h));
  }
  const fone = (d) => (d.length === 11 ? `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}` : d.length === 10 ? `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}` : d);

  let municipios = [];
  let porCodigo = new Map();
  let porNome = new Map();
  let lugares = [];
  let notas = {};
  let confirma = {};
  let baseFixa = [];
  let vinculos = [];
  let limite = PAGINA;
  let mapa = null;
  let camada = null;
  let visiveis = [];

  const estado = () => ({
    mun: porNome.get(chave($("#mun").value)) || null,
    tipos: new Set([...document.querySelectorAll('input[name="tipo"]:checked')].map((i) => i.value)),
    q: chave($("#q").value),
    raio: Number($("#raio").value),
    soOk: $("#so-ok").checked,
    per: $("#per").value,
  });

  /** Municípios próximos de `mun`: Map(código -> {km, manual}). */
  function proximos(mun, raio) {
    const origem = porCodigo.get(mun);
    const saida = new Map();
    for (const m of municipios) {
      if (m.c === mun) continue;
      const d = km(origem, m);
      const manual = vinculos.some(([a, b]) => (a === mun && b === m.c) || (b === mun && a === m.c));
      if (d <= raio || manual) saida.set(m.c, { km: d, manual });
    }
    return saida;
  }

  function filtra(e) {
    return lugares.filter((l) =>
      e.tipos.has(l.t) &&
      (!e.soOk || l.src === "colega" || notas[l.id] || confirma[l.id]) &&
      (!e.per || l.t !== "rest" || l[e.per]) &&
      (!e.q || l.busca.includes(e.q)));
  }

  /** Pontuação que ordena a lista: confirmação vale 2, indicação de colega 1, e a nota média até 1. */
  function pontos(l) {
    return (confirma[l.id] ? confirma[l.id].n * 2 : 0) + (l.src === "colega" ? 1 : 0) + (notas[l.id] ? notas[l.id].media / 5 : 0);
  }

  /** Devolve as seções da lista: [{titulo, sub, itens, dist}]. */
  function secoes(e) {
    const base = filtra(e);
    const ordena = (a, b) => ORDEM[a.t] - ORDEM[b.t] || pontos(b) - pontos(a) || a.n.localeCompare(b.n, "pt-BR");
    if (e.mun) {
      const nome = porCodigo.get(e.mun).n;
      const perto = proximos(e.mun, e.raio);
      const local = base.filter((l) => l.m === e.mun).sort(ordena);
      const vizinhos = base.filter((l) => perto.has(l.m)).sort((a, b) => perto.get(a.m).km - perto.get(b.m).km || ordena(a, b));
      return [
        { titulo: nome, sub: `${local.length} no município`, itens: local },
        { titulo: `Na órbita de ${nome}`, sub: `${vizinhos.length} em municípios próximos`, itens: vizinhos, dist: perto },
      ];
    }
    const grupos = new Map();
    for (const l of base) (grupos.get(l.m) || grupos.set(l.m, []).get(l.m)).push(l);
    return municipios.filter((m) => grupos.has(m.c)).map((m) => {
      const itens = grupos.get(m.c).sort(ordena);
      return { titulo: m.n, sub: `${itens.length} ${itens.length === 1 ? "lugar" : "lugares"}`, itens };
    });
  }

  /** Cinco estrelas em pixel, pintadas até a nota (arredondada). */
  function estrelas(valor) {
    const cheias = Math.round(valor);
    const linha = el("span", { class: "estrelas-fixas", role: "img", "aria-label": `${cheias} de 5 estrelas` });
    for (let i = 1; i <= 5; i++) { const s = icone("estrela"); if (i > cheias) s.classList.add("vazia"); linha.append(s); }
    return linha;
  }

  function cartao(l, dist) {
    const nota = notas[l.id];
    const conf = confirma[l.id];
    const mun = porCodigo.get(l.m);
    const d = dist && dist.get(l.m);
    const onde = [l.e, d ? `${mun.n}, a ${Math.round(d.km)} km${d.manual ? " (indicado por colegas)" : ""}` : null].filter(Boolean).join(". ");
    // Sem coordenada própria (local aproximado), a rota vai pelo nome e endereço, não pela sede do município.
    const destino = l.ap ? encodeURIComponent(`${l.n}, ${l.e || ""}, ${mun.n}, PR`) : `${l.lat},${l.lon}`;
    const rota = `https://www.google.com/maps/dir/?api=1&destination=${destino}`;
    const selos = [
      l.t === "hotel" && (l.ok || (nota && nota.ok) || (conf && conf.ok) ? el("span", { class: "selo ok" }, "Cabe na diária") : el("span", { class: "selo atencao" }, "Valor a confirmar")),
      l.t === "posto" && el("span", { class: "selo" }, l.b ? `Prime, ${l.b}` : "Prime"),
      l.almoco && el("span", { class: "selo" }, "Almoço"),
      l.jantar && el("span", { class: "selo" }, "Jantar"),
      conf && el("span", { class: "selo ok" }, `Confirmado por ${conf.n} ${conf.n === 1 ? "colega" : "colegas"}`),
      l.src === "colega" && el("span", { class: "selo" }, "Indicado por colega"),
      l.ap && el("span", { class: "selo atencao" }, "Local aproximado no mapa"),
    ];
    return el("article", { class: "lugar" },
      el("div", { class: "lugar-topo" },
        el("div", { class: "picto", title: ROTULO[l.t] }, icone(l.t)),
        el("div", {},
          el("h3", {}, l.n),
          onde && el("p", {}, onde),
          l.h && el("p", {}, l.h),
          nota && el("p", { class: "nota-media" }, estrelas(nota.media), ` ${nota.media.toFixed(1).replace(".", ",")} de 5, por ${nota.n} ${nota.n === 1 ? "colega" : "colegas"}`),
          el("div", { class: "selos" }, ...selos))),
      el("div", { class: "acoes" },
        l.tel && el("a", { class: "principal", href: `tel:+55${l.tel}`, "aria-label": `Ligar para ${l.n}: ${fone(l.tel)}` }, `Ligar ${fone(l.tel)}`),
        l.wa && el("a", { href: `https://wa.me/55${l.wa}`, target: "_blank", rel: "noopener" }, "WhatsApp"),
        l.email && el("a", { href: `mailto:${l.email}` }, "E-mail"),
        el("a", { href: rota, target: "_blank", rel: "noopener" }, "Rota"),
        el("button", { type: "button", onclick: () => abre("confirmar", l) }, "Confirmar"),
        el("button", { type: "button", onclick: () => abre("avaliar", l) }, "Avaliar"),
        el("button", { type: "button", onclick: () => abre("corrigir", l) }, "Corrigir")),
      // Até 2 comentários já aparecem abertos; acima disso ficam recolhidos para a lista não esticar.
      nota && nota.comentarios.length > 0 && el("details", { open: nota.comentarios.length <= 2 ? "" : null },
        el("summary", {}, `${nota.comentarios.length} ${nota.comentarios.length === 1 ? "comentário de colega" : "comentários de colegas"}`),
        ...nota.comentarios.map((c) => el("blockquote", {}, c.nota ? estrelas(c.nota) : null, el("span", {}, c.texto || String(c))))));
  }

  function desenha(enquadra = true) {
    const e = estado();
    const blocos = secoes(e);
    visiveis = blocos.flatMap((b) => b.itens);
    const lista = $("#lista");
    lista.replaceChildren();

    const total = visiveis.length;
    $("#resumo").textContent = e.mun
      ? `${total} ${total === 1 ? "parada" : "paradas"} em ${porCodigo.get(e.mun).n} e na órbita de ${e.raio} km`
      : `${total} paradas mapeadas em ${blocos.length} municípios, em ordem alfabética`;

    if (!total) {
      lista.append(el("div", { class: "vazio" },
        el("img", { class: "px", src: "assets/mascote.svg", alt: "" }),
        el("h2", {}, "Nenhum sinal de vida por aqui"),
        el("p", {}, e.mun ? "Aumente a órbita em Mais filtros ou marque os três tipos. Conhece um lugar bom neste canto da galáxia?" : "Confira a grafia ou tire algum filtro."),
        el("button", { class: "botao cheio", type: "button", onclick: () => abre("lugar") }, "Indicar lugar")));
    }
    let resta = limite;
    for (const b of blocos) {
      if (resta <= 0) break;
      if (!b.itens.length && !e.mun) continue;
      lista.append(el("div", { class: "planeta" }, icone("planeta"), el("h2", {}, b.titulo), el("span", {}, b.sub)));
      for (const l of b.itens.slice(0, resta)) lista.append(cartao(l, b.dist));
      resta -= b.itens.length;
    }
    if (total > limite) {
      lista.append(el("button", { class: "botao mais", type: "button", onclick: () => { limite += PAGINA; desenha(false); } }, `Mostrar mais (${total - limite} restantes)`));
    }
    desenhaMapa(e, enquadra);
  }

  function marcador(tipo) { return el("span", { class: "marcador" }, icone(ROTULO[tipo] ? tipo : "planeta")); }

  function desenhaMapa(e, enquadra = true) {
    if (!mapa) return;
    camada.clearLayers();
    const leve = visiveis.length > MAX_ICONES;
    for (const l of visiveis) {
      const m = leve
        ? L.circleMarker([l.lat, l.lon], { radius: 5, weight: 1, color: "#fff", fillColor: "#17123a", fillOpacity: 0.95 })
        : L.marker([l.lat, l.lon], { title: l.n, icon: L.divIcon({ className: "", html: marcador(l.t), iconSize: [28, 28] }) });
      m.bindPopup(() => el("div", {},
        el("strong", {}, l.n),
        `${ROTULO[l.t]} em ${porCodigo.get(l.m).n}`,
        l.tel && el("div", {}, el("a", { href: `tel:+55${l.tel}` }, fone(l.tel))),
        el("div", {}, el("a", { href: `https://www.google.com/maps/dir/?api=1&destination=${l.lat},${l.lon}`, target: "_blank", rel: "noopener" }, "Abrir rota"))));
      m.addTo(camada);
    }
    if (!enquadra) return;
    if (e.mun && visiveis.length) mapa.fitBounds(L.latLngBounds(visiveis.map((l) => [l.lat, l.lon])).pad(0.15));
    else if (e.mun) mapa.setView([porCodigo.get(e.mun).lat, porCodigo.get(e.mun).lon], 11);
  }

  function iniciaMapa() {
    if (mapa || !window.L) return;
    mapa = L.map("mapa", { preferCanvas: true }).setView([-24.7, -51.6], 7);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }).addTo(mapa);
    camada = L.layerGroup().addTo(mapa);
    desenhaMapa(estado());
  }

  function mostra(painel) {
    const largo = matchMedia("(min-width: 900px)").matches;
    $("#painel-lista").hidden = !largo && painel !== "lista";
    $("#painel-mapa").hidden = !largo && painel !== "mapa";
    for (const b of document.querySelectorAll("[data-ver]")) b.setAttribute("aria-pressed", String(b.dataset.ver === painel));
    if (largo || painel === "mapa") { iniciaMapa(); if (mapa) mapa.invalidateSize(); }
  }

  // ---------- formulários ----------
  function abre(qual, lugar) {
    const dlg = $(`#dlg-${qual}`);
    const form = $("form", dlg);
    form.reset();
    const ret = $(".retorno", form);
    ret.hidden = true;
    $('[type="submit"]', form).disabled = false;
    if (lugar) {
      form.elements.id.value = lugar.id;
      $("[data-alvo]", form).textContent = `${lugar.n}, ${porCodigo.get(lugar.m).n}`;
      const soHotel = $("[data-so-hotel]", form);
      if (soHotel) soHotel.hidden = lugar.t !== "hotel";
    } else {
      form.elements.mun.value = $("#mun").value;
      alternaTipo(form);
    }
    if (form.elements.data) form.elements.data.max = new Date().toISOString().slice(0, 10);
    if (form.elements.autor) form.elements.autor.value = localStorage.getItem("guia-autor") || "";
    dlg.showModal();
  }
  function alternaTipo(form) {
    for (const f of form.querySelectorAll("[data-so]")) f.hidden = f.dataset.so !== form.elements.t.value;
  }

  const RECEBIDO = {
    lugar: "Transmissão recebida. Já está no guia, e outros colegas podem confirmar.",
    confirmacao: "Confirmação registrada. Valeu por ajudar os colegas.",
    avaliacao: "Transmissão recebida. Aparece no guia depois que um colega mantenedor conferir.",
    correcao: "Transmissão recebida. Um colega mantenedor vai conferir e corrigir.",
  };

  async function envia(ev) {
    ev.preventDefault();
    const form = ev.target;
    const ret = $(".retorno", form);
    const botao = $('[type="submit"]', form);
    const avisa = (texto, erro) => { ret.textContent = texto; ret.classList.toggle("erro", !!erro); ret.hidden = false; };
    const dados = Object.fromEntries(new FormData(form));
    dados.tipo = form.dataset.tipo;

    if (dados.tipo === "lugar") {
      dados.m = porNome.get(chave(dados.mun));
      if (!dados.m) return avisa("Escolha um município do Paraná da lista.", true);
      if (!dados.wa && !dados.email) return avisa("Informe o WhatsApp ou o e-mail do lugar.", true);
      if (dados.t === "hotel" && !dados.ok) return avisa("Só entram na lista hotéis cujo valor cabe na diária. Marque a caixa se for o caso.", true);
    }
    if (form.querySelector("[data-estrelas]") && !dados.nota) return avisa("Dê uma nota de 1 a 5 estrelas.", true);
    if (!API) return avisa("O envio ainda não está ligado nesta versão do site. Avise um colega mantenedor.", true);

    botao.disabled = true;
    avisa("Transmitindo...");
    try {
      // text/plain evita o preflight CORS, que o Apps Script não responde.
      const resp = await fetch(API, { method: "POST", headers: { "Content-Type": "text/plain;charset=utf-8" }, body: JSON.stringify(dados) });
      const json = await resp.json();
      if (!json.success) throw new Error(json.error || "falha no servidor");
      localStorage.setItem("guia-autor", dados.autor || "");
      avisa(RECEBIDO[dados.tipo]);
      if (dados.tipo === "lugar" || dados.tipo === "confirmacao") sincroniza().then(() => desenha(false)).catch(() => {});
      setTimeout(() => form.closest("dialog").close(), 2200);
    } catch (erro) {
      botao.disabled = false;
      avisa(`Não foi possível enviar (${erro.message}). Confira a internet e tente de novo.`, true);
    }
  }

  // ---------- carga ----------
  function indexa(l) { return { ...l, busca: chave(`${l.n} ${l.e || ""} ${porCodigo.get(l.m).n} ${l.b || ""}`) }; }

  /** Junta a base estática com o que veio da planilha: a planilha vence por id; status "removido" some. */
  function mescla(base, remoto) {
    const mapaLugares = new Map(base.map((l) => [l.id, l]));
    for (const r of remoto) {
      if (r.status === "removido") { mapaLugares.delete(r.id); continue; }
      const antigo = mapaLugares.get(r.id) || {};
      const sede = porCodigo.get(r.m || antigo.m);
      if (!sede) continue;
      const novo = { src: "colega", ...antigo, ...Object.fromEntries(Object.entries(r).filter(([, v]) => v !== "" && v != null)) };
      for (const c of ["tel", "wa"]) if (novo[c] != null) novo[c] = String(novo[c]); // a planilha devolve telefone como número
      // Coordenada digitada na planilha pode vir torta ("-25,43"): fora do PR cai na sede do município.
      const lat = Number(novo.lat), lon = Number(novo.lon);
      const valida = lat > -26.8 && lat < -22.4 && lon > -54.7 && lon < -48.0;
      mapaLugares.set(r.id, valida ? { ...novo, lat, lon } : { ...novo, lat: sede.lat, lon: sede.lon, ap: 1 });
    }
    return [...mapaLugares.values()];
  }

  /** Busca na planilha o que os colegas indicaram, confirmaram e avaliaram. */
  async function sincroniza() {
    const json = await fetch(API).then((r) => r.json());
    if (!json.success) throw new Error(json.error);
    notas = json.data.notas || {};
    confirma = json.data.confirma || {};
    vinculos = json.data.vinculos || [];
    lugares = mescla(baseFixa, json.data.lugares || []).map(indexa);
  }

  async function carrega() {
    const [mun, base] = await Promise.all(["data/municipios.json", "data/lugares.json"].map((u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u); return r.json(); })));
    municipios = mun;
    porCodigo = new Map(mun.map((m) => [m.c, m]));
    porNome = new Map(mun.map((m) => [chave(m.n), m.c]));
    $("#lista-mun").append(...mun.map((m) => el("option", { value: m.n })));
    baseFixa = base;
    lugares = base.map(indexa);
    desenha();
    if (!API) return;
    try {
      await sincroniza();
      desenha();
    } catch (erro) {
      $("#resumo").textContent += ". Indicações recentes dos colegas não carregaram; mostrando a base inicial.";
    }
  }

  function pertoDeMim() {
    const botao = $("#perto-de-mim");
    if (!navigator.geolocation) { botao.textContent = "Sem GPS"; return; }
    botao.textContent = "Localizando...";
    navigator.geolocation.getCurrentPosition((pos) => {
      const aqui = { lat: pos.coords.latitude, lon: pos.coords.longitude };
      const perto = municipios.reduce((a, b) => (km(aqui, a) < km(aqui, b) ? a : b));
      $("#mun").value = perto.n;
      botao.textContent = "Perto de mim";
      limite = PAGINA;
      desenha();
    }, () => { botao.textContent = "GPS negado"; }, { timeout: 10000 });
  }

  function demo() { // checagem mínima: abra o site com #teste
    console.assert(chave("São José dos Pinhais") === "SAO JOSE DOS PINHAIS", "chave");
    console.assert(Math.abs(km({ lat: -25.43, lon: -49.27 }, { lat: -25.09, lon: -50.16 }) - 97) < 5, "km Curitiba-Ponta Grossa");
    const m = mescla([{ id: "a", m: municipios[0].c, n: "A", lat: 1, lon: 1 }, { id: "b", m: municipios[0].c, n: "B", lat: 1, lon: 1 }], [{ id: "a", status: "removido" }, { id: "b", tel: "42" }, { id: "c", m: municipios[1].c, n: "C" }]);
    console.assert(m.length === 2 && m[0].tel === "42" && m[1].ap === 1, "mescla");
    console.info("demo ok");
  }

  // Seletor de nota: cinco botões de rádio nativos, desenhados como estrelas.
  for (const campo of document.querySelectorAll("[data-estrelas]")) {
    for (let i = 1; i <= 5; i++) {
      campo.append(el("label", { title: `${i} de 5` }, el("input", { type: "radio", name: "nota", value: String(i) }), icone("estrela"), el("span", { class: "so-leitor" }, `${i} de 5 estrelas`)));
    }
  }
  for (const id of ["mun", "q", "raio", "so-ok", "per"]) $(`#${id}`).addEventListener("input", () => { limite = PAGINA; desenha(); });
  for (const c of document.querySelectorAll('input[name="tipo"]')) c.addEventListener("change", () => { limite = PAGINA; desenha(); });
  for (const b of document.querySelectorAll("[data-ver]")) b.addEventListener("click", () => mostra(b.dataset.ver));
  for (const b of document.querySelectorAll("[data-fechar]")) b.addEventListener("click", () => b.closest("dialog").close());
  for (const f of document.querySelectorAll("dialog form")) f.addEventListener("submit", envia);
  $("#dlg-lugar form").elements.t.addEventListener("change", (ev) => alternaTipo(ev.target.form));
  $("#abrir-indicar").addEventListener("click", () => abre("lugar"));
  $("#perto-de-mim").addEventListener("click", pertoDeMim);
  matchMedia("(min-width: 900px)").addEventListener("change", () => mostra("lista"));

  carrega().then(() => { mostra("lista"); if (location.hash === "#teste") demo(); }).catch((erro) => {
    $("#lista").replaceChildren(el("div", { class: "vazio" }, el("h2", {}, "O guia não carregou"), el("p", {}, `Confira a internet e recarregue a página. (${erro.message})`)));
  });
})();
