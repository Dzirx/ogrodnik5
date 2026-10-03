"""Książka na dysku: data/zrodla/<id>/ z oryginałem, stronami i meta.json.

Oryginał jest jedynym źródłem prawdy — strony i meta da się z niego
odtworzyć, więc ponowne przetworzenie nadpisuje je bez pytania, a oryginału
nie rusza nigdy."""

import json
import re
import shutil
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from app import config
from app.ingest.strony import Strona, odczytaj_strony


def slug(tekst: str) -> str:
    # NFKD nie rozkłada „ł" — bez tej podmiany Sułek dawałby „suek".
    tekst = tekst.replace("ł", "l").replace("Ł", "L")
    tekst = unicodedata.normalize("NFKD", tekst).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", tekst.lower()).strip("-") or "ksiazka"


def katalog(id: str) -> Path:
    return config.ZRODLA_DIR / id


def _nowe_id(tytul: str) -> str:
    baza = slug(tytul)
    id, n = baza, 2
    while katalog(id).exists():
        id, n = f"{baza}-{n}", n + 1
    return id


def czytaj_meta(id: str) -> dict:
    sciezka = katalog(id) / "meta.json"
    if sciezka.exists():
        return json.loads(sciezka.read_text(encoding="utf-8"))
    return {}


def _zapisz_meta(id: str, meta: dict) -> None:
    (katalog(id) / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


@contextmanager
def _nowa_ksiazka(id: str):
    # Nieudane wgranie nie może zostawić katalogu: zająłby id, a w bibliotece
    # wisiałaby książka bez oryginału.
    katalog(id).mkdir(parents=True)
    try:
        yield
    except BaseException:
        shutil.rmtree(katalog(id), ignore_errors=True)
        raise


def wgraj_pdf(plik: Path, tytul: str, autor: str = "", kategorie: list[str] | None = None) -> str:
    id = _nowe_id(tytul)
    with _nowa_ksiazka(id):
        shutil.copyfile(plik, katalog(id) / "original.pdf")
        _zapisz_meta(id, {"tytul": tytul, "autor": autor, "kategorie": kategorie or []})
        przetworz(id)
    return id


def wgraj_tekst(tekst: str, tytul: str, autor: str = "", kategorie: list[str] | None = None) -> str:
    id = _nowe_id(tytul)
    with _nowa_ksiazka(id):
        (katalog(id) / "original.txt").write_text(tekst, encoding="utf-8")
        _zapisz_meta(id, {"tytul": tytul, "autor": autor, "kategorie": kategorie or []})
        przetworz(id)
    return id


def przetworz(id: str) -> dict:
    """Strony i meta od nowa z oryginału. Przewodnik `ksiazka.md` zostaje —
    mógł go poprawić redaktor; nowy generuje się osobno (etap 2)."""
    kat = katalog(id)
    meta = czytaj_meta(id)
    meta.setdefault("tytul", id)
    meta.setdefault("autor", "")
    meta.setdefault("kategorie", [])

    if (kat / "original.pdf").exists():
        meta["rodzaj"] = "pdf"
        strony = odczytaj_strony((kat / "original.pdf").read_bytes())
    elif (kat / "original.txt").exists():
        meta["rodzaj"] = "tekst"
        strony = [Strona((kat / "original.txt").read_text(encoding="utf-8"), False, False)]
    else:
        raise FileNotFoundError(f"{id}: brak original.pdf i original.txt")

    # Zapis do katalogu obok i podmiana na końcu: przerwane przetwarzanie
    # nie zostawia połowy stron starych i połowy nowych.
    nowe = kat / "strony.nowe"
    shutil.rmtree(nowe, ignore_errors=True)
    nowe.mkdir()
    for numer, strona in enumerate(strony, start=1):
        # Pusta strona (same zdjęcia) też dostaje plik — numeracja ciągła.
        (nowe / f"{numer:04d}.txt").write_text(strona.tekst.strip() + "\n" if strona.tekst.strip() else "", encoding="utf-8")
    shutil.rmtree(kat / "strony", ignore_errors=True)
    nowe.rename(kat / "strony")

    meta["liczba_stron"] = len(strony)
    meta["strony_ocr"] = [n for n, s in enumerate(strony, start=1) if s.z_ocr]
    meta["strony_tabela"] = [n for n, s in enumerate(strony, start=1) if s.tabela]
    # Bez tego nieudany odczyt tabeli wygląda jak udany — strona ma tekst,
    # tylko poszarpany. Kod nie ocenia bloku, zapisuje tylko, czy model zadziałał.
    meta["odczyt_tabel"] = {
        str(n): s.tabela_blad or "ok" for n, s in enumerate(strony, start=1) if s.tabela
    }
    meta["status"] = "strony" if not (kat / "ksiazka.md").exists() else "gotowa"
    _zapisz_meta(id, meta)
    return meta


def zapisz_meta(id: str, meta: dict) -> None:
    _zapisz_meta(id, meta)


def utworz(tytul: str, autor: str = "", kategorie: list[str] | None = None,
           pdf: bytes | None = None, tekst: str | None = None) -> str:
    """Książka z panelu: sam oryginał i meta, bez przetwarzania.

    Tekst stron, OCR, tabele i przewodnik to minuty — robi je proces roboczy
    (app/worker.py), a panel od razu wraca do listy ze statusem „czeka"."""
    if not pdf and not (tekst and tekst.strip()):
        raise ValueError("podaj plik PDF albo tekst")
    id = _nowe_id(tytul)
    with _nowa_ksiazka(id):
        if pdf:
            (katalog(id) / "original.pdf").write_bytes(pdf)
        else:
            (katalog(id) / "original.txt").write_text(tekst, encoding="utf-8")
        _zapisz_meta(id, {"tytul": tytul, "autor": autor, "kategorie": kategorie or [],
                          "rodzaj": "pdf" if pdf else "tekst", "status": "czeka"})
    return id


def ustaw_status(id: str, status: str, blad: str | None = None) -> None:
    meta = czytaj_meta(id)
    meta["status"] = status
    if blad:
        meta["blad"] = blad
    else:
        meta.pop("blad", None)
    _zapisz_meta(id, meta)


def lista() -> list[dict]:
    """Wszystkie książki biblioteki: meta z dopisanym id, po tytule."""
    if not config.ZRODLA_DIR.exists():
        return []
    ksiazki = []
    for kat in config.ZRODLA_DIR.iterdir():
        if (kat / "meta.json").exists():
            meta = czytaj_meta(kat.name)
            meta["id"] = kat.name
            meta["ma_przewodnik"] = (kat / "ksiazka.md").exists()
            ksiazki.append(meta)
    return sorted(ksiazki, key=lambda m: m.get("tytul", m["id"]).lower())
