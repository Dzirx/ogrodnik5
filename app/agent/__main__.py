"""Pytanie z wiersza poleceń, zanim powstanie panel.

    python -m app.agent --ksiazki sulek-pomidory "Kiedy obcinać czubki?"
"""

import argparse
import json
import sys
from pathlib import Path

from app.agent.agent import odpowiedz


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.agent")
    p.add_argument("pytanie")
    p.add_argument("--ksiazki", nargs="+", required=True)
    p.add_argument("--slad", type=Path, help="zapisz ślad do pliku JSON")
    a = p.parse_args()

    wynik = odpowiedz(a.ksiazki, a.pytanie)
    print(wynik.tekst)
    s = wynik.slad.do_json()
    koszt = f"${s['koszt_usd']:.4f}" if s["koszt_usd"] is not None else "koszt nieznany"
    narzedzi = sum(1 for z in s["zdarzenia"] if "narzedzie" in z)
    print(f"\n[{s['czas_s']} s, {narzedzi} wywołań narzędzi, {koszt}]", file=sys.stderr)
    if a.slad:
        a.slad.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
