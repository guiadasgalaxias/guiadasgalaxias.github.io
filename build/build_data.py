"""Gera data/municipios.json e data/lugares.json (base inicial pública do site).

Fontes:
  - "Postos Prime com Link.xlsx" (NÃO vai para o repositório: tem CNPJ, IE e nome de contato)
  - build/raw/municipios.csv (kelvins/municipios-brasileiros: código IBGE + sede)
  - build/raw/osm.json (build/fetch_osm.py; © colaboradores do OpenStreetMap, ODbL)
  - build/raw/cadastur/hospedagem.xlsx (dados.turismo.gov.br, "Meios de Hospedagem"; NÃO vai
    para o repositório: tem CPF e nome do responsável)

Só saem campos públicos do estabelecimento: nome, endereço, telefone, horário, coordenada.
Uso: py -3 build/build_data.py
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import pathlib
import re
import sys
import unicodedata

import openpyxl

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "build" / "raw"
XLSX = ROOT / "Postos Prime com Link.xlsx"
OUT = ROOT / "data"
UF_PR = "41"
PR_BBOX = (-26.8, -22.4, -54.7, -48.0)  # lat_min, lat_max, lon_min, lon_max
MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "em", "a", "o"}
OSM_TIPO = {"hotel": "hotel", "guest_house": "hotel", "hostel": "hotel"}  # motel fica de fora de propósito
GENERICAS = frozenset("HOTEL HOTEIS POUSADA LTDA ME EIRELI E DE DA DO DAS DOS S A EPP".split())
FORA_DA_DIARIA = {"Resort", "Alojamento de Floresta"}


def chave(texto: str) -> str:
    """Normaliza nome de município: sem acento, maiúsculo, só letras e espaço."""
    sem = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z ]", " ", sem.upper())).strip()


def titulo(texto: str | None) -> str:
    """'AUTO POSTO DO ZE LTDA' -> 'Auto Posto do Ze Ltda'."""
    # MEI costuma registrar "NOME DA PESSOA 12345678901": o CPF/CNPJ grudado no nome não pode sair.
    sem_doc = re.sub(r"\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}|\d{3}\.?\d{3}\.?\d{3}-?\d{2}", " ", str(texto or ""))
    palavras = re.sub(r"\s+", " ", sem_doc).strip().lower().split(" ")
    return " ".join(p if i and p in MINUSCULAS else p[:1].upper() + p[1:] for i, p in enumerate(palavras))


def digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def no_parana(lat: float, lon: float) -> bool:
    return PR_BBOX[0] <= lat <= PR_BBOX[1] and PR_BBOX[2] <= lon <= PR_BBOX[3]


def km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 12742 * math.asin(math.sqrt(a))


def carrega_municipios() -> list[dict]:
    with open(RAW / "municipios.csv", encoding="utf-8") as f:
        linhas = [r for r in csv.DictReader(f) if r["codigo_uf"] == UF_PR]
    return sorted(
        ({"c": int(r["codigo_ibge"]), "n": r["nome"], "lat": float(r["latitude"]), "lon": float(r["longitude"])} for r in linhas),
        key=lambda m: chave(m["n"]),
    )


def postos(por_nome: dict[str, int], sedes: dict[int, tuple[float, float]]) -> tuple[list[dict], list[str]]:
    wb = openpyxl.load_workbook(XLSX, read_only=True)
    linhas = wb["postos"].iter_rows(values_only=True)
    col = {nome: i for i, nome in enumerate(next(linhas))}
    saida, problemas = [], []
    for r in linhas:
        if not r or not r[col["Terminal"]]:
            continue
        cidade = str(r[col["Cidade"]] or "")
        codigo = por_nome.get(chave(cidade))
        coord = re.search(r"q=(-?\d+\.\d+),(-?\d+\.\d+)", str(r[col["link"]] or ""))
        if not codigo:
            problemas.append(f"posto {r[col['Terminal']]}: município '{cidade}' não reconhecido, descartado")
            continue
        lat, lon = (float(coord.group(1)), float(coord.group(2))) if coord else (0.0, 0.0)
        aproximado = not no_parana(lat, lon)
        if aproximado:  # planilha traz coordenada errada (ex.: Flórida/EUA): cai na sede do município
            lat, lon = sedes[codigo]
            problemas.append(f"posto {r[col['Terminal']]} ({cidade}): coordenada inválida, usei a sede do município")
        endereco = titulo(r[col["Endereç_1"]])
        if r[col["Complement"]]:
            endereco += f" ({titulo(r[col['Complement']])})"
        saida.append({
            "id": f"p{r[col['Terminal']]}",
            "t": "posto",
            "n": titulo(r[col["Nome Fanta"]] or r[col["Razão Soc"]]),  # 5 postos vêm sem nome fantasia
            "m": codigo,
            "e": endereco,
            "tel": digitos(r[col["Telefone"]]),
            "h": re.sub(r"\s*\n\s*", "; ", str(r[col["Horario Fu"]] or "").strip()),
            "b": titulo(r[col["Bandeira"]]),
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "src": "prime",
            **({"ap": 1} if aproximado else {}),
        })
    return saida, problemas


def osm(municipios: list[dict], por_nome: dict[str, int]) -> list[dict]:
    arquivo = RAW / "osm.json"
    if not arquivo.exists():
        print("aviso: build/raw/osm.json não existe; base sai sem hotéis e restaurantes do OSM")
        return []
    saida = []
    for el in json.loads(arquivo.read_text(encoding="utf-8"))["elements"]:
        tags = el.get("tags", {})
        centro = el if "lat" in el else el.get("center")
        tipo = OSM_TIPO.get(tags.get("tourism", ""), "rest" if tags.get("amenity") == "restaurant" else None)
        if not centro or not tipo or not tags.get("name") or not no_parana(centro["lat"], centro["lon"]):
            continue
        # ponytail: sem addr:city, usa a sede mais próxima; erra perto de divisas.
        # Trocar por ponto-em-polígono com a malha do IBGE se isso incomodar.
        codigo = por_nome.get(chave(tags.get("addr:city", ""))) or min(
            municipios, key=lambda m: km(centro["lat"], centro["lon"], m["lat"], m["lon"])
        )["c"]
        rua = " ".join(x for x in (tags.get("addr:street"), tags.get("addr:housenumber")) if x)
        item = {
            "id": f"o{el['type'][0]}{el['id']}",
            "t": tipo,
            "n": tags["name"].strip(),
            "m": codigo,
            "e": ", ".join(x for x in (rua, tags.get("addr:suburb")) if x),
            "tel": digitos((tags.get("phone") or tags.get("contact:phone") or "").split(";")[0]).removeprefix("55"),
            "wa": digitos(tags.get("contact:whatsapp")).removeprefix("55"),
            "email": tags.get("email") or tags.get("contact:email") or "",
            "h": tags.get("opening_hours", ""),
            "lat": round(centro["lat"], 5),
            "lon": round(centro["lon"], 5),
            "src": "osm",
        }
        saida.append({k: v for k, v in item.items() if v != ""})
    return saida


def miolo(nome: str) -> frozenset[str]:
    """Palavras que identificam o hotel, para casar Cadastur com OSM: 'HOTEL DO LAGO LTDA' -> {LAGO}."""
    return frozenset(chave(nome).split()) - GENERICAS


def cadastur(por_nome: dict[str, int], sedes: dict[int, tuple[float, float]], existentes: list[dict]) -> list[dict]:
    """Meios de hospedagem do PR no Cadastur (dados abertos do Ministério do Turismo).

    Traz o contato comercial (telefone e e-mail), que é o que falta no OSM. Não traz preço nem
    coordenada: se o hotel já existe no OSM do mesmo município, só completa o contato dele;
    senão entra na sede do município, marcado como local aproximado.
    Nunca saem CPF, nome do responsável, CNPJ nem e-mail do administrador.
    """
    arquivo = RAW / "cadastur" / "hospedagem.xlsx"
    if not arquivo.exists():
        print("aviso: build/raw/cadastur/hospedagem.xlsx não existe; base sai sem o Cadastur")
        return []
    linhas = openpyxl.load_workbook(arquivo, read_only=True).worksheets[0].iter_rows(values_only=True)
    col = {nome: i for i, nome in enumerate(next(linhas))}
    do_osm = {(l["m"], miolo(l["n"])): l for l in existentes if l["t"] == "hotel" and miolo(l["n"])}
    cache = ROOT / "build" / "geocode_cache.json"
    geocodificados = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    novos, completados, vistos = [], 0, set()
    for r in linhas:
        if r[col["UF"]] != "PR" or r[col["Situação da Atividade"]] != "Operação" or r[col["Tipo de Hospedagem"]] in FORA_DA_DIARIA:
            continue
        codigo = por_nome.get(chave(str(r[col["Município"]] or "")))
        nome = titulo(r[col["Nome Fantasia"]] or r[col["Nome da Pessoa Jurídica"]])
        if not codigo or not nome:
            continue
        tel = digitos(r[col["Telefone Comercial"]])
        contato = {
            "e": re.sub(r"\s*CEP:.*$", "", str(r[col["Endereço Completo Comercial"]] or "")).strip(),
            "tel": tel if len(tel) in (10, 11) else "",
            "wa": tel if len(tel) == 11 else "",  # celular: quase sempre atende no WhatsApp
            "email": str(r[col["E-mail Comercial"]] or "").strip().lower(),
        }
        contato = {k: v for k, v in contato.items() if v}
        par = do_osm.get((codigo, miolo(nome)))
        if par:
            for k, v in contato.items():
                par.setdefault(k, v)
            completados += 1
            continue
        ident = "h" + hashlib.sha1(str(r[col["Número de Inscrição do CNPJ"]]).encode()).hexdigest()[:10]
        if ident in vistos:
            continue
        vistos.add(ident)
        ponto = geocodificados.get(ident)  # build/geocode.py; sem resultado, fica na sede como local aproximado
        lat, lon = ponto or sedes[codigo]
        novos.append({"id": ident, "t": "hotel", "n": nome, "m": codigo, **contato, "lat": lat, "lon": lon, "src": "cadastur",
                      **({} if ponto else {"ap": 1})})
    print(f"cadastur: {len(novos)} hotéis novos, {completados} do OSM ganharam contato")
    return novos


def manuais(sedes: dict[int, tuple[float, float]]) -> list[dict]:
    """Lugares indicados por colegas fora do formulário (build/manuais.json). Sem lat/lon, ficam na sede."""
    arquivo = ROOT / "build" / "manuais.json"
    if not arquivo.exists():
        return []
    saida = []
    for item in json.loads(arquivo.read_text(encoding="utf-8")):
        assert item["m"] in sedes and item["t"] in ("hotel", "rest", "posto"), f"manual inválido: {item}"
        sem_ponto = "lat" not in item
        lat, lon = (item["lat"], item["lon"]) if not sem_ponto else sedes[item["m"]]
        saida.append({**item, "lat": lat, "lon": lon, "src": "colega", **({"ap": 1} if sem_ponto else {})})
    return saida


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    municipios = carrega_municipios()
    assert len(municipios) == 399, f"esperava 399 municípios do PR, vieram {len(municipios)}"
    por_nome = {chave(m["n"]): m["c"] for m in municipios}
    assert titulo("ELOISA WINTER 32263082972") == "Eloisa Winter" and titulo("POSTO 277 LTDA 41.401.022/0001-40") == "Posto 277 Ltda"
    assert miolo("HOTEL DO LAGO LTDA") == miolo("Lago Hotel") == {"LAGO"}
    assert chave("São José dos Pinhais") == "SAO JOSE DOS PINHAIS" and chave("Pato-Branco d'Oeste") == "PATO BRANCO D OESTE"

    sedes = {m["c"]: (m["lat"], m["lon"]) for m in municipios}
    lista_postos, problemas = postos(por_nome, sedes)
    do_osm = osm(municipios, por_nome)
    lugares = lista_postos + do_osm + cadastur(por_nome, sedes, do_osm) + manuais(sedes)
    lugares = [l for l in lugares if l["n"].strip()]  # sem nome não dá para indicar
    lugares = [l for l in lugares if not re.search(r"\bmot[eé]l\b", l["n"], re.I)]  # motel não é parada de viagem a serviço
    assert len({l["id"] for l in lugares}) == len(lugares), "ids duplicados"

    OUT.mkdir(exist_ok=True)
    for nome, dados in (("municipios.json", municipios), ("lugares.json", lugares)):
        (OUT / nome).write_text(json.dumps(dados, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    por_tipo: dict[str, int] = {}
    for l in lugares:
        por_tipo[l["t"]] = por_tipo.get(l["t"], 0) + 1
    print("lugares por tipo:", por_tipo)
    print(f"{len(problemas)} avisos da planilha")
    for p in problemas:
        print("  -", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
