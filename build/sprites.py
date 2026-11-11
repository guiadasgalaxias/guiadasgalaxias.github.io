"""Pixel art do Guia do Extensionista das Galáxias, desenhada em texto e exportada como SVG.

Cada caractere é um pixel; "." é transparente e "x" usa a cor do texto (currentColor).
Uso: py -3 build/sprites.py  ->  assets/sprites.svg, assets/logo.svg, assets/mascote.svg
"""
from __future__ import annotations

import pathlib

ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"
CORES = {
    "x": "currentColor",
    "n": "#17123a",  # noite
    "g": "#3dbe6c",  # planeta
    "d": "#1f8a4c",  # sombra do planeta
    "y": "#ffd23f",  # anel / estrela
    "s": "#8cf07a",  # broto
    "w": "#f4f4f8",  # traje / estrela
    "c": "#a9a9c4",  # sombra do traje
    "v": "#4cc9f0",  # visor
    "l": "#c8f1ff",  # brilho do visor
    "h": "#e9b44c",  # chapéu de palha
    "H": "#b8862b",  # aba do chapéu
    "p": "#ff6b9d",  # fita do chapéu
}

# Planeta com anel e um broto no polo norte: o planeta do extensionista.
PLANETA = """
................
.w....s..s......
......ssss....w.
.......ss.......
.....gggggg.....
....gggggggg....
...ggggsggggg...
y..gggggggggg..y
.yyyyyyyyyyyyyy.
...dggggggggd...
...ddggggggdd...
....dddddddd....
.....dddddd.....
..w.............
.............w..
................
"""

# Astronauta de chapéu de palha: o extensionista em missão.
MASCOTE = """
................
......hhhh......
.....hhhhhh.....
.....pppppp.....
..HHHHHHHHHHHH..
....wwwwwwww....
...wwvvvvvvww...
...wvvlvvvvvw...
...wvvvvvvvvw...
...wwvvvvvvww...
....wwwwwwww....
..cwwwwyywwwwc..
..ww.wwwwww.ww..
.....wwwwww.....
.....ww..ww.....
....ccc..ccc....
"""

HOTEL = """
............
............
x...........
x...........
x.xx........
x.xx.xxxxxxx
xxxxxxxxxxxx
xxxxxxxxxxxx
x..........x
x..........x
............
............
"""

REST = """
............
x.x.x...xx..
x.x.x...xxx.
x.x.x...xxx.
x.x.x...xxx.
xxxxx...xxx.
.xxx....xx..
..x.....x...
..x.....x...
..x.....x...
..x.....x...
............
"""

POSTO = """
............
.xxxxxx.....
.x....x..x..
.x....x...x.
.xxxxxx...x.
.xxxxxx.xxx.
.xxxxxxxx.x.
.xxxxxx.x.x.
.xxxxxx.x.x.
.xxxxxx.xxx.
xxxxxxxx....
............
"""

ESTRELA = """
...x...
...x...
xxxxxxx
.xxxxx.
..xxx..
.xx.xx.
.x...x.
"""

SPRITES = {"planeta": PLANETA, "mascote": MASCOTE, "hotel": HOTEL, "rest": REST, "posto": POSTO, "estrela": ESTRELA}


def linhas(arte: str) -> list[str]:
    grade = arte.strip("\n").split("\n")
    assert len({len(l) for l in grade}) == 1, f"linhas de tamanhos diferentes: {[len(l) for l in grade]}"
    return grade


def pixels(arte: str, fundo: str | None = None) -> tuple[str, int, int]:
    """Devolve (rects SVG, largura, altura). Pixels vizinhos na mesma linha viram um rect só."""
    grade = linhas(arte)
    saida = []
    for y, linha in enumerate(grade):
        x = 0
        while x < len(linha):
            ch = linha[x]
            fim = x
            while fim < len(linha) and linha[fim] == ch:
                fim += 1
            cor = CORES.get(ch, fundo) if ch != "." else fundo
            if cor:
                saida.append(f'<rect x="{x}" y="{y}" width="{fim - x}" height="1" fill="{cor}"/>')
            x = fim
    return "".join(saida), len(grade[0]), len(grade)


def arquivo(arte: str, rotulo: str, fundo: str | None = None) -> str:
    rects, w, h = pixels(arte, fundo)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" shape-rendering="crispEdges" '
            f'role="img" aria-label="{rotulo}">{rects}</svg>\n')


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    simbolos = []
    for nome, arte in SPRITES.items():
        rects, w, h = pixels(arte)
        simbolos.append(f'<symbol id="i-{nome}" viewBox="0 0 {w} {h}" shape-rendering="crispEdges">{rects}</symbol>')
    (ASSETS / "sprites.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">' + "".join(simbolos) + "</svg>\n", encoding="utf-8")
    (ASSETS / "logo.svg").write_text(arquivo(PLANETA, "Guia do Extensionista das Galáxias", CORES["n"]), encoding="utf-8")
    (ASSETS / "mascote.svg").write_text(arquivo(MASCOTE, "Astronauta de chapéu de palha"), encoding="utf-8")
    print("sprites:", ", ".join(SPRITES))


if __name__ == "__main__":
    main()
