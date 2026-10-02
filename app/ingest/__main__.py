"""Wgrywanie z wiersza poleceń, zanim powstanie panel.

    python -m app.ingest plik.pdf --tytul "Sułek pomidory" --kategorie pomidor
    python -m app.ingest --tekst notatka.txt --tytul "Notatka" --kategorie pomidor
    python -m app.ingest --przetworz sulek-pomidory
"""

import argparse
import json
from pathlib import Path

from app.ingest import zapis


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.ingest")
    p.add_argument("plik", nargs="?", type=Path, help="PDF do wgrania")
    p.add_argument("--tekst", type=Path, help="plik tekstowy wgrywany jako wklejony tekst")
    p.add_argument("--przetworz", metavar="ID", help="przetwórz ponownie istniejącą książkę")
    p.add_argument("--tytul")
    p.add_argument("--autor", default="")
    p.add_argument("--kategorie", nargs="*", default=[])
    a = p.parse_args()

    if a.przetworz:
        meta = zapis.przetworz(a.przetworz)
        id = a.przetworz
    else:
        if not a.tytul or not (a.plik or a.tekst):
            p.error("podaj plik PDF albo --tekst oraz --tytul")
        if a.plik:
            id = zapis.wgraj_pdf(a.plik, a.tytul, a.autor, a.kategorie)
        else:
            id = zapis.wgraj_tekst(a.tekst.read_text(encoding="utf-8"), a.tytul, a.autor, a.kategorie)
        meta = zapis.czytaj_meta(id)
    print(id)
    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
