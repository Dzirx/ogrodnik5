"""Przewodnik `ksiazka.md`: droga do treści książki, nie treść.

Agent czyta przewodnik na starcie pytania i z niego wie, którą stronę
grepować i czytać. Najważniejsza jest kolumna słów: bez wektorów tylko ona
mówi, że „obcinanie czubków" stoi w książce jako „ogławianie".

Ręcznego wzorca (sulek-pomidory) nie dajemy modelowi jako przykładu —
przepisałby jego tematy do każdej książki, a porównanie z nim w etapie 2
straciłoby sens."""

import argparse
import sys
from pathlib import Path

from openai import OpenAI

from app import config
from app.ingest import zapis

_openai = OpenAI(api_key=config.OPENAI_API_KEY)

PROMPT = """Piszesz przewodnik po książce dla innego modelu, który będzie w niej szukał
odpowiedzi na pytania ogrodników. Tamten model ma tylko dwa narzędzia: grep po tekście
stron (dokładne słowa, bez odmiany i synonimów) i czytanie wskazanych stron. Przewodnik
mówi mu, GDZIE szukać i POD JAKIMI SŁOWAMI — nie zawiera treści książki.

Tekst książki masz niżej, strona po stronie, między znacznikami „=== STRONA N ==="
i „=== KONIEC STRONY N ===".
Numery stron to numery stron pliku (od 1), nie numery wydrukowane w książce.
Wiele stron zaczyna się od wydrukowanego numeru (np. „42 OCHRONA PRZED…" pod
znacznikiem „=== STRONA 43 ==="). Ten numer IGNORUJ — w mapie stron zawsze
numer ze znacznika, nad którym stoi tekst.

Napisz przewodnik w Markdown, dokładnie w tym układzie:

# {tytul}

Przewodnik, nie treść. Numery stron to numery stron pliku (od 1).
Wskazówki są pomocą w szukaniu. Cytujemy wyłącznie z oryginału, a gdy
przewodnik i oryginał się różnią, wygrywa oryginał.

## Co to jest
3–5 punktów: rodzaj książki i dla kogo; jaka uprawa (tunel, szklarnia, grunt) i jaka skala;
jaka roślina; jak jest pisana (poradnik, program ochrony, broszura, osobiste rady autora);
strony bez treści (same zdjęcia, okładka) — wymień ich numery.

## Czego tu nie ma
Tematy, których czytelnik takiej książki mógłby szukać, a których w niej nie ma
(np. „brak dawek środków ochrony roślin", „brak terminów siewu"). Tylko to, czego
brak jest pewny po przeczytaniu całości. To oszczędza szukania na darmo.

## Mapa stron

| Strony | Temat | Szukaj też jako |
|--------|-------|-----------------|

Jeden wiersz na spójny temat; zakres stron („14–16"), gdy temat przechodzi przez strony.
Wiersz obejmuje najwyżej 3 strony — dłuższy rozdział (np. „Choroby" na 10 stronach)
podziel na wiersze po jednej chorobie, problemie albo zabiegu.
Pokryj wszystkie strony z treścią. „Temat" nazywa, o czym jest strona, nie podaje
wartości — bez liczb, dawek, terminów i zaleceń (te model przeczyta ze strony).
„Szukaj też jako": 2–6 słów lub krótkich fraz, które DOSŁOWNIE stoją na tych stronach
— szczególnie fachowe i nieoczywiste (np. „ogławianie", „wilki", „pikowanie",
nazwy chorób, preparatów, substancji). Podawaj POJEDYNCZE słowa albo rdzenie
(„pikow", „zapraw", „odkaż"), nie frazy: łamanie linii i OCR rozbijają frazy
w tekście, a rdzeń trafia każdą odmianę. Gdy termin książki różni się od tego,
jak powie laik, dopisz potoczne słowo pytającego w tej samej komórce.

## Pułapki
Krótkie punkty o tym, co może zmylić szukającego: tematy rozłożone na kilka stron
lub rozdziałów; ten sam temat w dwóch miejscach w różnych warunkach (tunel / grunt,
etap uprawy); strony z tabelą odczytaną automatycznie ({tabele}); strony odczytane
z obrazu przez OCR ({ocr}) — możliwe literówki; osobiste rekomendacje autora
(konkretne produkty); słowa książki inne niż słowa pytającego.

Pisz po polsku, zwięźle, bez wstępu i bez podsumowania. Zwróć tylko przewodnik.
"""

