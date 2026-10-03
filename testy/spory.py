"""Scenariusz sporu z planu (etap 5) — kroki po kolei, na jednej bazie:

1. pytanie o sporną liczbę → agent zgłasza spór,
2. to samo pytanie drugi raz → spór nie wraca (żadnego nowego),
3. redaktor rozstrzyga → odpowiedź używa przyjętej wartości ze znacznikiem [U..],
4. pytanie o ten sam temat w innym warunku → ustalenie nie zostaje przeniesione.

    python testy/spory.py testy/spory.yaml

Kod tylko liczy zgłoszenia (to stan bazy, nie treść); czy odpowiedź
poprawnie użyła ustalenia, ocenia człowiek z raportu."""

import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, spory  # noqa: E402
from app.agent.agent import odpowiedz  # noqa: E402


def _krok(linie: list[str], tytul: str, ksiazki: list[str], pytanie: str) -> str:
    przed = len(spory.lista())
    wynik = odpowiedz(ksiazki, pytanie)
    s = wynik.slad.do_json()
    nowe = spory.lista()[przed:]
    linie += [f"### {tytul}", "", f"**Pytanie:** {pytanie}", "", wynik.tekst, "",
              f"*Nowe spory:* {len(nowe)}  ", f"*Czas / koszt:* {s['czas_s']} s / "
              + (f"${s['koszt_usd']:.4f}" if s["koszt_usd"] is not None else "?"), ""]
    linie += ["```", *(spory.opis(n) for n in nowe), "```", ""] if nowe else []
    return wynik.tekst


def main() -> None:
    plik = Path(sys.argv[1])
    scenariusze = yaml.safe_load(plik.read_text(encoding="utf-8"))
    katalog = Path(__file__).parent / "wyniki" / f"{datetime.now():%Y-%m-%d_%H%M%S}_{plik.stem}"
    katalog.mkdir(parents=True, exist_ok=True)
    config.DB_PATH = katalog / "ogrodnik.db"

    linie = [f"# Scenariusze sporów {datetime.now():%Y-%m-%d %H:%M}", ""]
    for sc in scenariusze:
        ksiazki = sc["ksiazki"]
        linie += ["---", "", f"## {sc['id']}", "", f"*Zakres:* {', '.join(ksiazki)}", "",
                  f"*Oczekiwane:* {sc['oczekiwane'].strip()}", ""]
        przed = len(spory.lista())
        _krok(linie, "1. Pierwsze pytanie — spór ma zostać zgłoszony", ksiazki, sc["pytanie"])
        zgloszone = spory.lista()[przed:]
        _krok(linie, "2. To samo pytanie — spór nie może wrócić", ksiazki, sc["pytanie"])
        if not zgloszone:
            linie += ["**Spór nie został zgłoszony — kroki 3–4 pominięte.**", ""]
            continue
        spor = zgloszone[0]
        wartosc = sc.get("rozstrzygnij") or spor["opcje"][0]["wartosc"]
        spory.rozstrzygnij(spor["id"], wartosc)
        linie += [f"*Redaktor rozstrzyga U{spor['id']}: przyjęto „{wartosc}\".*", ""]
        _krok(linie, f"3. Po rozstrzygnięciu — wartość z ustalenia ze znacznikiem [U{spor['id']}]",
              ksiazki, sc["pytanie"])
        if sc.get("inny_warunek"):
            _krok(linie, "4. Inny warunek — ustalenie NIE może zostać przeniesione", ksiazki, sc["inny_warunek"])

    linie += ["---", "", "## Spory w bazie na koniec", "", "```",
              *(spory.opis(s) for s in spory.lista()), "```"]
    (katalog / "raport.md").write_text("\n".join(linie) + "\n", encoding="utf-8")
    (katalog / "spory.json").write_text(json.dumps(spory.lista(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(katalog / "raport.md")


if __name__ == "__main__":
    main()
