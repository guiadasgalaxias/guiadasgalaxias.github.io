"""Geocodifica os hotéis que vieram do Cadastur sem coordenada (hoje na sede do município).

Usa o Nominatim (OpenStreetMap), 1 consulta por segundo, e guarda o resultado em
build/geocode_cache.json para não repetir consultas. Depois rode build/build_data.py.

Uso: py -3 build/geocode.py
Dados © colaboradores do OpenStreetMap, licença ODbL.
"""
from __future__ import annotations

import json
import math
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / "build" / "geocode_cache.json"
URL = "https://nominatim.openstreetmap.org/search"
PAUSA = 1.1  # política do Nominatim: no máximo 1 consulta por segundo
MAX_KM_DA_SEDE = 30  # resultado mais longe que isso é quase sempre a rua homônima de outra cidade


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def rua(endereco: str, cidade: str) -> str:
    """'Rua X 261 Curitiba Centro' -> 'Rua X 261' (o Cadastur cola a cidade e o bairro no fim)."""
    achado = list(re.finditer(re.escape(cidade), endereco, flags=re.I))
    return (endereco[: achado[-1].start()] if achado else endereco).strip(" ,-")


def consulta(params: dict[str, str]) -> tuple[float, float] | None:
    query = urllib.parse.urlencode({**params, "format": "jsonv2", "limit": "1", "countrycodes": "br"})
    req = urllib.request.Request(f"{URL}?{query}", headers={"User-Agent": "guia-extensionista-build/0.1"})
    time.sleep(PAUSA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        dados = json.loads(resp.read().decode("utf-8"))
    return (float(dados[0]["lat"]), float(dados[0]["lon"])) if dados else None


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    municipios = {m["c"]: m for m in json.loads((ROOT / "data" / "municipios.json").read_text(encoding="utf-8"))}
    lugares = json.loads((ROOT / "data" / "lugares.json").read_text(encoding="utf-8"))
    cache: dict[str, list[float] | None] = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    assert rua("Rua X 261 Curitiba Centro", "Curitiba") == "Rua X 261"

    pendentes = [l for l in lugares if l.get("src") == "cadastur" and l["id"] not in cache]
    print(f"{len(pendentes)} hotéis para geocodificar ({len(cache)} já no cache)")
    for i, l in enumerate(pendentes, 1):
        sede = municipios[l["m"]]
        via = rua(l.get("e", ""), sede["n"])
        tentativas = [
            {"street": via, "city": sede["n"], "state": "Paraná", "country": "Brasil"} if via else None,
            {"q": f"{l['n']}, {sede['n']}, Paraná, Brasil"},
        ]
        achado = None
        try:
            for params in filter(None, tentativas):
                ponto = consulta(params)
                if ponto and km(ponto[0], ponto[1], sede["lat"], sede["lon"]) <= MAX_KM_DA_SEDE:
                    achado = [round(ponto[0], 5), round(ponto[1], 5)]
                    break
            cache[l["id"]] = achado
        except Exception as exc:  # rede ou limite do servidor: não grava, a próxima execução tenta de novo
            print(f"  falhou {l['id']}: {exc}")
            time.sleep(10)
        if i % 25 == 0 or i == len(pendentes):
            CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=0), encoding="utf-8")
            print(f"{i}/{len(pendentes)}: {sum(1 for v in cache.values() if v)} localizados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