PROMPT_KAWALEK = """To jest kawałek dłuższej książki: strony {od}–{do} z {razem}.
Napisz przewodnik tylko dla tych stron, w tym samym układzie. W „Czego tu nie ma"
wpisz tylko to, co jest pewne dla tego kawałka; zostanie to złożone z resztą.
"""

PROMPT_SKLADANIE = """Niżej masz przewodniki po kolejnych kawałkach jednej książki „{tytul}".
Złóż z nich jeden przewodnik w tym samym układzie:
- „Co to jest" — jedno spójne ujęcie całej książki,
- „Czego tu nie ma" — tylko to, czego brakuje we WSZYSTKICH kawałkach,
- „Mapa stron" — wszystkie wiersze ze wszystkich kawałków, po kolei; temat
  przechodzący przez granicę kawałków połącz w jeden wiersz,
- „Pułapki" — połączone, bez powtórzeń.
Zwróć tylko przewodnik.

"""


def _tekst_stron(id: str, od: int, do: int) -> str:
    kat = zapis.katalog(id) / "strony"
    czesci = []
    for n in range(od, do + 1):
        tekst = (kat / f"{n:04d}.txt").read_text(encoding="utf-8").strip()
        # Znacznik też na końcu: broszury drukują własny numer na początku
        # strony (PODR: „42 OCHRONA…" pod znacznikiem 43) i model brał go
        # zamiast numeru pliku — cała mapa od s. 40 była przesunięta o jeden.
        czesci.append(
            f"=== STRONA {n} ===\n{tekst or '(brak tekstu — strona bez treści albo same zdjęcia)'}"
            f"\n=== KONIEC STRONY {n} ==="
        )
    return "\n\n".join(czesci)


def _zapytaj(prompt: str) -> str:
    odp = _openai.chat.completions.create(
        model=config.PRZEWODNIK_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    # Model zapisujemy na stderr — w .env go nie podglądamy, a do porównania
    # przewodników trzeba wiedzieć, który je pisał.
    print(f"[przewodnik] model={odp.model} tokeny={odp.usage.total_tokens}", file=sys.stderr)
    return odp.choices[0].message.content.strip()


def _lista(numery: list[int]) -> str:
    return "s. " + ", ".join(map(str, numery)) if numery else "brak w tej książce"


def generuj(id: str) -> str:
    meta = zapis.czytaj_meta(id)
    razem = meta["liczba_stron"]
    prompt = PROMPT.format(
        tytul=meta.get("tytul", id),
        tabele=_lista(meta.get("strony_tabela", [])),
        ocr=_lista(meta.get("strony_ocr", [])),
    )
    krok = config.PRZEWODNIK_STRON_NA_KAWALEK
    if razem <= krok:
        return _zapytaj(prompt + "\n\nTEKST KSIĄŻKI:\n\n" + _tekst_stron(id, 1, razem))

    kawalki = []
    for od in range(1, razem + 1, krok):
        do = min(od + krok - 1, razem)
        kawalki.append(_zapytaj(
            prompt + "\n" + PROMPT_KAWALEK.format(od=od, do=do, razem=razem)
            + "\n\nTEKST KSIĄŻKI:\n\n" + _tekst_stron(id, od, do)
        ))
    return _zapytaj(
        PROMPT_SKLADANIE.format(tytul=meta.get("tytul", id))
        + "\n\n---\n\n".join(kawalki)
    )


def zapisz(id: str, nadpisz: bool = False, wyjscie: Path | None = None) -> Path:
    """Domyślnie do ksiazka.md, ale nie na istniejący — mógł go poprawić redaktor."""
    cel = wyjscie or zapis.katalog(id) / "ksiazka.md"
    if cel.exists() and not nadpisz:
        raise FileExistsError(f"{cel} istnieje — użyj --nadpisz albo --wyjscie")
    cel.write_text(generuj(id) + "\n", encoding="utf-8")
    if cel.name == "ksiazka.md":
        meta = zapis.czytaj_meta(id)
        meta["status"] = "gotowa"
        zapis._zapisz_meta(id, meta)
    return cel


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.ingest.przewodnik")
    p.add_argument("id")
    p.add_argument("--nadpisz", action="store_true", help="nadpisz istniejący ksiazka.md")
    p.add_argument("--wyjscie", type=Path, help="zapisz gdzie indziej (np. do porównania)")
    a = p.parse_args()
    print(zapisz(a.id, a.nadpisz, a.wyjscie))


if __name__ == "__main__":
    main()
