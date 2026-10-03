import pytest

from app import config
from app.agent import narzedzia as n
from app.ingest import zapis

SULEK = config.ZRODLA_DIR / "sulek-pomidory"


@pytest.fixture
def biblioteka(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    a = zapis.wgraj_tekst("Ogławianie robimy w sierpniu.\nSaletry\nwapniowej nie żałujemy.", "Książka A")
    b = zapis.wgraj_tekst("Ogławianie pomidorów w tunelu.", "Książka B")
    return a, b


def test_szukaj_bez_wielkosci_liter_i_przez_lamanie_linii(biblioteka):
    a, b = biblioteka
    z = n.Zakres((a,))
    w = n.szukaj(z, "OGŁAWIANIE")
    assert [(t["ksiazka"], t["strona"]) for t in w["trafienia"]] == [(a, 1)]
    assert n.szukaj(z, "saletry wapniowej")["stron_z_trafieniem"] == 1


def test_ksiazka_spoza_zakresu_niewidoczna(biblioteka):
    a, b = biblioteka
    z = n.Zakres((a,))
    assert "blad" in n.szukaj(z, "ogławianie", ksiazki=[b])
    assert "blad" in n.czytaj_strony(z, b, 1)
    assert "blad" in n.przewodnik(z, b)


def test_poza_zakresem_bez_tekstu(biblioteka):
    a, b = biblioteka
    w = n.poza_zakresem(n.Zakres((a,)), "ogławianie")
    assert w["poza_zakresem"] == [{"ksiazka": b, "tytul": "Książka B", "strony": [1], "stron_z_trafieniem": 1}]


def test_limit_trafien(biblioteka, monkeypatch):
    a, b = biblioteka
    monkeypatch.setattr(config, "SZUKAJ_LIMIT_TRAFIEN", 1)
    w = n.szukaj(n.Zakres((a, b)), "ogławianie")
    assert len(w["trafienia"]) == 1 and w["stron_z_trafieniem"] == 2 and "uwaga" in w


def test_czytaj_poza_ksiazka(biblioteka):
    a, _ = biblioteka
    assert "blad" in n.czytaj_strony(n.Zakres((a,)), a, 2)


def test_cache_unieważnia_przetworzenie(biblioteka):
    a, _ = biblioteka
    z = n.Zakres((a,))
    assert n.szukaj(z, "sierpniu")["stron_z_trafieniem"] == 1
    (zapis.katalog(a) / "original.txt").write_text("Coś zupełnie innego.")
    import os, time
    zapis.przetworz(a)
    meta = zapis.katalog(a) / "meta.json"
    os.utime(meta, (time.time() + 5, time.time() + 5))
    assert n.szukaj(z, "sierpniu")["stron_z_trafieniem"] == 0


# --- na prawdziwym Sułku (data/ jest poza repozytorium) ---

sulek = pytest.mark.skipif(not SULEK.exists(), reason="brak data/zrodla/sulek-pomidory")


@sulek
def test_sulek_oglawianie():
    z = n.Zakres(("sulek-pomidory",))
    dokladnie = {t["strona"] for t in n.szukaj(z, "ogławianie")["trafienia"]}
    rdzen = {t["strona"] for t in n.szukaj(z, "ogław")["trafienia"]}
    assert 28 in dokladnie
    # s. 12 ma „ogławiające" — trafia dopiero rdzeń; po to przewodnik je podaje.
    assert {12, 28} <= rdzen


@sulek
def test_sulek_limit_stron(monkeypatch):
    monkeypatch.setattr(config, "CZYTAJ_LIMIT_STRON", 3)
    w = n.czytaj_strony(n.Zakres(("sulek-pomidory",)), "sulek-pomidory", 10, 20)
    assert [s["strona"] for s in w["strony"]] == [10, 11, 12]
    assert "od strony 13" in w["uwaga"]


@sulek
def test_sulek_pusta_strona():
    w = n.czytaj_strony(n.Zakres(("sulek-pomidory",)), "sulek-pomidory", 37)
    assert "bez tekstu" in w["strony"][0]["tekst"]
