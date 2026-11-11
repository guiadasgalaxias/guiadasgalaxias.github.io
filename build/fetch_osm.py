"""Baixa hotéis e restaurantes do PR do OpenStreetMap (Overpass) para build/raw/osm.json.

Uso: py -3 build/fetch_osm.py
Dados © colaboradores do OpenStreetMap, licença ODbL.
"""
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

OUT = pathlib.Path(__file__).parent / "raw" / "osm.json"
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
QUERY = """[out:json][timeout:170];
area["ISO3166-2"="BR-PR"]->.a;
(
  nwr["tourism"~"^(hotel|motel|guest_house|hostel)$"]["name"](area.a);
  nwr["amenity"="restaurant"]["name"](area.a);
);
out center tags;"""
MAX_TRIES = 12


def fetch(url: str) -> dict:
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(url, data=body, headers={"User-Agent": "guia-extensionista-build/0.1"})
    with urllib.request.urlopen(req, timeout=200) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    wait = 15
    for attempt in range(MAX_TRIES):
        url = MIRRORS[attempt % len(MIRRORS)]
        try:
            data = fetch(url)
            if data.get("elements"):
                OUT.parent.mkdir(parents=True, exist_ok=True)
                OUT.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                print(f"ok: {len(data['elements'])} elementos de {url}")
                return 0
            print(f"vazio em {url}: {data.get('remark')}")
        except Exception as exc:  # rede/servidor ocupado: tenta o próximo espelho
            print(f"falhou {url}: {exc}")
        time.sleep(wait)
        wait = min(wait * 2, 240)
    print("desisti: Overpass indisponível")
    return 1


if __name__ == "__main__":
    sys.exit(main())
