"""Prompty edytowane w panelu (na razie: system prompt pisarza).

Domyślny tekst siedzi w kodzie (agent.py). Redaktor może go zmienić w panelu; zmiana
trafia do SQLite jako nowy wiersz (historia zostaje), a agent czyta bieżący prompt
przy każdej odpowiedzi — działa od następnego pytania, bez restartu. Kod nie ocenia
treści promptu: sprawdza tylko, że nie jest pusty ani absurdalnie długi."""

from app import db

PISARZ_STRONY = "pisarz_strony"
MAKS_ZNAKOW = 30000


def aktualny(klucz: str, domyslny: str) -> tuple[str, str]:
    """(tekst, skąd): skąd to „domyslny" albo „wlasny" — do śladu odpowiedzi."""
    with db.polaczenie() as con:
        w = con.execute("SELECT tekst FROM prompty WHERE klucz = ? ORDER BY id DESC LIMIT 1", (klucz,)).fetchone()
    if w is None or w["tekst"] is None:
        return domyslny, "domyslny"
    return w["tekst"], "wlasny"


def zapisz(klucz: str, tekst: str) -> None:
    tekst = tekst.replace("\r\n", "\n").strip()
    if not tekst:
        raise ValueError("Prompt nie może być pusty.")
    if len(tekst) > MAKS_ZNAKOW:
        raise ValueError(f"Prompt jest za długi (najwyżej {MAKS_ZNAKOW} znaków).")
    with db.polaczenie() as con:
        ostatni = con.execute("SELECT tekst FROM prompty WHERE klucz = ? ORDER BY id DESC LIMIT 1", (klucz,)).fetchone()
        if ostatni is not None and ostatni["tekst"] == tekst:
            return   # nic się nie zmieniło — bez dublowania wpisu w historii
        con.execute("INSERT INTO prompty (klucz, tekst) VALUES (?, ?)", (klucz, tekst))


def przywroc_domyslny(klucz: str) -> None:
    with db.polaczenie() as con:
        con.execute("INSERT INTO prompty (klucz, tekst) VALUES (?, NULL)", (klucz,))


def historia(klucz: str, limit: int = 10) -> list[dict]:
    """Ostatnie zapisy, od najnowszego; tekst None = przywrócenie domyślnego."""
    with db.polaczenie() as con:
        return [dict(r) for r in con.execute(
            "SELECT id, tekst, zapisano FROM prompty WHERE klucz = ? ORDER BY id DESC LIMIT ?", (klucz, limit))]


def wersja(klucz: str, id: int) -> dict | None:
    with db.polaczenie() as con:
        w = con.execute("SELECT id, tekst, zapisano FROM prompty WHERE klucz = ? AND id = ?", (klucz, id)).fetchone()
    return dict(w) if w else None
