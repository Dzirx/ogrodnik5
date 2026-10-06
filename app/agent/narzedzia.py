"""Narzędzia agenta: szukaj, czytaj_strony, przewodnik, poza_zakresem.

Zwykłe funkcje, bez modelu. Zakres ustawia kod przy rozmowie, nie model:
narzędzie po prostu nie widzi książek spoza zaznaczenia. Książka spoza
zakresu daje błąd, a nie treść — prompt można obejść, parametr nie.

Wyniki to słowniki gotowe do json.dumps; błąd to {"blad": ...}, żeby model
mógł go przeczytać i spróbować inaczej, zamiast przerywać pętlę."""

import re
from dataclasses import dataclass
from functools import cache

import regex as _regex

from app import config
from app.ingest import zapis

# Ile znaków wokół trafienia. Okno znaków, nie linijki: tekst z PDF ma
# łamanie co kilka słów, a tabela z modelu to jedna długa linia na pole.
KONTEKST = 200
# Granice narzędzia szukaj/lista: wzorzec od modelu nie może zawiesić procesu,
# a wynik — zalać kontekstu.
MAX_REGEX = 300
TIMEOUT_REGEX_S = 1.0
MAX_TRAFIEN_NA_STRONE = 500
KONTEKST_MAX = 600
MAX_LIMIT = 60
MAX_STRON_W_TRYBIE = 300
LISTA_LIMIT_STRON = 60
POCZATEK_ZNAKOW = 90
# Przy kilku trafieniach na stronie — krótszy kontekst każdego, żeby wynik
# nie puchł; pełny tekst daje czytaj_strony.
KONTEKST_KILKU = 100
TRAFIEN_NA_STRONE = 3
# Podpowiedź „zaznaczyć?" ma wskazać, gdzie jest temat, a nie wyliczać wszystko.
POZA_ZAKRESEM_STRON = 5
POZA_ZAKRESEM_KSIAZEK = 3


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


def _fragment(tekst: str, start: int, koniec: int, kontekst: int = KONTEKST) -> str:
    od, do = max(0, start - kontekst), min(len(tekst), koniec + kontekst)
    # Do granicy słowa, żeby fragment nie zaczynał się od pół wyrazu.
    if od > 0:
        od = tekst.find(" ", od) + 1 or od
    if do < len(tekst) and (spacja := tekst.rfind(" ", koniec, do)) > 0:
        do = spacja
    return ("…" if od > 0 else "") + tekst[od:do] + ("…" if do < len(tekst) else "")


def _wzor_literalny(fraza: str) -> str:
    """„nasion|nasien|F1" — warianty jak w grep -E, ale każdy dosłownie
    (bez reszty składni wzorców: model pisze frazy, nie regexy)."""
    warianty = [re.escape(re.sub(r"\s+", " ", w.strip())) for w in fraza.split("|") if len(w.strip()) >= 2]
    return "|".join(warianty) or r"(?!x)x"


def _kompiluj(fraza: str | None, jako_regex: bool):
    """Wzorzec do szukania albo None, gdy nie podano. Wzorzec od modelu ma limit
    długości i czasu: zły regex (np. „(a|aa)+$") nie może zawiesić procesu."""
    if not fraza:
        return None
    if jako_regex:
        if len(fraza) > MAX_REGEX:
            raise ValueError(f"wzorzec za długi (najwyżej {MAX_REGEX} znaków)")
        try:
            return _regex.compile(fraza, _regex.IGNORECASE)
        except _regex.error as e:
            raise ValueError(f"zły wzorzec: {e}")
    return _regex.compile(_wzor_literalny(fraza), _regex.IGNORECASE)


def _trafienia_na_stronie(wzor, tekst: str) -> list:
    wynik = []
    for m in wzor.finditer(tekst, timeout=TIMEOUT_REGEX_S):
        if m.end() == m.start():  # pusty wynik („a*") nie jest trafieniem
            continue
        wynik.append(m)
        if len(wynik) >= MAX_TRAFIEN_NA_STRONE:
            break
    return wynik


def _trafienia(id: str, fraza: str, razem_z: str | None = None, bez: str | None = None,
               jako_regex: bool = False, kontekst: int | None = None,
               z_fragmentami: bool = True) -> list[tuple[int, int, list[str]]]:
    """(strona, liczba trafień na stronie, fragmenty wokół pierwszych kilku).

    razem_z: strona musi zawierać także to (warunek „i"); bez: strona NIE może
    tego zawierać — jak drugi i trzeci grep na wynikach pierwszego."""
    wzor = _kompiluj(fraza, jako_regex)
    warunek, wyklucz = _kompiluj(razem_z, jako_regex), _kompiluj(bez, jako_regex)
    wynik = []
    for numer, tekst in enumerate(_tekst_stron(id), start=1):
        trafione = _trafienia_na_stronie(wzor, tekst)
        if not trafione:
            continue
        if warunek and not warunek.search(tekst, timeout=TIMEOUT_REGEX_S):
            continue
        if wyklucz and wyklucz.search(tekst, timeout=TIMEOUT_REGEX_S):
            continue
        fragmenty = []
        if z_fragmentami:
            k = min(kontekst, KONTEKST_MAX) if kontekst else (KONTEKST if len(trafione) == 1 else KONTEKST_KILKU)
            fragmenty = [_fragment(tekst, t.start(), t.end(), k) for t in trafione[:TRAFIEN_NA_STRONE]]
        wynik.append((numer, len(trafione), fragmenty))
    return wynik


