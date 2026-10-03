"""Proces roboczy: odpowiedzi i wgrywanie w tle, bez Redisa i RQ.

    python -m app.worker

Bierze z SQLite wiadomości „czeka" i zadania „czeka". Kilka naraz w wątkach:
odpowiedź to głównie czekanie na OpenAI, a redaktor nie powinien stać
w kolejce za cudzym artykułem."""

import json
import logging
import time
import traceback
from concurrent.futures import ThreadPoolExecutor

from app import rozmowy
from app.agent.agent import odpowiedz
from app.db import polaczenie
from app.ingest import przewodnik, zapis

log = logging.getLogger("worker")
WATKOW = 3
PRZERWA_S = 1.0


def _wez(tabela: str) -> dict | None:
    """Jedno „czeka" → „w_toku"; UPDATE z warunkiem na status, żeby dwa wątki
    nie wzięły tego samego."""
    with polaczenie() as con:
        r = con.execute(f"SELECT * FROM {tabela} WHERE status = 'czeka' ORDER BY id LIMIT 1").fetchone()
        if r is None:
            return None
        if con.execute(f"UPDATE {tabela} SET status = 'w_toku' WHERE id = ? AND status = 'czeka'",
                       (r["id"],)).rowcount != 1:
            return None
    return dict(r)


def odpowiedz_na(w: dict) -> None:
    pytanie = rozmowy.historia(w["rozmowa_id"], w["id"])
    ostatnie = pytanie.pop() if pytanie and pytanie[-1]["role"] == "user" else None
    if ostatnie is None:
        raise RuntimeError("brak pytania przed odpowiedzią")
    wynik = odpowiedz(json.loads(w["ksiazki"] or "[]"), ostatnie["content"], pytanie, wiadomosc_id=w["id"])
    with polaczenie() as con:
        con.execute("UPDATE wiadomosci SET tekst = ?, status = 'gotowa', slad = ? WHERE id = ?",
                    (wynik.tekst, json.dumps(wynik.slad.do_json(), ensure_ascii=False), w["id"]))


def wykonaj(z: dict) -> None:
    if z["rodzaj"] == "przetworz":
        zapis.ustaw_status(z["ksiazka"], "przetwarzanie")
        zapis.przetworz(z["ksiazka"])
        # Nowa książka dostaje przewodnik od razu; istniejącego (mógł go
        # poprawić redaktor) ponowne przetworzenie nie rusza.
        if not (zapis.katalog(z["ksiazka"]) / "ksiazka.md").exists():
            przewodnik.zapisz(z["ksiazka"])
    elif z["rodzaj"] == "przewodnik":
        zapis.ustaw_status(z["ksiazka"], "przetwarzanie")
        przewodnik.zapisz(z["ksiazka"], nadpisz=True)
    zapis.ustaw_status(z["ksiazka"], "gotowa")


def _z_obsluga(tabela: str, rekord: dict, praca) -> None:
    try:
        praca(rekord)
        if tabela == "zadania":
            with polaczenie() as con:
                con.execute("UPDATE zadania SET status = 'gotowe' WHERE id = ?", (rekord["id"],))
    except Exception as e:
        log.error("%s %s: %s", tabela, rekord["id"], traceback.format_exc())
        blad = f"{type(e).__name__}: {e}"[:500]
        with polaczenie() as con:
            con.execute(f"UPDATE {tabela} SET status = 'blad', blad = ? WHERE id = ?", (blad, rekord["id"]))
        if tabela == "zadania":
            zapis.ustaw_status(rekord["ksiazka"], "blad", blad)


def zlec(rodzaj: str, ksiazka: str) -> None:
    with polaczenie() as con:
        con.execute("INSERT INTO zadania (rodzaj, ksiazka) VALUES (?, ?)", (rodzaj, ksiazka))
    zapis.ustaw_status(ksiazka, "czeka")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    # Po przerwaniu (restart, błąd) „w_toku" wisiałoby wiecznie — wracają do kolejki.
    with polaczenie() as con:
        con.execute("UPDATE wiadomosci SET status = 'czeka' WHERE status = 'w_toku'")
        con.execute("UPDATE zadania SET status = 'czeka' WHERE status = 'w_toku'")
    log.info("start, %d wątki", WATKOW)
    with ThreadPoolExecutor(max_workers=WATKOW) as pula:
        zajete: set = set()
        while True:
            zajete = {f for f in zajete if not f.done()}
            if len(zajete) < WATKOW:
                if w := _wez("wiadomosci"):
                    zajete.add(pula.submit(_z_obsluga, "wiadomosci", w, odpowiedz_na))
                    continue
                if z := _wez("zadania"):
                    zajete.add(pula.submit(_z_obsluga, "zadania", z, wykonaj))
                    continue
            time.sleep(PRZERWA_S)


if __name__ == "__main__":
    main()
