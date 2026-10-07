import pytest
from fastapi.testclient import TestClient

from app import config, prompty
from app.agent import agent


@pytest.fixture
def baza(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ogrodnik.db")


@pytest.fixture
def panel(baza, monkeypatch):
    monkeypatch.setattr(config, "AUTH_USERNAME", "red")
    monkeypatch.setattr(config, "AUTH_PASSWORD", "haslo")
    from app.api.main import app
    k = TestClient(app)
    k.auth = ("red", "haslo")
    return k


def test_bez_zapisu_obowiazuje_domyslny(baza):
    assert prompty.aktualny("k", "DOMYŚLNY") == ("DOMYŚLNY", "domyslny")


def test_zapis_przywrocenie_i_historia(baza):
    prompty.zapisz("k", "  Pierwszy\r\nprompt  ")
    assert prompty.aktualny("k", "D") == ("Pierwszy\nprompt", "wlasny")
    prompty.zapisz("k", "Pierwszy\nprompt")        # to samo — bez dublowania w historii
    prompty.zapisz("k", "Drugi")
    prompty.przywroc_domyslny("k")
    assert prompty.aktualny("k", "D") == ("D", "domyslny")
    h = prompty.historia("k")
    assert [x["tekst"] for x in h] == [None, "Drugi", "Pierwszy\nprompt"]      # od najnowszego
    assert prompty.aktualny("inny-klucz", "X")[1] == "domyslny"                # klucze są osobne
    assert prompty.wersja("k", h[2]["id"])["tekst"] == "Pierwszy\nprompt"


def test_pusty_i_za_dlugi_prompt_nie_zapisuje_sie(baza):
    with pytest.raises(ValueError):
        prompty.zapisz("k", "   \n ")
    with pytest.raises(ValueError):
        prompty.zapisz("k", "x" * (prompty.MAKS_ZNAKOW + 1))
    assert prompty.historia("k") == []


def test_strona_w_panelu_pokazuje_zapisuje_i_przywraca(panel):
    r = panel.get("/prompt-pisarza")
    assert r.status_code == 200 and "domyślny (z kodu)" in r.text
    assert "Piszesz odpowiedź dla redaktora" in r.text            # domyślny tekst w polu

    r = panel.post("/prompt-pisarza", data={"tekst": "Mój <b>prompt</b>"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/prompt-pisarza?zapisano=1"
    r = panel.get("/prompt-pisarza?zapisano=1")
    assert "własny" in r.text and "Zapisano." in r.text
    assert "Mój &lt;b&gt;prompt&lt;/b&gt;" in r.text                 # escapowany, nie HTML

    # Pusty zapis nie kasuje promptu — wraca z komunikatem.
    r = panel.post("/prompt-pisarza", data={"tekst": " "}, follow_redirects=False)
    assert "blad=" in r.headers["location"]
    assert prompty.aktualny(prompty.PISARZ_STRONY, "D")[0] == "Mój <b>prompt</b>"

    # Wczytanie starszej wersji tylko wypełnia pole.
    panel.post("/prompt-pisarza/domyslny", follow_redirects=False)
    assert prompty.aktualny(prompty.PISARZ_STRONY, "D") == ("D", "domyslny")
    stara = next(h for h in prompty.historia(prompty.PISARZ_STRONY) if h["tekst"])
    assert "Mój &lt;b&gt;prompt&lt;/b&gt;" in panel.get(f"/prompt-pisarza?wersja={stara['id']}").text
    assert prompty.aktualny(prompty.PISARZ_STRONY, "D")[1] == "domyslny"      # bez zapisu


def test_panel_wymaga_loginu(panel):
    from app.api.main import app
    assert TestClient(app).get("/prompt-pisarza").status_code == 401
    assert TestClient(app).post("/prompt-pisarza", data={"tekst": "x"}).status_code == 401
