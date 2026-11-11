"""Grava o vídeo tutorial do guia: como indicar um lugar e como sugerir a exclusão.

Abre o site local num navegador com tela de celular, percorre os dois formulários com legendas
e salva tutorial/como-indicar-e-sugerir-exclusao.mp4. Nada é gravado na planilha: o envio é
respondido aqui mesmo, e o lugar de exemplo só existe dentro da gravação.

Uso: py -3 build/tutorial_video.py   (precisa de playwright e ffmpeg)
"""
from __future__ import annotations

import functools
import http.server
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time

from playwright.sync_api import Page, Route, sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SAIDA = ROOT / "tutorial" / "como-indicar-e-sugerir-exclusao.mp4"
PORTA = 8765
TELA = {"width": 480, "height": 854}
EXEMPLO = {
    "id": "cdemo", "status": "aprovado", "t": "rest", "n": "Restaurante da Dona Exemplo",
    "e": "Rua XV de Novembro, 100", "m": 4109401, "tel": "4233330000", "wa": "42999990000", "almoco": 1,
}
COMENTARIO = "Comida caseira, atende rápido e cabe na diária."

CAMADA = """
(() => {
  const c = document.createElement("div");
  c.id = "tuto"; c.popover = "manual";
  c.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;margin:0;padding:0;border:0;background:none;pointer-events:none;overflow:visible";
  c.innerHTML = `
    <div id="tuto-legenda" style="position:absolute;left:12px;right:12px;top:12px;padding:12px 14px;background:#ffd23f;color:#17123a;
      font:700 19px/1.25 'Atkinson Hyperlegible',system-ui,sans-serif;border:4px solid #17123a;box-shadow:0 6px 0 #0d0a24;display:none"></div>
    <div id="tuto-dedo" style="position:absolute;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;border:5px solid #ff6b9d;
      background:rgba(255,107,157,.3);display:none"></div>`;
  document.body.append(c);
  window.tuto = {
    cima() { c.hidePopover(); c.showPopover(); },
    legenda(t, embaixo) {
      const l = c.querySelector("#tuto-legenda");
      l.textContent = t; l.style.display = t ? "block" : "none";
      l.style.top = embaixo ? "auto" : "12px"; l.style.bottom = embaixo ? "84px" : "auto";
      this.cima();
    },
    dedo(x, y) { const d = c.querySelector("#tuto-dedo"); d.style.display = x == null ? "none" : "block"; d.style.left = x + "px"; d.style.top = y + "px"; },
  };
})();
"""


def legenda(page: Page, texto: str, espera: float = 2.6, embaixo: bool = False) -> None:
    page.evaluate("([t, e]) => window.tuto.legenda(t, e)", [texto, embaixo])
    page.wait_for_timeout(int(espera * 1000))


def toca(page: Page, seletor: str, espera: float = 0.7) -> None:
    alvo = page.locator(seletor).first
    alvo.scroll_into_view_if_needed()
    page.wait_for_timeout(250)
    caixa = alvo.bounding_box()
    page.evaluate("([x, y]) => window.tuto.dedo(x, y)", [caixa["x"] + caixa["width"] / 2, caixa["y"] + caixa["height"] / 2])
    page.wait_for_timeout(600)
    alvo.click()
    page.evaluate("() => { window.tuto.dedo(null); window.tuto.cima(); }")
    page.wait_for_timeout(int(espera * 1000))


def digita(page: Page, seletor: str, texto: str) -> None:
    campo = page.locator(seletor).first
    campo.scroll_into_view_if_needed()
    campo.click()
    campo.press_sequentially(texto, delay=35)
    page.wait_for_timeout(350)


