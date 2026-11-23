# pkohout-analogie-data

Data pro nástroje **Historické analogie** (pkohout.com) a interní **Laboratoř hypotéz**.

GitHub Actions každý pracovní den po zavření burzy v New Yorku spustí `aktualizuj.py`, který:

- stáhne zavírací hodnoty S&P 500 (^GSPC), Nasdaq Composite (^IXIC) a VIX (^VIX) z Yahoo Finance; když Yahoo nefunguje, použije FRED (SP500, NASDAQCOM, VIXCLS),
- doplní je do `data/*.csv` (posledních 10 dní smí přepsat opravenými hodnotami),
- zkontroluje věrohodnost denních změn (jinak běh selže a GitHub pošle e-mail),
- vytvoří `data.json`, který si stránky stahují při otevření.

Maržový dluh/M2 (`data/margin_m2.csv`) se doplňuje ručně jednou měsíčně řádkem `RRRR-MM,gross_ratio`.

Ruční spuštění: záložka **Actions → Denní aktualizace dat → Run workflow**.
