"""Odpowiedź modelu jako HTML: akapity, listy i znaczniki źródeł jako linki.

Tekst z bazy najpierw idzie przez escape, dopiero potem dokładamy znaczniki —
surowego HTML-a z modelu ani z poprawki redaktora nigdy nie wstawiamy."""

import re
from urllib.parse import quote

from markupsafe import Markup, escape

# [sulek-pomidory s. 12, 28], [sulek-pomidory s. 13–14] albo — gdy model
# złamie zasadę „jedna książka w nawiasie" — [a s. 15; b s. 7]. Wyświetlanie
# ma to znieść: bez tego znacznik został surowym tekstem, bez linku, a książka
# nie trafiała do listy źródeł.
_POZYCJA = r"[a-z0-9][a-z0-9-]* s\. \d[\d,\s–-]*"
ZNACZNIK_ZRODLA = re.compile(rf"\[({_POZYCJA}(?:;\s*{_POZYCJA})*)\]")
_POZYCJA_RE = re.compile(r"([a-z0-9][a-z0-9-]*) s\. (\d[\d,\s–-]*)")


def pozycje(grupa: str) -> list[tuple[str, str]]:
    """„a s. 15; b s. 7" → [("a", "15"), ("b", "7")]."""
    return [(m[1], m[2].strip()) for m in _POZYCJA_RE.finditer(grupa)]
ZNACZNIK_SPORU = re.compile(r"\[U(\d+)\]")
POGRUBIENIE = re.compile(r"\*\*(.+?)\*\*")


def strony(zapis: str) -> list[int]:
    """„12, 28" → [12, 28]; „13–14" → [13, 14]. Zakres rozwijamy, bo każda
    strona dostaje własny link."""
    wynik: list[int] = []
    for czesc in re.split(r"\s*,\s*", zapis.strip()):
        if m := re.fullmatch(r"(\d+)\s*[–-]\s*(\d+)", czesc):
            od, do = int(m[1]), int(m[2])
            wynik += list(range(od, do + 1)) if 0 < do - od < 30 else [od, do]
        elif czesc.isdigit():
            wynik.append(int(czesc))
    return list(dict.fromkeys(wynik))


ETYKIETY_SPORU = {"otwarty": "spór", "rozstrzygniety": "ustalenie redakcji", "odrzucony": "to nie spór"}


INDEKSY = "¹²³⁴⁵⁶⁷⁸⁹"


def numer_ksiazki(numery: dict[str, int], id: str) -> str:
    """Indeks górny książki w znaczniku — tylko gdy odpowiedź ma kilka książek."""
    if len(numery) < 2 or id not in numery:
        return ""
    n = numery[id]
    return INDEKSY[n - 1] if n <= len(INDEKSY) else str(n)


def _linia(tekst: str, tytuly: dict[str, str], baza_url: str, statusy: dict[int, str],
           numery: dict[str, int]) -> Markup:
    # Zdanie bez znaczników idzie w linku do podglądu — po nim podgląd
    # zaznacza na stronie liczby, które redaktor chce sprawdzić.
    fraza = quote(ZNACZNIK_SPORU.sub("", ZNACZNIK_ZRODLA.sub("", tekst))[:200])
    html = str(escape(tekst))
    html = POGRUBIENIE.sub(r"<strong>\1</strong>", html)

    def zrodlo(m: re.Match) -> str:
        spany = []
        for id, zapis_stron in pozycje(m[1]):
            tytul = escape(tytuly.get(id, id))
            linki = ", ".join(
                f'<a href="{baza_url}?podglad={id}:{n}&amp;f={fraza}" title="{tytul}, strona {n}">{n}</a>'
                for n in strony(zapis_stron)
            )
            # Krótko: „s. 14" (i indeks książki, gdy jest ich kilka). Pełny tytuł
            # przy każdym zdaniu zaśmiecał tekst — jest w podpowiedzi i w źródłach.
            spany.append(f'<span class="znacznik" title="{tytul}">{numer_ksiazki(numery, id)}s. {linki}</span>')
        return " ".join(spany)

    def spor(m: re.Match) -> str:
        # Etykieta po bieżącym statusie: „ustalenie redakcji" tylko przy
        # rozstrzygniętym — przy otwartym myliłoby, że ktoś już zdecydował.
        status = statusy.get(int(m[1]), "otwarty")
        return (f'<a class="spor-znacznik {status}" href="/spory#U{m[1]}" '
                f'title="Spór U{m[1]} — obie wartości i decyzja redakcji">'
                f'{ETYKIETY_SPORU.get(status, "spór")} · U{m[1]}</a>')

    html = ZNACZNIK_ZRODLA.sub(zrodlo, html)
    # Dwa znaczniki obok siebie ([a s. 61][b s. 26]) sklejały się w „¹s. 61²s. 26".
    html = html.replace('</span><span class="znacznik"', '</span> <span class="znacznik"')
    html = ZNACZNIK_SPORU.sub(spor, html)
    return Markup(html)


