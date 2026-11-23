"""Denní aktualizace dat pro nástroje „Historické analogie“ a „Laboratoř hypotéz“.

Spouští ho GitHub Actions každý pracovní den po zavření burzy v New Yorku
(.github/workflows/denni-aktualizace.yml), ale jde spustit i ručně:
    python3 aktualizuj.py

Co dělá:
  1. stáhne poslední zhruba dva měsíce zavíracích hodnot S&P 500, Nasdaq Composite
     a VIX z Yahoo Finance; když Yahoo nefunguje, použije FRED (SP500, NASDAQCOM,
     VIXCLS) bez API klíče,
  2. doplní nové dny do data/*.csv a přepíše posledních 10 dní (opravy zdroje),
  3. zkontroluje, že denní změny nejsou nesmyslné (jinak skončí chybou a GitHub
     pošle e-mail),
  4. vytvoří data.json, který si stránky stahují při otevření.

Maržový dluh/M2 (data/margin_m2.csv) se aktualizuje ručně: jednou měsíčně stačí
připsat řádek ve tvaru  2026-10,0.0645  (rok-měsíc, Gross Ratio z FINRA).

Potřebuje jen standardní Python 3.9+ (žádné další knihovny).
"""
import csv
import datetime as dt
import io
import json
import sys
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

SLOZKA = Path(__file__).resolve().parent
DATA = SLOZKA / "data"
NY = ZoneInfo("America/New_York")
UA = {"User-Agent": "Mozilla/5.0 (pkohout.com data update)"}

RADY = {
    #  klíč   soubor          Yahoo     FRED        max. denní změna
    "sp":  ("sp500.csv",  "^GSPC", "SP500",     0.25),
    "nq":  ("nasdaq.csv", "^IXIC", "NASDAQCOM", 0.25),
    "vix": ("vix.csv",    "^VIX",  "VIXCLS",    3.00),
}
PREPSAT_DNI = 10  # kolik posledních dní se smí přepsat novějšími hodnotami ze zdroje


def stahni(url, pokusy=3):
    for i in range(pokusy):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8")
        except Exception as e:  # síťové chyby, 429 apod.
            posledni = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url}: {posledni}")


def ny_hotove_dny():
    """Poslední den, jehož zavírací hodnota už je konečná (po 16:20 v New Yorku)."""
    ted = dt.datetime.now(NY)
    return ted.date() if ted.time() >= dt.time(16, 20) else ted.date() - dt.timedelta(days=1)


def z_yahoo(symbol):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.request.quote(symbol) + "?range=3mo&interval=1d")
    j = json.loads(stahni(url))["chart"]["result"][0]
    tz = ZoneInfo(j["meta"].get("exchangeTimezoneName", "America/New_York"))
    zavreno = ny_hotove_dny()
    out = {}
    for ts, c in zip(j.get("timestamp", []), j["indicators"]["quote"][0]["close"]):
        if c is None:
            continue
        den = dt.datetime.fromtimestamp(ts, tz).date()
        if den <= zavreno:
            out[den.isoformat()] = round(float(c), 2)
    return out


def z_fred(serie):
    od = (dt.date.today() - dt.timedelta(days=90)).isoformat()
    text = stahni(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}&cosd={od}")
    out = {}
    for radek in csv.DictReader(io.StringIO(text)):
        hodnoty = list(radek.values())
        try:
            out[hodnoty[0]] = round(float(hodnoty[1]), 2)
        except (ValueError, IndexError):
            pass  # "." = chybějící den
    return out


def nacti_csv(cesta):
    with open(cesta, newline="", encoding="utf-8") as f:
        return {r["date"]: float(r["close"]) for r in csv.DictReader(f)}


def uloz_csv(cesta, rada):
    with open(cesta, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "close"])
        for d in sorted(rada):
            w.writerow([d, f"{rada[d]:.2f}"])


def aktualizuj_radu(klic):
    soubor, yahoo, fred, max_zmena = RADY[klic]
    cesta = DATA / soubor
    rada = nacti_csv(cesta)
    nove, zdroj = {}, ""
    for nazev, fce, arg in (("Yahoo", z_yahoo, yahoo), ("FRED", z_fred, fred)):
        try:
            nove = fce(arg)
            if nove:
                zdroj = nazev
                break
        except Exception as e:
            print(f"  {klic}: {nazev} selhal ({e})")
    if not nove:
        raise RuntimeError(f"{klic}: žádný zdroj nevrátil data")

    dny = sorted(rada)
    hranice = dny[-PREPSAT_DNI] if len(dny) >= PREPSAT_DNI else dny[0]
    zmeneno = 0
    for d, v in nove.items():
        if d < hranice or v <= 0:
            continue
        if rada.get(d) != v:
            rada[d] = v
            zmeneno += 1

    # kontrola věrohodnosti posledních 30 dní
    dny = sorted(rada)
    for a, b in zip(dny[-31:], dny[-30:]):
        zmena = rada[b] / rada[a] - 1
        if abs(zmena) > max_zmena:
            raise RuntimeError(f"{klic}: podezřelá změna {zmena:+.1%} mezi {a} a {b}")
    uloz_csv(cesta, rada)
    print(f"  {klic}: {zdroj}, změněno/přidáno {zmeneno}, poslední den {dny[-1]} = {rada[dny[-1]]}")
    return rada


def kompaktni(rada):
    """Stejný formát, jaký mají vložená data v HTML: rozdíly dnů od 1970 + hodnoty."""
    epocha = dt.date(1970, 1, 1)
    dny = sorted(rada)
    cisla = [(dt.date.fromisoformat(d) - epocha).days for d in dny]
    return {"d": [cisla[0]] + [b - a for a, b in zip(cisla, cisla[1:])],
            "v": [round(rada[d], 2) for d in dny]}


def main():
    rady = {}
    for klic in RADY:
        rady[klic] = aktualizuj_radu(klic)
    with open(DATA / "margin_m2.csv", newline="", encoding="utf-8") as f:
        mg = [(r["ym"][:7], float(r["gross_ratio"])) for r in csv.DictReader(f)]
    mg.sort()
    vystup = {
        "sp": kompaktni(rady["sp"]), "nq": kompaktni(rady["nq"]), "vix": kompaktni(rady["vix"]),
        "mg": {"ym": [m for m, _ in mg], "v": [round(v, 6) for _, v in mg]},
        "konec": {k: max(rady[k]) for k in rady} | {"mg": mg[-1][0]},
        "vytvoreno": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
    }
    (SLOZKA / "data.json").write_text(json.dumps(vystup, separators=(",", ":")), encoding="utf-8")
    print("data.json:", vystup["konec"])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("CHYBA:", e)
        sys.exit(1)
