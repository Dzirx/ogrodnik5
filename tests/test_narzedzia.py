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


def test_warianty_i_warunek_razem_z(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    id = zapis.wgraj_tekst("x", "K")
    kat = zapis.katalog(id) / "strony"
    (kat / "0001.txt").write_text("Nasiona F1 to mieszańce.")
    (kat / "0002.txt").write_text("Nasienie zbieramy z dojrzałych owoców.")
    (kat / "0003.txt").write_text("Nasiona wysiewamy w marcu.")
    meta = zapis.czytaj_meta(id); meta["liczba_stron"] = 3; zapis.zapisz_meta(id, meta)
    z = n.Zakres((id,))
    assert [t["strona"] for t in n.szukaj(z, "nasion|nasien")["trafienia"]] == [1, 2, 3]
    # Warunek „i": tylko strony z „nasion" i jednocześnie z F1 albo mieszańcami.
    assert [t["strona"] for t in n.szukaj(z, "nasion", razem_z="F1|mieszańc")["trafienia"]] == [1]
    # Pojedyncze znaki w wariantach są pomijane — „|" na końcu nie trafia wszystkiego.
    assert n.szukaj(z, "marc|")["stron_z_trafieniem"] == 1


def test_kilka_fragmentow_na_stronie(biblioteka):
    a, _ = biblioteka
    (zapis.katalog(a) / "strony" / "0001.txt").write_text("pomidor raz. " + "x " * 150 + "pomidor dwa. " + "y " * 150 + "pomidor trzy. pomidor cztery.")
    import os, time
    os.utime(zapis.katalog(a) / "meta.json", (time.time() + 10, time.time() + 10))
    t = n.szukaj(n.Zakres((a,)), "pomidor")["trafienia"][0]
    assert t["trafien_na_stronie"] == 4 and len(t["fragmenty"]) == 3
    assert "dwa" in t["fragmenty"][1]


# --- rozszerzone szukanie i lista (2026-10-04) ---

@pytest.fixture
def ksiazka_testowa(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    id = zapis.wgraj_tekst("x", "Tom")
    kat = zapis.katalog(id) / "strony"
    (kat / "0001.txt").write_text("Ogławianie robimy w sierpniu. Ogławiające się odmiany kończą wzrost.")
    (kat / "0002.txt").write_text("")
    (kat / "0003.txt").write_text("Pędy boczne usuwamy sekatorem. Ogławianie dotyczy czubka.")
    (kat / "0004.txt").write_text("Pędy boczne wyłamujemy, nie używamy noża.")
    meta = zapis.czytaj_meta(id); meta.update(liczba_stron=4, strony_tabela=[3], strony_ocr=[4])
    zapis.zapisz_meta(id, meta)
    return id, n.Zakres((id,))


def test_regex_lapie_odmiane(ksiazka_testowa):
    id, z = ksiazka_testowa
    assert [t["strona"] for t in n.szukaj(z, "ogławianie")["trafienia"]] == [1, 3]           # dosłownie: bez „ogławiające"
    w = n.szukaj(z, "ogław[^ ]*", regex=True)
    assert [t["strona"] for t in w["trafienia"]] == [1, 3] and w["trafienia"][0]["trafien_na_stronie"] == 2


def test_bez_i_razem_z(ksiazka_testowa):
    _, z = ksiazka_testowa
    assert [t["strona"] for t in n.szukaj(z, "pędy boczne", bez="sekator")["trafienia"]] == [4]
    assert [t["strona"] for t in n.szukaj(z, "ogław", razem_z="czubk")["trafienia"]] == [3]


def test_tryby_strony_i_licz(ksiazka_testowa):
    id, z = ksiazka_testowa
    assert n.szukaj(z, "ogław", tryb="strony")["ksiazki"] == [{"ksiazka": id, "stron_z_trafieniem": 2, "strony": [1, 3]}]
    assert n.szukaj(z, "ogław", tryb="licz")["ksiazki"] == [{"ksiazka": id, "stron_z_trafieniem": 2, "trafien": 3}]
    assert "trafienia" not in n.szukaj(z, "ogław", tryb="strony")           # bez tekstu — tanio
    assert "blad" in n.szukaj(z, "ogław", tryb="cokolwiek")


def test_kontekst(ksiazka_testowa):
    _, z = ksiazka_testowa
    krotki = n.szukaj(z, "sekator", kontekst=5)["trafienia"][0]["fragmenty"][0]
    assert len(krotki) < 30 and "sekator" in krotki


def test_zly_regex_daje_blad_a_nie_wyjatek(ksiazka_testowa, monkeypatch):
    import time
    _, z = ksiazka_testowa
    assert "zły wzorzec" in n.szukaj(z, "(niezamknięty", regex=True)["blad"]
    assert "za długi" in n.szukaj(z, "a" * 400, regex=True)["blad"]
    # Groźny wzorzec nie może zawiesić procesu: kończy się błędem albo wynikiem, szybko.
    monkeypatch.setattr(n, "TIMEOUT_REGEX_S", 0.3)
    id, _ = ksiazka_testowa
    (zapis.katalog(id) / "strony" / "0002.txt").write_text("a" * 45 + "!")
    import os; os.utime(zapis.katalog(id) / "meta.json", (time.time() + 10, time.time() + 10))
    start = time.time()
    w = n.szukaj(z, "(a|aa)+$", regex=True)
    assert time.time() - start < 3 and ("blad" in w or "trafienia" in w)


def test_lista_ksiazek_i_stron(ksiazka_testowa, biblioteka):
    id, z = ksiazka_testowa
    k = n.lista(z)["ksiazki"][0]
    assert (k["stron"], k["pustych"], k["strony_tabela"], k["strony_ocr"]) == (4, 1, [3], [4])
    s = n.lista(z, id)["strony"]
    assert s[0]["poczatek"].startswith("Ogławianie robimy") and s[1] == {"strona": 2, "pusta": True}
    assert s[2]["tabela"] is True and s[3]["ocr"] is True
    assert n.lista(z, id, 3, 4)["strony"][0]["strona"] == 3
    assert "blad" in n.lista(z, id, 9, 12)
    # Książka spoza zakresu jest niewidoczna dla listy tak samo jak dla szukaj.
    a, _ = biblioteka
    assert "blad" in n.lista(z, a)
