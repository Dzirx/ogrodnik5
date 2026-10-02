"""Tekst stron PDF: warstwa tekstowa, tabele z modelu, OCR tam, gdzie treść
siedzi w obrazie. Przeniesione z ogrodnik4 (`pipeline._extract_pages`)
bez zmian w regułach — zmienił się tylko wynik: strona idzie do pliku
`strony/NNNN.txt`, a nie do podziału na akapity."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import fitz

from app.ingest.ocr import (
    MIN_PEWNOSC,
    RAZEM_STRON,
    brakujace_akapity,
    gdzie_jest_tekst,
    ma_tresc,
    odczytaj_linie_png,
    odczytaj_png,
    zrzut_strony,
)
from app.ingest.tabele import czy_tabela, odczytaj_tabele


@dataclass
class Strona:
    tekst: str
    z_ocr: bool
    tabela: bool
    # Tylko dla stron z tabelą: None = blok z modelu, tekst = przyczyna,
    # dla której została surowa warstwa.
    tabela_blad: str | None = None


def odczytaj_strony(data: bytes) -> list[Strona]:
    """Tekst kazdej strony wraz z informacja, czy trzeba go bylo odczytac
    z obrazu i czy to tabela (blok czytelnego tekstu z modelu tabel).

    Nie pytamy "czy to jest skan", tylko "gdzie na tej stronie jest tresc".
    Dzieki temu ta sama reguła obsluguje ksiazke tekstowa, skan i ksiazke
    mieszana - a klient niczego nie musi nam mowic przy wgrywaniu."""
    # TEXT_INHIBIT_SPACES jest tu konieczne, nie kosmetyczne. Bez tej flagi
    # PyMuPDF wstawia spacje wszedzie tam, gdzie w PDF-ie jest wiekszy
    # odstep miedzy literami - w ksiazce Sulka dawalo to "Poleca m podlewa
    # c pomido ry system em lin ii kroplujacyc h" w co trzecim akapicie.
    # W ogrodnik5 psuloby grep agenta: "kroplujacych" nie trafia
    # w "kroplujacyc h".
    flagi = fitz.TEXTFLAGS_TEXT | fitz.TEXT_INHIBIT_SPACES | fitz.TEXT_DEHYPHENATE

    strony: list[tuple[str, bool, bool]] = []
    do_odczytu: list[int] = []
    do_uzupelnienia: list[int] = []
    bledy_tabel: dict[int, str | None] = {}

    with fitz.open(stream=data, filetype="pdf") as document:
        for numer, strona in enumerate(document):
            warstwa = strona.get_text("text", flags=flagi)
            # Tabela z warstwy tekstowej - wykrywana z kresek w PDF-ie, nie
            # z tego, co mowi tekst. Strona bez warstwy tekstowej (skan) tu
            # nie trafia - taka idzie do OCR-u nizej, a tabel z OCR-u
            # świadomie nie obsługujemy (patrz "Czego nie robimy" w docs).
            tabela = czy_tabela(strona)
            if tabela:
                warstwa, bledy_tabel[numer] = odczytaj_tabele(strona, warstwa)
            pokrycie_tekstu, pokrycie_obrazow = gdzie_jest_tekst(strona)
            strony.append((warstwa, False, tabela))

            # Tekst pokrywa strone - nie ma czego szukac w obrazach. Ale warstwa
            # tekstowa moze byc niepelna albo nieprawdziwa (strona 26 Sulka:
            # akapit o wilkach widac, a w warstwie go nie ma), wiec strone
            # sprawdzamy jeszcze odczytem. Tabel to nie dotyczy - te czyta
            # model patrzacy na obraz, a dopisek z OCR-u tylko by je zasmiecil.
            if pokrycie_tekstu >= 0.05:
                if not tabela:
                    do_uzupelnienia.append(numer)
                continue
            # Tekstu nie ma albo jest go sladowo. Jesli jest obraz, tresc
            # siedzi wlasnie w nim.
            if pokrycie_obrazow >= 0.2:
                do_odczytu.append(numer)

        if do_odczytu:
            # Render po kolei, w watku glownym: PyMuPDF nie jest bezpieczny
            # wielowatkowo i siegniecie po dokument z czterech watkow naraz
            # zawieszalo przetwarzanie. Rownolegle idzie tylko Tesseract -
            # osobny proces, wiec czekamy wylacznie na wejscie-wyjscie.
            zrzuty = [zrzut_strony(document[n]) for n in do_odczytu]
            with ThreadPoolExecutor(max_workers=RAZEM_STRON) as pula:
                odczyty = list(pula.map(odczytaj_png, zrzuty))

            for numer, (odczyt, pewnosc) in zip(do_odczytu, odczyty):
                if pewnosc < MIN_PEWNOSC or not ma_tresc(odczyt):
                    continue  # fotografia - odczyt to szum, zostaje co bylo
                # Naglowek rozdzialu z warstwy tekstowej zostaje - jest
                # dokladny co do znaku, a OCR moze go przekrecic.
                warstwa = strony[numer][0]
                strony[numer] = (f"{warstwa}\n{odczyt}".strip(), True, strony[numer][2])

        # Po kilka stron naraz, zeby nie trzymac w pamieci setek zrzutow.
        partia = RAZEM_STRON * 2
        for start in range(0, len(do_uzupelnienia), partia):
            numery = do_uzupelnienia[start : start + partia]
            zrzuty = [zrzut_strony(document[n]) for n in numery]
            with ThreadPoolExecutor(max_workers=RAZEM_STRON) as pula:
                linie_stron = list(pula.map(odczytaj_linie_png, zrzuty))
            for numer, linie in zip(numery, linie_stron):
                warstwa = strony[numer][0]
                dopisek = brakujace_akapity(warstwa, linie)
                if dopisek:
                    # Strona ma teraz tekst z odczytu, wiec dostaje te sama
                    # gwiazdke co skan: cytat moze byc niedokladny.
                    strony[numer] = (warstwa + "\n\n" + "\n\n".join(dopisek), True, False)

    return [Strona(t, o, tab, bledy_tabel.get(n)) for n, (t, o, tab) in enumerate(strony)]