def grava(pasta_video: str) -> tuple[pathlib.Path, float]:
    enviado = {"lugar": False}

    def api(route: Route) -> None:
        if route.request.method == "POST":  # nada chega à planilha
            dados = json.loads(route.request.post_data or "{}")
            assert dados.get("autor") == "Colega Exemplo", f"envio inesperado: {dados}"
            enviado["lugar"] = enviado["lugar"] or dados["tipo"] == "lugar"
            route.fulfill(json={"success": True, "data": {"id": EXEMPLO["id"]}, "error": None})
            return
        resposta = route.fetch()
        corpo = resposta.json()
        if enviado["lugar"] and corpo.get("success"):
            corpo["data"]["lugares"].append(EXEMPLO)
            corpo["data"]["notas"][EXEMPLO["id"]] = {"n": 1, "media": 5, "ok": False, "comentarios": [{"nota": 5, "texto": COMENTARIO}]}
        route.fulfill(json=corpo)

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(viewport=TELA, record_video_dir=pasta_video, record_video_size=TELA,
                                         locale="pt-BR", has_touch=True, is_mobile=True, device_scale_factor=1)
        contexto.route("https://script.google.com/**", api)
        contexto.route("https://script.googleusercontent.com/**", api)
        inicio = time.monotonic()
        page = contexto.new_page()
        page.goto(f"http://127.0.0.1:{PORTA}/index.html")
        page.wait_for_selector("#lista article, #lista .cartao, #lista > *")
        page.wait_for_timeout(1500)
        page.evaluate(CAMADA)
        corte = time.monotonic() - inicio  # o que veio antes é só carregamento

        # ---------- parte 1: indicar um lugar ----------
        legenda(page, "Parte 1: como indicar um lugar novo no guia", 3.2)
        legenda(page, "Toque em Indicar lugar, na barra de baixo", 1.6)
        toca(page, "#abrir-indicar", 1.2)
        legenda(page, "Escolha o tipo e preencha nome, endereço e município", 2.2, embaixo=True)
        page.locator('#dlg-lugar select[name="t"]').select_option("rest")
        page.wait_for_timeout(600)
        digita(page, '#dlg-lugar input[name="n"]', EXEMPLO["n"])
        digita(page, '#dlg-lugar input[name="e"]', EXEMPLO["e"])
        digita(page, '#dlg-lugar input[name="mun"]', "Guarapuava")
        legenda(page, "Opcional: localize pelo endereço ou toque no mapa para marcar o ponto", 1.8)
        toca(page, "#localizar-endereco", 0.5)
        page.wait_for_function("() => !document.querySelector('#localizar-endereco').disabled")
        page.locator("#mini-mapa").scroll_into_view_if_needed()
        page.wait_for_timeout(2600)
        legenda(page, "Telefone é obrigatório. Informe também WhatsApp ou e-mail do lugar", 1.6)
        digita(page, '#dlg-lugar input[name="tel"]', "(42) 3333-0000")
        digita(page, '#dlg-lugar input[name="wa"]', "(42) 99999-0000")
        legenda(page, "Marque o que o lugar atende, dê sua nota e comente", 1.6)
        toca(page, '#dlg-lugar input[name="almoco"]', 0.4)
        toca(page, "#dlg-lugar [data-estrelas] label:nth-of-type(5)", 0.6)
        digita(page, '#dlg-lugar textarea[name="comentario"]', COMENTARIO)
        legenda(page, "Seu nome fica só com os mantenedores. Depois, Enviar indicação", 1.6)
        digita(page, '#dlg-lugar input[name="autor"]', "Colega Exemplo")
        toca(page, '#dlg-lugar [type="submit"]', 0.3)
        legenda(page, "Pronto: o lugar entra no guia na hora", 2.6)
        page.wait_for_selector("#dlg-lugar", state="hidden")

        # ---------- parte 2: sugerir a exclusão ----------
        legenda(page, "Parte 2: como sugerir a exclusão de um lugar", 3.2)
        legenda(page, "Ache o lugar: digite o município e, se quiser, o nome", 1.4)
        digita(page, "#mun", "Guarapuava")
        page.locator("#mun").press("Enter")
        digita(page, "#q", "Dona Exemplo")
        page.wait_for_timeout(1200)
        legenda(page, "No cartão do lugar, toque em Confirmar", 1.6)
        toca(page, '#lista button:has-text("Confirmar")', 1.0)
        legenda(page, "Informe a data da visita, a nota e o motivo", 1.6, embaixo=True)
        page.locator('#dlg-confirmar input[name="data"]').fill("2026-11-10")
        page.wait_for_timeout(600)
        toca(page, "#dlg-confirmar [data-estrelas] label:nth-of-type(1)", 0.6)
        digita(page, '#dlg-confirmar textarea[name="comentario"]', "Fechou as portas, não atende mais.")
        legenda(page, 'Marque "Experiência ruim: recomendo remover do guia"', 1.4)
        toca(page, '#dlg-confirmar input[name="remover"]', 1.4)
        legenda(page, "Confira seu nome e toque em Confirmar parada", 1.4)
        toca(page, '#dlg-confirmar [type="submit"]', 0.3)
        legenda(page, "Registrado. Um colega mantenedor confere e tira o lugar da lista", 3.2)
        page.wait_for_selector("#dlg-confirmar", state="hidden")
        legenda(page, "Se o lugar existe e só um dado está errado, use Corrigir no cartão", 3.4)
        legenda(page, "Boa viagem, e não esqueça a toalha", 2.6)

        video = page.video
        contexto.close()
        navegador.close()
        return pathlib.Path(video.path()), corte


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    servidor = http.server.ThreadingHTTPServer(
        ("127.0.0.1", PORTA), functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT)))
    servidor.RequestHandlerClass.log_message = lambda *a: None
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as pasta:
            bruto, corte = grava(pasta)
            SAIDA.parent.mkdir(exist_ok=True)
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{corte:.2f}", "-i", str(bruto),
                 "-vf", "scale=720:-2:flags=lanczos,fps=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
                 "-movflags", "+faststart", "-an", str(SAIDA)],
                check=True)
    finally:
        servidor.shutdown()
    print(f"vídeo salvo em {SAIDA} ({SAIDA.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
