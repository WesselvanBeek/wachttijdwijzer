#!/usr/bin/env python3
"""Haalt GGZ-wachttijden op van de websites van aanbieders en bouwt index.html.

Gebruik:
    python scraper/ophalen.py                 # ophalen en app bouwen
    python scraper/ophalen.py --alleen-bouwen # alleen app bouwen uit bestaande gegevens

De leesregels per aanbieder staan in data/aanbieders.json. Het resultaat komt in
data/wachttijden.json en wordt ingebouwd in index.html.
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
AANBIEDERS = ROOT / "data" / "aanbieders.json"
WACHTTIJDEN = ROOT / "data" / "wachttijden.json"
TEMPLATE = ROOT / "app" / "template.html"
INDEX = ROOT / "index.html"

TZ = ZoneInfo("Europe/Amsterdam")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Wachttijdwijzer-GGZ; eenmaal per dag)"}

GETALWOORDEN = {
    "een": 1, "één": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6,
    "zeven": 7, "acht": 8, "negen": 9, "tien": 10, "elf": 11, "twaalf": 12,
}
EENHEID = r"(weken|week|wk|maanden|maand)\b"
DUUR = re.compile(
    r"(\d+)\s*(?:-|–|tot|à)\s*(\d+)\s*" + EENHEID + r"|(\d+)\s*" + EENHEID,
    re.IGNORECASE,
)
KAAL = re.compile(r"^(\d+)\*?$", re.MULTILINE)
STOP = re.compile(r"aanmeldpauze|aanmeldstop|aannamestop|\bgesloten\b", re.IGNORECASE)
GETALWOORD = re.compile(
    r"\b(" + "|".join(GETALWOORDEN) + r")\s+(?=" + EENHEID + ")", re.IGNORECASE
)


class Fout(Exception):
    """Een leesregel kon de pagina niet (meer) lezen."""


# ---------- pagina's ophalen ----------

_cache = {}


def pagina(url):
    """Geeft de zichtbare tekst van een pagina als lijst van regels, of None."""
    if url not in _cache:
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for tag in soup(["script", "style", "noscript", "svg"]):
                tag.decompose()
            regels = [l.strip() for l in soup.get_text("\n").splitlines()]
            _cache[url] = [l.replace(" ", " ") for l in regels if l]
        except requests.RequestException as e:
            print(f"  ! {url}: {e}", file=sys.stderr)
            _cache[url] = None
    return _cache[url]


# ---------- leesregels ----------

def naar_weken(n, eenheid):
    return round(n * 4.33) if eenheid.lower().startswith("maand") else n


def venster(regels, ankers, n):
    """Zoekt de ankers na elkaar op; geeft het ankerregel plus n regels erna."""
    pos = -1
    for anker in ankers:
        bevat = anker.startswith("~")
        tekst = (anker[1:] if bevat else anker).lower()
        for i in range(pos + 1, len(regels)):
            regel = regels[i].lower()
            if (tekst in regel) if bevat else regel.startswith(tekst):
                pos = i
                break
        else:
            raise Fout(f"tekst '{anker.lstrip('~')}' niet gevonden")
    return regels[pos:pos + n + 1]


def duren(tekst, kaal=False):
    """Alle wachttijden in de tekst, als (positie, [min, max]) in weken."""
    tekst = GETALWOORD.sub(lambda m: f"{GETALWOORDEN[m.group(1).lower()]} ", tekst)
    gevonden = []
    for m in DUUR.finditer(tekst):
        if m.group(1):
            w = [naar_weken(int(m.group(1)), m.group(3)), naar_weken(int(m.group(2)), m.group(3))]
        else:
            w = [naar_weken(int(m.group(4)), m.group(5))] * 2
        gevonden.append((m.start(), w))
    if kaal:
        gevonden += [(m.start(), [int(m.group(1))] * 2) for m in KAAL.finditer(tekst)]
    return sorted(gevonden, key=lambda x: x[0]), tekst


def lees_duur(regel, regels):
    """Geeft ("ok", [min, max]) of ("stop", None), of gooit Fout."""
    if regel.get("type") == "regex_alle":
        waarden = [int(m[regel["groep"] - 1]) for m in re.findall(regel["regex"], "\n" + "\n".join(regels))]
        if not waarden:
            raise Fout("tabel met wachttijden niet gevonden")
        return "ok", [min(waarden), max(waarden)]

    stuk = venster(regels, regel["ankers"], regel.get("regels", 1))
    tekst = "\n".join(stuk)
    if "vast" in regel:
        if regel["zoek"].lower() in tekst.lower():
            return "ok", regel["vast"]
        raise Fout(f"tekst '{regel['zoek']}' niet meer gevonden")

    gevonden, tekst = duren(tekst, regel.get("kaal", False))
    stop = STOP.search(tekst)
    if stop and (not gevonden or stop.start() < gevonden[0][0]):
        return "stop", None
    nr = regel.get("nr", 1)
    if len(gevonden) < nr:
        raise Fout(f"geen wachttijd gevonden bij '{regel['ankers'][-1].lstrip('~')}'")
    w = list(gevonden[nr - 1][1])
    if regel.get("vanaf_nul"):
        w[0] = 0
    return "ok", w


def lees_datum(regel, regels):
    tekst = "\n".join(venster(regels, regel["ankers"], regel.get("regels", 0)) if "ankers" in regel else regels)
    m = re.search(regel["regex"], tekst, re.IGNORECASE)
    if not m:
        raise Fout("datum niet gevonden")
    return m.group(1)


# ---------- verwerken ----------

def beschrijf(w):
    if w.get("stop"):
        return "aanmeldstop"
    def r(x):
        return "?" if not x else (f"{x[0]}" if x[0] == x[1] else f"{x[0]}-{x[1]}")
    return f"intake {r(w.get('aanm'))} wk, behandeling {r(w.get('beh'))} wk"


def verwerk(rij, oud, nu):
    nieuw = {k: oud.get(k) for k in ("aanm", "beh", "videoAanm", "stop", "bijgewerkt", "gecontroleerd", "gewijzigd", "vorige")}
    fouten = []
    regelset = rij.get("regels", {})

    for veld in ("aanm", "beh", "videoAanm"):
        regel = regelset.get(veld)
        if not regel or (veld != "aanm" and nieuw.get("stop")):
            continue
        regels = pagina(regel.get("url", rij["bron"]))
        if regels is None:
            fouten.append("pagina niet bereikbaar")
            break
        try:
            soort, w = lees_duur(regel, regels)
        except Fout as e:
            fouten.append(str(e))
            continue
        if veld == "aanm":
            nieuw["stop"] = soort == "stop"
            nieuw["aanm"] = w
            if nieuw["stop"]:
                nieuw["beh"] = None
                nieuw["videoAanm"] = None
        else:
            nieuw[veld] = w

    if "bijgewerkt" in regelset and not fouten:
        regel = regelset["bijgewerkt"]
        regels = pagina(regel.get("url", rij["bron"]))
        try:
            nieuw["bijgewerkt"] = lees_datum(regel, regels or [])
        except Fout:
            pass  # een ontbrekende datum is geen reden voor controle

    if not fouten:
        nieuw["gecontroleerd"] = nu
    velden = ("aanm", "beh", "stop")
    if oud and any(oud.get(k) != nieuw.get(k) for k in velden):
        nieuw["gewijzigd"] = nu
        nieuw["vorige"] = "Was: " + beschrijf(oud)
    nieuw["status"] = "controle" if fouten else "ok"
    nieuw["melding"] = "; ".join(dict.fromkeys(fouten)) or None
    return nieuw


def bouw(aanbieders, wachttijden):
    rijen = []
    for rij in aanbieders:
        samen = {k: v for k, v in rij.items() if k != "regels"}
        samen.update(wachttijden["rijen"].get(rij["id"], {}))
        rijen.append(samen)
    repo = os.environ.get("GITHUB_REPOSITORY") or wachttijden.get("repo")
    gegevens = {
        "laatsteControle": wachttijden.get("laatsteControle"),
        "samenvatting": wachttijden.get("samenvatting"),
        "vernieuwUrl": f"https://github.com/{repo}/actions/workflows/ophalen.yml" if repo else None,
        "aanbieders": rijen,
    }
    js = json.dumps(gegevens, ensure_ascii=False).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__GEGEVENS__*/null", js)
    INDEX.write_text(html, encoding="utf-8")
    print(f"index.html gebouwd met {len(rijen)} regels.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--alleen-bouwen", action="store_true", help="niets ophalen, alleen index.html bouwen")
    args = p.parse_args()

    aanbieders = json.loads(AANBIEDERS.read_text(encoding="utf-8"))
    ids = [r["id"] for r in aanbieders]
    if len(ids) != len(set(ids)):
        sys.exit("Fout: dubbele id in data/aanbieders.json")
    wachttijden = json.loads(WACHTTIJDEN.read_text(encoding="utf-8")) if WACHTTIJDEN.exists() else {"rijen": {}}

    if not args.alleen_bouwen:
        nu = dt.datetime.now(TZ).replace(microsecond=0).isoformat()
        rijen, gewijzigd, controle = {}, 0, []
        for rij in aanbieders:
            oud = wachttijden["rijen"].get(rij["id"], {})
            nieuw = verwerk(rij, oud, nu)
            rijen[rij["id"]] = nieuw
            if nieuw.get("gewijzigd") == nu:
                gewijzigd += 1
                print(f"  ~ {rij['org']} ({rij['afd'] or rij['plaats']}): {nieuw['vorige']} -> {beschrijf(nieuw)}")
            if nieuw["status"] == "controle":
                controle.append(rij["org"])
                print(f"  ! {rij['org']} ({rij['afd'] or rij['plaats']}): {nieuw['melding']}")
        delen = [f"{len(aanbieders) - len(controle)} van {len(aanbieders)} regels gelezen", f"{gewijzigd} gewijzigd"]
        if controle:
            delen.append(f"controle nodig bij {', '.join(dict.fromkeys(controle))}")
        wachttijden = {
            "laatsteControle": nu,
            "samenvatting": ", ".join(delen) + ".",
            "repo": os.environ.get("GITHUB_REPOSITORY") or wachttijden.get("repo"),
            "rijen": rijen,
        }
        WACHTTIJDEN.write_text(json.dumps(wachttijden, ensure_ascii=False, indent=2), encoding="utf-8")
        print(wachttijden["samenvatting"])

    bouw(aanbieders, wachttijden)


if __name__ == "__main__":
    main()
