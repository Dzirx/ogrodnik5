import pytest

from app import config, spory


@pytest.fixture(autouse=True)
def baza(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ogrodnik.db")


def _zglos():
    return spory.zglos("rozstaw odmian późnych", "grunt", [
        {"ksiazka": "a", "strona": 23, "wartosc": "100 x 80 cm"},
        {"ksiazka": "b", "strona": 41, "wartosc": "70 x 50 cm"},
    ])


def test_zgloszenie_i_spory_ksiazki():
    id = _zglos()
    spory.zglos("pH", "", [{"ksiazka": "c", "strona": 1, "wartosc": "6"}, {"ksiazka": "d", "strona": 2, "wartosc": "5"}])
    assert [s["id"] for s in spory.lista(["b"])] == [id]
    assert spory.pobierz(id)["status"] == "otwarty"
    assert "U1 [otwarty] rozstaw odmian późnych, grunt" in spory.blok(["a"])
    assert "b s. 41: 70 x 50 cm" in spory.blok(["a"])


def test_rozstrzygniecie_i_odrzucenie():
    id = _zglos()
    spory.rozstrzygnij(id, "100 x 80 cm")
    assert "przyjęto: 100 x 80 cm (ze źródła)" in spory.blok(["a"])
    spory.rozstrzygnij(id, "90 x 60 cm", "redakcja")
    assert "(ustalenie redakcji)" in spory.blok(["a"])
    spory.odrzuc(id)
    # Odrzucony zostaje widoczny, bez wartości — agent ma go nie zgłaszać ponownie.
    assert spory.blok(["a"]) == "U1 [odrzucony – to nie spór] rozstaw odmian późnych, grunt"


def test_brak_sporow():
    assert spory.blok(["a"]) == "(brak sporów)"


def test_istniejacy_po_parze_zrodel():
    id = _zglos()
    # Ta sama para książek i stron, inna kolejność i inna wartość — ten sam spór.
    assert spory.istniejacy([{"ksiazka": "b", "strona": 41, "wartosc": "x"},
                             {"ksiazka": "a", "strona": 23, "wartosc": "y"}])["id"] == id
    assert spory.istniejacy([{"ksiazka": "a", "strona": 24, "wartosc": "x"},
                             {"ksiazka": "b", "strona": 41, "wartosc": "y"}]) is None
