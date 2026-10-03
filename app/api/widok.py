"""Odpowiedź modelu jako HTML: akapity, listy i znaczniki źródeł jako linki.

Tekst z bazy najpierw idzie przez escape, dopiero potem dokładamy znaczniki —
surowego HTML-a z modelu ani z poprawki redaktora nigdy nie wstawiamy."""

import re
from urllib.parse import quote

from markupsafe import Markup, escape

# [sulek-pomidory s. 12, 28] albo [sulek-pomidory s. 13–14]
ZNACZNIK_ZRODLA = re.compile(r"\[([a-z0-9][a-z0-9-]*) s\. ([\d][\d,\s–-]*)\]")
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


def _linia(tekst: str, tytuly: dict[str, str], baza_url: str, statusy: dict[int, str]) -> Markup:
    # Zdanie bez znaczników idzie w linku do podglądu — po nim podgląd
    # zaznacza na stronie liczby, które redaktor chce sprawdzić.
    fraza = quote(ZNACZNIK_SPORU.sub("", ZNACZNIK_ZRODLA.sub("", tekst))[:200])
    html = str(escape(tekst))
    html = POGRUBIENIE.sub(r"<strong>\1</strong>", html)

    def zrodlo(m: re.Match) -> str:
        id = m[1]
        tytul = escape(tytuly.get(id, id))
        linki = ", ".join(
            f'<a href="{baza_url}?podglad={id}:{n}&amp;f={fraza}" title="{tytul}, strona {n}">{n}</a>'
            for n in strony(m[2])
        )
        return f'<span class="znacznik" title="{tytul}">{tytul} s. {linki}</span>'

    def spor(m: re.Match) -> str:
        # Etykieta po bieżącym statusie: „ustalenie redakcji" tylko przy
        # rozstrzygniętym — przy otwartym myliłoby, że ktoś już zdecydował.
        status = statusy.get(int(m[1]), "otwarty")
        return (f'<a class="spor-znacznik {status}" href="/spory#U{m[1]}" '
                f'title="Spór U{m[1]} — obie wartości i decyzja redakcji">'
                f'{ETYKIETY_SPORU.get(status, "spór")} · U{m[1]}</a>')

    html = ZNACZNIK_ZRODLA.sub(zrodlo, html)
    html = ZNACZNIK_SPORU.sub(spor, html)
    return Markup(html)


def odpowiedz_html(tekst: str, tytuly: dict[str, str], baza_url: str = "",
                   statusy: dict[int, str] | None = None) -> Markup:
    """Akapity po pustej linii, linie „- " jako lista. Więcej Markdownu model
    nie powinien pisać (styl: bez nagłówków i ozdobników)."""
    bloki = []
    for blok in re.split(r"\n\s*\n", tekst.strip()):
        linie = [l for l in blok.splitlines() if l.strip()]
        if linie and all(re.match(r"\s*[-•*]\s+", l) for l in linie):
            pozycje = "".join(f"<li>{_linia(re.sub(r'^\s*[-•*]\s+', '', l), tytuly, baza_url, statusy or {})}</li>" for l in linie)
            bloki.append(f"<ul>{pozycje}</ul>")
        elif linie:
            bloki.append("<p>" + "<br>".join(str(_linia(l, tytuly, baza_url, statusy or {})) for l in linie) + "</p>")
    return Markup("".join(bloki))


def zrodla_odpowiedzi(tekst: str) -> dict[str, list[int]]:
    """Komplet książek i stron pod odpowiedzią."""
    wynik: dict[str, list[int]] = {}
    for m in ZNACZNIK_ZRODLA.finditer(tekst):
        lista = wynik.setdefault(m[1], [])
        lista += [s for s in strony(m[2]) if s not in lista]
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
