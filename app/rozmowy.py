"""Rozmowy i wiadomości w SQLite.

Pytanie zapisujemy od razu, a odpowiedź jako wiadomość „czeka" — liczy ją
proces roboczy (app/worker.py), bo pętla agenta nie mieści się w żądaniu HTTP."""

import json

from app.db import polaczenie


def nowa(tytul: str, ksiazki: list[str]) -> int:
    with polaczenie() as con:
        id = con.execute("INSERT INTO rozmowy (tytul) VALUES (?)", (tytul[:120],)).lastrowid
        _ustaw_zakres(con, id, ksiazki)
    return id


def _ustaw_zakres(con, id: int, ksiazki: list[str]) -> None:
    con.execute("DELETE FROM rozmowa_ksiazki WHERE rozmowa_id = ?", (id,))
    # Książka z dwiema kategoriami stoi w wyborze w dwóch grupach i przychodzi
    # dwa razy — bez dict.fromkeys klucz główny odrzucał zapis.
    con.executemany("INSERT INTO rozmowa_ksiazki (rozmowa_id, ksiazka) VALUES (?, ?)",
                    [(id, k) for k in dict.fromkeys(ksiazki)])


def ustaw_zakres(id: int, ksiazki: list[str]) -> None:
    with polaczenie() as con:
        _ustaw_zakres(con, id, ksiazki)


def pobierz(id: int) -> dict | None:
    with polaczenie() as con:
        r = con.execute("SELECT * FROM rozmowy WHERE id = ?", (id,)).fetchone()
        if r is None:
            return None
        rozmowa = dict(r)
        rozmowa["ksiazki"] = [w["ksiazka"] for w in con.execute(
            "SELECT ksiazka FROM rozmowa_ksiazki WHERE rozmowa_id = ? ORDER BY ksiazka", (id,))]
    return rozmowa


def lista(ile: int) -> tuple[list[dict], int]:
    """Najnowsze rozmowy i liczba starszych, których nie pokazano."""
    with polaczenie() as con:
        wiersze = [dict(r) for r in con.execute("SELECT * FROM rozmowy ORDER BY id DESC LIMIT ?", (ile,))]
        wszystkich = con.execute("SELECT COUNT(*) FROM rozmowy").fetchone()[0]
    return wiersze, max(wszystkich - ile, 0)


def zapytaj(rozmowa_id: int, pytanie: str) -> int:
    """Pytanie i pusta odpowiedź „czeka". Zakres zapisany przy odpowiedzi —
    późniejsza zmiana zakresu nie zmienia tego, z czego powstała."""
    rozmowa = pobierz(rozmowa_id)
    with polaczenie() as con:
        con.execute("INSERT INTO wiadomosci (rozmowa_id, rola, tekst) VALUES (?, 'user', ?)", (rozmowa_id, pytanie))
        return con.execute(
            "INSERT INTO wiadomosci (rozmowa_id, rola, status, ksiazki) VALUES (?, 'assistant', 'czeka', ?)",
            (rozmowa_id, json.dumps(rozmowa["ksiazki"])),
        ).lastrowid


def wiadomosci(rozmowa_id: int) -> list[dict]:
    with polaczenie() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM wiadomosci WHERE rozmowa_id = ? ORDER BY id", (rozmowa_id,))]


def wiadomosc(id: int) -> dict | None:
    with polaczenie() as con:
        r = con.execute("SELECT * FROM wiadomosci WHERE id = ?", (id,)).fetchone()
    return dict(r) if r else None


def popraw(id: int, tekst: str) -> None:
    """Ręczna poprawka; puste pole przywraca wersję z modelu."""
    with polaczenie() as con:
        con.execute("UPDATE wiadomosci SET poprawiony_tekst = ? WHERE id = ?", (tekst.strip() or None, id))


def historia(rozmowa_id: int, przed: int) -> list[dict]:
    """Wcześniejsze tury dla modelu — z poprawką redaktora, jeśli jest:
    to jego wersja obowiązuje w dalszej rozmowie."""
    tury = []
    for w in wiadomosci(rozmowa_id):
        if w["id"] >= przed or w["status"] != "gotowa":
            continue
        tury.append({"role": w["rola"], "content": w["poprawiony_tekst"] or w["tekst"]})
    return tury
