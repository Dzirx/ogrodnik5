import pytest

from app import config
from app.ingest import przewodnik, zapis


class _Odp:
    def __init__(self, tekst):
        self.model = "fake"
        self.usage = type("U", (), {"total_tokens": 0})
        self.choices = [type("C", (), {"message": type("M", (), {"content": tekst})})]


@pytest.fixture
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    prompty = []

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    prompty.append(kw["messages"][0]["content"])
                    return _Odp(f"przewodnik {len(prompty)}")

    monkeypatch.setattr(przewodnik, "_openai", Fake)
    return prompty


def test_strony_ze_znacznikami_i_pusta_strona(fake):
    id = zapis.wgraj_tekst("Ogławianie pomidorów.", "Notatka")
    przewodnik.zapisz(id)
    assert "=== STRONA 1 ===\nOgławianie pomidorów." in fake[0]
    assert (zapis.katalog(id) / "ksiazka.md").read_text() == "przewodnik 1\n"
    assert zapis.czytaj_meta(id)["status"] == "gotowa"


def test_nie_nadpisuje_przewodnika_redaktora(fake):
    id = zapis.wgraj_tekst("a", "Notatka")
    (zapis.katalog(id) / "ksiazka.md").write_text("poprawiony ręcznie")
    with pytest.raises(FileExistsError):
        przewodnik.zapisz(id)
    assert (zapis.katalog(id) / "ksiazka.md").read_text() == "poprawiony ręcznie"


def test_gruba_ksiazka_po_kawalkach(fake, monkeypatch):
    monkeypatch.setattr(config, "PRZEWODNIK_STRON_NA_KAWALEK", 2)
    id = zapis.wgraj_tekst("a", "Gruba")
    kat = zapis.katalog(id)
    for n in range(2, 6):
        (kat / "strony" / f"{n:04d}.txt").write_text(f"strona {n}")
    meta = zapis.czytaj_meta(id); meta["liczba_stron"] = 5; zapis._zapisz_meta(id, meta)
    przewodnik.zapisz(id)
    # 3 kawałki (1–2, 3–4, 5) + złożenie
    assert len(fake) == 4
    assert "strony 3–4 z 5" in fake[1] and "=== STRONA 4 ===" in fake[1]
    assert "przewodnik 1" in fake[3] and "przewodnik 3" in fake[3]