def _blok_html(linie: list[str], f) -> str:
    """Jeden blok tekstu: akapity, listy i podlisty (jeden poziom wcięcia).

    Model pisze „Co się z nimi robi:" i od razu listę, czasem z podpunktami.
    Wcześniej lista była listą tylko wtedy, gdy WSZYSTKIE linie bloku były
    punktami — inaczej zostawały surowe myślniki, a podpunkty traciły wcięcie."""
    wynik, akapit, pozycje = [], [], []

    def zamknij_akapit():
        if akapit:
            wynik.append("<p>" + "<br>".join(akapit) + "</p>")
            akapit.clear()

    def zamknij_liste():
        if pozycje:
            glowne: list[list] = []  # [html, [dzieci]]
            for poziom, html in pozycje:
                if poziom and glowne:
                    glowne[-1][1].append(html)
                else:
                    glowne.append([html, []])
            wynik.append("<ul>" + "".join(
                f"<li>{h}" + (("<ul>" + "".join(f"<li>{d}</li>" for d in dzieci) + "</ul>") if dzieci else "") + "</li>"
                for h, dzieci in glowne) + "</ul>")
            pozycje.clear()

    for l in linie:
        m = re.match(r"^(\s*)[-•*]\s+(.*)$", l)
        if m:
            zamknij_akapit()
            pozycje.append((1 if len(m[1].expandtabs(2)) >= 2 else 0, str(f(m[2]))))
        else:
            zamknij_liste()
            akapit.append(str(f(l.strip())))
    zamknij_akapit()
    zamknij_liste()
    return "".join(wynik)


def odpowiedz_html(tekst: str, tytuly: dict[str, str], baza_url: str = "",
                   statusy: dict[int, str] | None = None) -> Markup:
    """Akapity po pustej linii, listy z „- " (także z podpunktami). Więcej
    Markdownu model nie powinien pisać (styl: bez nagłówków i ozdobników)."""
    numery = {id: i for i, id in enumerate(zrodla_odpowiedzi(tekst), start=1)}

    def f(linia: str) -> Markup:
        return _linia(linia, tytuly, baza_url, statusy or {}, numery)

    bloki = []
    for blok in re.split(r"\n\s*\n", tekst.strip()):
        linie = [l for l in blok.splitlines() if l.strip()]
        if linie:
            bloki.append(_blok_html(linie, f))
    return Markup("".join(bloki))


def zrodla_odpowiedzi(tekst: str) -> dict[str, list[int]]:
    """Komplet książek i stron pod odpowiedzią."""
    wynik: dict[str, list[int]] = {}
    for m in ZNACZNIK_ZRODLA.finditer(tekst):
        for id, zapis_stron in pozycje(m[1]):
            lista = wynik.setdefault(id, [])
            lista += [n for n in strony(zapis_stron) if n not in lista]
    return {k: sorted(v) for k, v in wynik.items()}


def zaznacz(tekst_strony: str, fraza: str) -> list[dict]:
    """Strona podzielona na kawałki z zaznaczeniem liczb z odpowiedzi.

    Zaznaczamy liczby ze zdania, przy którym stał znacznik — po to redaktor
    otwiera stronę: sprawdzić wartość. To tylko podświetlenie, nie kontrola:
    brak trafienia niczego nie oznacza i nic nie blokuje."""
    liczby = sorted({l for l in re.findall(r"\d+(?:[,.]\d+)?(?:\s*[–-]\s*\d+(?:[,.]\d+)?)?", fraza)},
                    key=len, reverse=True)
    if not liczby:
        return [{"tekst": tekst_strony, "zaznacz": False}]
    # Granice liczby: „1" z „1%" nie może zaznaczyć jedynki w „10%".
    wzor = re.compile(r"(?<![\d,.])(?:" + "|".join(re.escape(l).replace(r"\ ", r"\s*") for l in liczby)
                      + r")(?![\d])")
    kawalki, ostatni = [], 0
    for m in wzor.finditer(tekst_strony):
        if m.start() > ostatni:
            kawalki.append({"tekst": tekst_strony[ostatni:m.start()], "zaznacz": False})
        kawalki.append({"tekst": m[0], "zaznacz": True})
        ostatni = m.end()
    kawalki.append({"tekst": tekst_strony[ostatni:], "zaznacz": False})
    return kawalki
