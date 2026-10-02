import fitz
import pytest

from app import config
from app.ingest import zapis


@pytest.fixture(autouse=True)
def osobny_katalog(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")


def test_slug_polskie_litery():
    assert zapis.slug("Sułek — pomidory") == "sulek-pomidory"
    assert zapis.slug("Żółć gęśla") == "zolc-gesla"


def test_tekst_to_jedna_strona():
    id = zapis.wgraj_tekst("Pomidor lubi ciepło.", "Notatka", kategorie=["pomidor"])
    kat = zapis.katalog(id)
    assert (kat / "original.txt").exists()
    assert (kat / "strony" / "0001.txt").read_text(encoding="utf-8") == "Pomidor lubi ciepło.\n"
    meta = zapis.czytaj_meta(id)
    assert meta["liczba_stron"] == 1 and meta["rodzaj"] == "tekst" and meta["kategorie"] == ["pomidor"]


def test_kolizja_id():
    assert zapis.wgraj_tekst("a", "Notatka") == "notatka"
    assert zapis.wgraj_tekst("b", "Notatka") == "notatka-2"


def test_pdf_pusta_strona_ma_plik(tmp_path):
    pdf = tmp_path / "k.pdf"
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Strona pierwsza")
    doc.new_page()  # bez treści
    doc.new_page().insert_text((72, 72), "Strona trzecia")
    doc.save(pdf)
    id = zapis.wgraj_pdf(pdf, "Próba")
    strony = sorted((zapis.katalog(id) / "strony").iterdir())
    assert [s.name for s in strony] == ["0001.txt", "0002.txt", "0003.txt"]
    assert strony[1].read_text() == ""
    assert "trzecia" in strony[2].read_text()


def test_ponowne_przetworzenie_nie_rusza_oryginalu_ani_przewodnika():
    id = zapis.wgraj_tekst("stary", "Notatka")
    kat = zapis.katalog(id)
    (kat / "ksiazka.md").write_text("przewodnik redaktora")
    (kat / "strony" / "0099.txt").write_text("śmieć")
    meta = zapis.przetworz(id)
    assert (kat / "original.txt").read_text() == "stary"
    assert (kat / "ksiazka.md").read_text() == "przewodnik redaktora"
    assert not (kat / "strony" / "0099.txt").exists()
    assert meta["status"] == "gotowa"


def test_nieudane_wgranie_nie_zostawia_katalogu(tmp_path):
    with pytest.raises(FileNotFoundError):
        zapis.wgraj_pdf(tmp_path / "nie-ma.pdf", "Próba")
    assert not zapis.katalog("proba").exists()


def test_meta_zapisuje_wynik_odczytu_tabel(monkeypatch):
    from app.ingest import strony as strony_mod

    monkeypatch.setattr(zapis, "odczytaj_strony", lambda _: [
        strony_mod.Strona("blok", False, True, None),
        strony_mod.Strona("proza", False, False),
        strony_mod.Strona("surowa warstwa", False, True, "RateLimitError: brak środków"),
    ])
    kat = zapis.katalog("ksiazka")
    kat.mkdir(parents=True)
    (kat / "original.pdf").write_bytes(b"")
    meta = zapis.przetworz("ksiazka")
    assert meta["odczyt_tabel"] == {"1": "ok", "3": "RateLimitError: brak środków"}