def szukaj(zakres: Zakres, fraza: str, ksiazki: list[str] | None = None, razem_z: str | None = None,
           *, bez: str | None = None, regex: bool = False, tryb: str = "fragmenty",
           kontekst: int | None = None, limit: int | None = None) -> dict:
    """Jak grep po stronach zaznaczonych książek. Domyślnie dosłowna fraza bez
    wielkości liter i bez odmiany („a|b|c" — warianty); regex=True traktuje
    fraza / razem_z / bez jak wzorce regularne.

    tryb: „fragmenty" (strona + fragmenty), „strony" (same numery stron — tanie
    rozpoznanie) albo „licz" (liczby trafień na książkę, jak grep -c)."""
    if len((fraza or "").strip()) < 2:
        return {"blad": "fraza za krótka"}
    if tryb not in ("fragmenty", "strony", "licz"):
        return {"blad": "tryb: fragmenty, strony albo licz"}
    ids = ksiazki or list(zakres.ksiazki)
    for id in ids:
        if blad := _poza(zakres, id):
            return blad
    try:
        wyniki = {id: _trafienia(id, fraza, razem_z, bez, regex, kontekst, z_fragmentami=(tryb == "fragmenty"))
                  for id in ids}
    except ValueError as e:
        return {"blad": str(e)}
    except TimeoutError:
        return {"blad": "wzorzec zbyt kosztowny — uprość go"}

    opis = {"fraza": fraza, **({"razem_z": razem_z} if razem_z else {}),
            **({"bez": bez} if bez else {}), **({"regex": True} if regex else {})}
    if tryb == "licz":
        return {**opis, "tryb": "licz", "ksiazki": [
            {"ksiazka": id, "stron_z_trafieniem": len(t), "trafien": sum(x[1] for x in t)}
            for id, t in wyniki.items()]}
    if tryb == "strony":
        return {**opis, "tryb": "strony", "ksiazki": [
            {"ksiazka": id, "stron_z_trafieniem": len(t), "strony": [x[0] for x in t][:MAX_STRON_W_TRYBIE]}
            for id, t in wyniki.items()]}

    trafienia = [
        {"ksiazka": id, "strona": strona, "trafien_na_stronie": ile, "fragmenty": fragmenty}
        for id, t in wyniki.items()
        for strona, ile, fragmenty in t
    ]
    limit = min(limit or config.SZUKAJ_LIMIT_TRAFIEN, MAX_LIMIT)
    wynik = {**opis, "stron_z_trafieniem": len(trafienia), "trafienia": trafienia[:limit]}
    if len(trafienia) > limit:
        wynik["uwaga"] = (
            f"pokazano {limit} z {len(trafienia)} stron — zawęź frazę, dodaj razem_z / bez "
            f"albo użyj trybu „strony”")
    return wynik


def lista(zakres: Zakres, ksiazka: str | None = None, od: int = 1, do: int | None = None) -> dict:
    """Jak ls i head: bez książki — książki zakresu; z książką — jej strony
    z początkiem tekstu, żeby zobaczyć układ rozdziałów bez czytania."""
    if ksiazka is None:
        wynik = []
        for id in zakres.ksiazki:
            meta, teksty = zapis.czytaj_meta(id), _tekst_stron(id)
            wynik.append({
                "ksiazka": id, "tytul": meta.get("tytul", id), "kategorie": meta.get("kategorie", []),
                "stron": len(teksty), "pustych": sum(1 for t in teksty if not t),
                "strony_tabela": meta.get("strony_tabela", []), "strony_ocr": meta.get("strony_ocr", []),
                "przewodnik": (zapis.katalog(id) / "ksiazka.md").exists(),
            })
        return {"ksiazki": wynik}
    if blad := _poza(zakres, ksiazka):
        return blad
    meta, teksty = zapis.czytaj_meta(ksiazka), _tekst_stron(ksiazka)
    razem = len(teksty)
    do = min(do or razem, razem)
    if not 1 <= od <= do:
        return {"blad": f"strony {od}–{do} poza książką (ma {razem} stron)"}
    koniec = min(do, od + LISTA_LIMIT_STRON - 1)
    tabele, ocr = set(meta.get("strony_tabela", [])), set(meta.get("strony_ocr", []))
    strony = []
    for n in range(od, koniec + 1):
        tekst = teksty[n - 1]
        wpis = {"strona": n, "poczatek": tekst[:POCZATEK_ZNAKOW] + ("…" if len(tekst) > POCZATEK_ZNAKOW else "")}
        if not tekst:
            wpis = {"strona": n, "pusta": True}
        if n in tabele:
            wpis["tabela"] = True
        if n in ocr:
            wpis["ocr"] = True
        strony.append(wpis)
    wynik = {"ksiazka": ksiazka, "stron": razem, "strony": strony}
    if koniec < do:
        wynik["uwaga"] = f"limit {LISTA_LIMIT_STRON} stron na wywołanie — dalej od strony {koniec + 1}"
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
        trafione = _trafienia(id, fraza)
        if trafione:
            # Strony z największą liczbą trafień — tam temat jest, a nie tylko
            # wspomniany. Bez limitu podpowiedź wymieniała 22 strony.
            najlepsze = sorted(trafione, key=lambda t: -t[1])[:POZA_ZAKRESEM_STRON]
            wynik.append({
                "ksiazka": id,
                "tytul": zapis.czytaj_meta(id).get("tytul", id),
                "strony": sorted(s for s, _, _ in najlepsze),
                "stron_z_trafieniem": len(trafione),
                "_trafien": sum(ile for _, ile, _ in trafione),
            })
    wynik.sort(key=lambda w: -w.pop("_trafien"))
    return {"fraza": fraza, "poza_zakresem": wynik[:POZA_ZAKRESEM_KSIAZEK]}
