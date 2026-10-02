"""Narzędzia agenta: szukaj, czytaj_strony, przewodnik, poza_zakresem.

Zwykłe funkcje, bez modelu. Zakres ustawia kod przy rozmowie, nie model:
narzędzie po prostu nie widzi książek spoza zaznaczenia. Książka spoza
zakresu daje błąd, a nie treść — prompt można obejść, parametr nie.

Wyniki to słowniki gotowe do json.dumps; błąd to {"blad": ...}, żeby model
mógł go przeczytać i spróbować inaczej, zamiast przerywać pętlę."""

import re
from dataclasses import dataclass
from functools import cache

from app import config
from app.ingest import zapis

# Ile znaków wokół trafienia. Okno znaków, nie linijki: tekst z PDF ma
# łamanie co kilka słów, a tabela z modelu to jedna długa linia na pole.
KONTEKST = 200


@dataclass(frozen=True)
class Zakres:
    ksiazki: tuple[str, ...]

    def __contains__(self, id: str) -> bool:
        return id in self.ksiazki


def _wszystkie() -> list[str]:
    if not config.ZRODLA_DIR.exists():
        return []
    return sorted(p.name for p in config.ZRODLA_DIR.iterdir() if (p / "meta.json").exists())


def _poza(zakres: Zakres, id: str) -> dict | None:
    if id not in zakres:
        return {"blad": f"książka {id!r} nie jest w zaznaczonym zakresie"}
    return None


@cache
def _strony(id: str, _znacznik: float) -> list[str]:
    """Tekst stron ze złączonymi białymi znakami — fraza przełamana końcem
    linii („saletry\\nwapniowej") też trafia. Cache po czasie meta.json,
    więc ponowne przetworzenie książki go unieważnia."""
    katalog = zapis.katalog(id) / "strony"
    return [re.sub(r"\s+", " ", p.read_text(encoding="utf-8")).strip() for p in sorted(katalog.glob("*.txt"))]


def _tekst_stron(id: str) -> list[str]:
    return _strony(id, (zapis.katalog(id) / "meta.json").stat().st_mtime)


def _fragment(tekst: str, start: int, koniec: int) -> str:
    od, do = max(0, start - KONTEKST), min(len(tekst), koniec + KONTEKST)
    # Do granicy słowa, żeby fragment nie zaczynał się od pół wyrazu.
    if od > 0:
        od = tekst.find(" ", od) + 1 or od
    if do < len(tekst) and (spacja := tekst.rfind(" ", koniec, do)) > 0:
        do = spacja
    return ("…" if od > 0 else "") + tekst[od:do] + ("…" if do < len(tekst) else "")


def _trafienia(id: str, fraza: str) -> list[tuple[int, int, str]]:
    """(strona, liczba trafień na stronie, fragment wokół pierwszego)."""
    wzor = re.compile(re.escape(re.sub(r"\s+", " ", fraza.strip())), re.IGNORECASE)
    wynik = []
    for numer, tekst in enumerate(_tekst_stron(id), start=1):
        trafione = list(wzor.finditer(tekst))
        if trafione:
            wynik.append((numer, len(trafione), _fragment(tekst, trafione[0].start(), trafione[0].end())))
    return wynik


def szukaj(zakres: Zakres, fraza: str, ksiazki: list[str] | None = None) -> dict:
    """Dosłowna fraza bez rozróżniania wielkości liter, bez odmiany —
    odmianę łapie model, szukając rdzenia albo kilku wariantów."""
    if len(fraza.strip()) < 2:
        return {"blad": "fraza za krótka"}
    ids = ksiazki or list(zakres.ksiazki)
    for id in ids:
        if blad := _poza(zakres, id):
            return blad
    trafienia = [
        {"ksiazka": id, "strona": strona, "trafien_na_stronie": ile, "fragment": fragment}
        for id in ids
        for strona, ile, fragment in _trafienia(id, fraza)
    ]
    limit = config.SZUKAJ_LIMIT_TRAFIEN
    wynik = {"fraza": fraza, "stron_z_trafieniem": len(trafienia), "trafienia": trafienia[:limit]}
    if len(trafienia) > limit:
        wynik["uwaga"] = (
            f"pokazano {limit} z {len(trafienia)} stron — zawęź frazę albo książki"
        )
    return wynik


def czytaj_strony(zakres: Zakres, ksiazka: str, od: int, do: int | None = None) -> dict:
    if blad := _poza(zakres, ksiazka):
        return blad
    do = do or od
    meta = zapis.czytaj_meta(ksiazka)
    razem = meta["liczba_stron"]
    if not 1 <= od <= do <= razem:
        return {"blad": f"strony {od}–{do} poza książką (ma {razem} stron)"}
    limit = config.CZYTAJ_LIMIT_STRON
    obcieto = do - od + 1 > limit
    do = min(do, od + limit - 1)
    tabele, ocr = set(meta.get("strony_tabela", [])), set(meta.get("strony_ocr", []))
    katalog = zapis.katalog(ksiazka) / "strony"
    strony = []
    for n in range(od, do + 1):
        strona = {"strona": n, "tekst": (katalog / f"{n:04d}.txt").read_text(encoding="utf-8").strip()
                  or "(strona bez tekstu — zdjęcia albo pusta)"}
        # Model ma wiedzieć, że wartości z takiej strony mogą być przekręcone —
        # to samo mówi redaktorowi etykieta w panelu.
        if n in tabele:
            strona["uwaga"] = "tabela odczytana automatycznie przez model"
        elif n in ocr:
            strona["uwaga"] = "część tekstu z OCR — możliwe literówki"
        strony.append(strona)
    wynik = {"ksiazka": ksiazka, "strony": strony}
    if obcieto:
        wynik["uwaga"] = f"limit {limit} stron na wywołanie — dalej od strony {do + 1}"
    return wynik


def przewodnik(zakres: Zakres, ksiazka: str) -> dict:
    if blad := _poza(zakres, ksiazka):
        return blad
    sciezka = zapis.katalog(ksiazka) / "ksiazka.md"
    if not sciezka.exists():
        return {"blad": f"książka {ksiazka!r} nie ma jeszcze przewodnika — użyj szukaj"}
    return {"ksiazka": ksiazka, "przewodnik": sciezka.read_text(encoding="utf-8")}


def poza_zakresem(zakres: Zakres, fraza: str) -> dict:
    """Same tytuły i numery stron — bez tekstu, żeby odpowiedź nadal stała
    wyłącznie na zaznaczonych książkach. Służy do podpowiedzi „zaznaczyć?"."""
    if len(fraza.strip()) < 2:
        return {"blad": "fraza za krótka"}
    wynik = []
    for id in _wszystkie():
        if id in zakres:
            continue
        strony = [s for s, _, _ in _trafienia(id, fraza)]
        if strony:
            wynik.append({"ksiazka": id, "tytul": zapis.czytaj_meta(id).get("tytul", id), "strony": strony})
    return {"fraza": fraza, "poza_zakresem": wynik}
