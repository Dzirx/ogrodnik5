import json

import pytest
from fastapi.testclient import TestClient

from app import config, rozmowy, spory, worker
from app.agent.petla import Slad
from app.ingest import zapis


@pytest.fixture
def panel(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ogrodnik.db")
    monkeypatch.setattr(config, "AUTH_USERNAME", "red")
    monkeypatch.setattr(config, "AUTH_PASSWORD", "haslo")
    for tytul, tekst in [("Książka A", "Rozstaw 80 x 40 cm przy palikach."), ("Książka B", "Rozstaw 70 x 50 cm.")]:
        id = zapis.wgraj_tekst(tekst, tytul, kategorie=["pomidor"])
        (zapis.katalog(id) / "ksiazka.md").write_text("# przewodnik\n")
        zapis.ustaw_status(id, "gotowa")
    from app.api.main import app
    return _klient(app, ("red", "haslo"))


def _klient(app, auth=None):
    k = TestClient(app)
    if auth:
        k.auth = auth
    return k


def test_bez_hasla_nie_wpuszcza(panel):
    assert _klient(panel.app).get("/").status_code == 401
    assert _klient(panel.app, ("red", "zle")).get("/").status_code == 401


def test_puste_haslo_w_env_nie_wpuszcza_nikogo(panel, monkeypatch):
    monkeypatch.setattr(config, "AUTH_PASSWORD", "")
    assert _klient(panel.app, ("red", "")).get("/").status_code == 503


def test_pytanie_odpowiedz_i_podglad(panel, monkeypatch):
    r = panel.post("/pytania", data={"pytanie": "Jaki rozstaw?", "ksiazki": ["ksiazka-a"]}, follow_redirects=False)
    assert r.status_code == 303
    rozmowa_id = int(r.headers["location"].rsplit("/", 1)[1])
    assert "Szukam w książkach" in panel.get(f"/rozmowy/{rozmowa_id}").text
    assert panel.get(f"/rozmowy/{rozmowa_id}/stan").json() == {"czeka": True}

    # Proces roboczy z podmienionym agentem — bez OpenAI.
    wywolania = []

    def fake(ksiazki, pytanie, historia, wiadomosc_id=None):
        wywolania.append((ksiazki, pytanie, historia))
        spory.zglos("rozstaw", "grunt", [{"ksiazka": "ksiazka-a", "strona": 1, "wartosc": "80 x 40 cm"},
                                          {"ksiazka": "ksiazka-b", "strona": 1, "wartosc": "70 x 50 cm"}], wiadomosc_id)
        return type("O", (), {"tekst": "Rozstaw 80 x 40 cm [ksiazka-a s. 1] [U1].", "slad": Slad()})

    monkeypatch.setattr(worker, "odpowiedz", fake)
    w = worker._wez("wiadomosci")
    worker._z_obsluga("wiadomosci", w, worker.odpowiedz_na)
    assert wywolania == [(["ksiazka-a"], "Jaki rozstaw?", [])]

    html = panel.get(f"/rozmowy/{rozmowa_id}").text
    assert 'href="/rozmowy/%d?podglad=ksiazka-a:1' % rozmowa_id in html
    assert "Spór U1: rozstaw" in html and "spór · U1" in html
    # Podgląd strony z zaznaczoną liczbą ze zdania.
    html = panel.get(f"/rozmowy/{rozmowa_id}?podglad=ksiazka-a:1&f=Rozstaw 80 x 40 cm").text
    assert "<mark>80</mark>" in html and "Książka A — strona 1" in html

    # Rozstrzygnięcie z ramki pod odpowiedzią.
    panel.post("/spory/1", data={"wybor": "0", "powrot": f"/rozmowy/{rozmowa_id}"})
    assert spory.pobierz(1)["przyjeta_wartosc"] == "80 x 40 cm"
    html = panel.get(f"/rozmowy/{rozmowa_id}").text
    assert "Przyjęto: <strong>80 x 40 cm</strong>" in html
    # Stara odpowiedź się nie zmienia — powstała, gdy spór był otwarty.
    assert "spór · U1" in html and "ustalenie redakcji · U1" not in html

    # Kolejne pytanie dostaje historię.
    panel.post(f"/rozmowy/{rozmowa_id}/pytania", data={"pytanie": "a późne?"})
    worker._z_obsluga("wiadomosci", worker._wez("wiadomosci"), worker.odpowiedz_na)
    assert wywolania[1][2] == [{"role": "user", "content": "Jaki rozstaw?"},
                               {"role": "assistant", "content": "Rozstaw 80 x 40 cm [ksiazka-a s. 1] [U1]."}]


def test_blad_agenta_widoczny_w_rozmowie(panel, monkeypatch):
    def zepsuty(*a, **k):
        raise RuntimeError("brak środków")
    monkeypatch.setattr(worker, "odpowiedz", zepsuty)
    r = panel.post("/pytania", data={"pytanie": "?"}, follow_redirects=False)
    worker._z_obsluga("wiadomosci", worker._wez("wiadomosci"), worker.odpowiedz_na)
    assert "Nie udało się przygotować odpowiedzi: RuntimeError: brak środków" in panel.get(r.headers["location"]).text


def test_poprawka_bez_html(panel):
    id = rozmowy.nowa("x", ["ksiazka-a"])
    w = rozmowy.zapytaj(id, "x")
    from app.db import polaczenie
    with polaczenie() as con:
        con.execute("UPDATE wiadomosci SET status='gotowa', tekst='oryginał' WHERE id=?", (w,))
    panel.post(f"/rozmowy/{id}/wiadomosci/{w}", data={"tekst": "<b>moja</b> wersja"})
    html = panel.get(f"/rozmowy/{id}").text
    assert "&lt;b&gt;moja&lt;/b&gt; wersja" in html and "poprawione ręcznie" in html


def test_biblioteka_dodaj_i_przetworz(panel):
    assert "Książka A" in panel.get("/zrodla").text
    wynik = panel.get("/zrodla?szukaj=książka a").text
    assert "Książka A" in wynik and "Książka B" not in wynik
    panel.post("/zrodla", data={"tytul": "Notatka", "kategorie": "pomidor, papryka", "tekst": "Treść."})
    meta = zapis.czytaj_meta("notatka")
    assert meta["kategorie"] == ["pomidor", "papryka"] and meta["status"] == "czeka"
    assert worker._wez("zadania")["ksiazka"] == "notatka"
    assert panel.post("/zrodla", data={"tytul": "X"}, follow_redirects=False).headers["location"].startswith("/zrodla?blad=")


def test_ksiazka_i_przewodnik(panel):
    html = panel.get("/zrodla/ksiazka-a").text
    # Przewodnik w osobnej zakładce, nie przy każdej stronie.
    assert "Rozstaw 80 x 40 cm" in html and "# przewodnik" not in html
    assert "# przewodnik" in panel.get("/zrodla/ksiazka-a?widok=przewodnik").text
    # Zapis automatyczny (fetch z nagłówkiem) dostaje JSON, nie przekierowanie.
    r = panel.post("/zrodla/ksiazka-a/przewodnik", data={"tekst": "# poprawiony"}, headers={"X-Autozapis": "1"})
    assert r.json() == {"zapisano": True}
    assert (zapis.katalog("ksiazka-a") / "ksiazka.md").read_text() == "# poprawiony\n"
    # Pusty przewodnik to raczej wypadek — nie nadpisuje.
    assert panel.post("/zrodla/ksiazka-a/przewodnik", data={"tekst": "  "}, headers={"X-Autozapis": "1"}).status_code == 400
    assert (zapis.katalog("ksiazka-a") / "ksiazka.md").read_text() == "# poprawiony\n"
    assert panel.get("/zrodla/..%2Fetc").status_code == 404


def test_ekran_sporow(panel):
    spory.zglos("pH", "", [{"ksiazka": "ksiazka-a", "strona": 1, "wartosc": "6"},
                           {"ksiazka": "ksiazka-b", "strona": 1, "wartosc": "5"}])
    assert "Do ustalenia (1)" in panel.get("/spory").text
    panel.post("/spory/1", data={"wybor": "__wlasna__", "wlasna": "5,5"})
    s = spory.pobierz(1)
    assert (s["przyjeta_wartosc"], s["skad"]) == ("5,5", "redakcja")
    panel.post("/spory/1", data={"wybor": "__odrzuc__", "powrot": "https://zly.example"})
    assert spory.pobierz(1)["status"] == "odrzucony"
