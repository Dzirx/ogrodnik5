"""Spory między książkami: zgłasza agent, rozstrzyga redaktor.

Kod niczego tu nie ocenia — nie porównuje wartości, nie sprawdza, czy to
„naprawdę" spór. Zapisuje zgłoszenie i decyzję. Pomyłki modelu redaktor
usuwa przyciskiem „to nie jest spór" (status odrzucony; wiersz zostaje,
żeby agent go widział i nie zgłaszał drugi raz).

    python -m app.spory lista [--ksiazka ID] [--status otwarty]
    python -m app.spory pokaz 17
    python -m app.spory rozstrzygnij 17 --wartosc "100 x 80 cm" [--redakcja]
    python -m app.spory odrzuc 17
"""

import argparse

from app.db import polaczenie

STATUSY = {"otwarty": "otwarty", "rozstrzygniety": "rozstrzygnięty", "odrzucony": "odrzucony – to nie spór"}


def zglos(czego_dotyczy: str, warunek: str, opcje: list[dict], wiadomosc_id: int | None = None) -> int:
    """opcje: [{"ksiazka": id, "strona": N, "wartosc": "..."}, ...]"""
    with polaczenie() as con:
        cur = con.execute(
            "INSERT INTO spory (czego_dotyczy, warunek, wiadomosc_id) VALUES (?, ?, ?)",
            (czego_dotyczy, warunek or "", wiadomosc_id),
        )
        spor_id = cur.lastrowid
        con.executemany(
            "INSERT INTO spor_opcje (spor_id, ksiazka, strona, wartosc) VALUES (?, ?, ?, ?)",
            [(spor_id, o["ksiazka"], o.get("strona"), o["wartosc"]) for o in opcje],
        )
    return spor_id


def istniejacy(opcje: list[dict]) -> dict | None:
    """Spór o tę samą parę (książka, strona), w dowolnym statusie.

    Porównuje tylko oznaczenia źródeł, nie wartości ani opis — to
    księgowość, nie ocena treści. Bez tego agent zgłaszał ten sam spór przy
    każdym pytaniu (testy 2026-10-03: U2, U3, U4), a ustalenie U2 przepadało."""
    klucz = sorted((o["ksiazka"], o.get("strona")) for o in opcje)
    for spor in lista([o["ksiazka"] for o in opcje]):
        if sorted((o["ksiazka"], o["strona"]) for o in spor["opcje"]) == klucz:
            return spor
    return None


def _z_opcjami(con, wiersze) -> list[dict]:
    wynik = []
    for w in wiersze:
        spor = dict(w)
        spor["opcje"] = [dict(o) for o in con.execute(
            "SELECT ksiazka, strona, wartosc FROM spor_opcje WHERE spor_id = ? ORDER BY rowid", (w["id"],))]
        wynik.append(spor)
    return wynik


def pobierz(spor_id: int) -> dict | None:
    with polaczenie() as con:
        wynik = _z_opcjami(con, con.execute("SELECT * FROM spory WHERE id = ?", (spor_id,)))
    return wynik[0] if wynik else None


def lista(ksiazki: list[str] | None = None, status: str | None = None) -> list[dict]:
    """Spory dotyczące którejkolwiek z książek — po tabeli opcji, bo spór
    zawsze dotyczy dwóch książek."""
    warunki, parametry = [], []
    if ksiazki:
        warunki.append(f"id IN (SELECT spor_id FROM spor_opcje WHERE ksiazka IN ({','.join('?' * len(ksiazki))}))")
        parametry += ksiazki
    if status:
        warunki.append("status = ?")
        parametry.append(status)
    sql = "SELECT * FROM spory" + (" WHERE " + " AND ".join(warunki) if warunki else "") + " ORDER BY id"
    with polaczenie() as con:
        return _z_opcjami(con, con.execute(sql, parametry))


def rozstrzygnij(spor_id: int, wartosc: str, skad: str = "ksiazka") -> None:
    with polaczenie() as con:
        con.execute(
            "UPDATE spory SET status = 'rozstrzygniety', przyjeta_wartosc = ?, skad = ?, "
            "rozstrzygnieto = datetime('now') WHERE id = ?",
            (wartosc, skad, spor_id),
        )


def odrzuc(spor_id: int) -> None:
    with polaczenie() as con:
        con.execute(
            "UPDATE spory SET status = 'odrzucony', rozstrzygnieto = datetime('now') WHERE id = ?", (spor_id,))


def opis(spor: dict) -> str:
    """Blok dla modelu (i dla człowieka w wierszu poleceń):
    U17 [rozstrzygnięty] rozstaw odmian późnych pomidora, grunt
        przyjęto: 100 x 80 cm (ze źródła)
        sulek-pomidory s. 23: 100 x 80 cm | ksiazka-x s. 41: 70 x 50 cm"""
    linie = [f"U{spor['id']} [{STATUSY[spor['status']]}] {spor['czego_dotyczy']}"
             + (f", {spor['warunek']}" if spor["warunek"] else "")]
    if spor["status"] == "rozstrzygniety":
        zrodlo = "ustalenie redakcji" if spor["skad"] == "redakcja" else "ze źródła"
        linie.append(f"    przyjęto: {spor['przyjeta_wartosc']} ({zrodlo})")
    if spor["status"] != "odrzucony":
        linie.append("    " + " | ".join(
            f"{o['ksiazka']} s. {o['strona']}: {o['wartosc']}" for o in spor["opcje"]))
    return "\n".join(linie)


def blok(ksiazki: list[str]) -> str:
    spory = lista(ksiazki)
    return "\n".join(opis(s) for s in spory) if spory else "(brak sporów)"


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.spory")
    sub = p.add_subparsers(dest="polecenie", required=True)
    l = sub.add_parser("lista")
    l.add_argument("--ksiazka", action="append")
    l.add_argument("--status", choices=list(STATUSY))
    sub.add_parser("pokaz").add_argument("id", type=int)
    r = sub.add_parser("rozstrzygnij")
    r.add_argument("id", type=int)
    r.add_argument("--wartosc", required=True)
    r.add_argument("--redakcja", action="store_true", help="własna wartość redakcji, nie z książki")
    sub.add_parser("odrzuc").add_argument("id", type=int)
    a = p.parse_args()

    if a.polecenie == "lista":
        print("\n".join(opis(s) for s in lista(a.ksiazka, a.status)) or "(brak sporów)")
    elif a.polecenie == "pokaz":
        spor = pobierz(a.id)
        print(opis(spor) if spor else f"nie ma sporu U{a.id}")
    elif a.polecenie == "rozstrzygnij":
        rozstrzygnij(a.id, a.wartosc, "redakcja" if a.redakcja else "ksiazka")
        print(opis(pobierz(a.id)))
    elif a.polecenie == "odrzuc":
        odrzuc(a.id)
        print(opis(pobierz(a.id)))


if __name__ == "__main__":
    main()
