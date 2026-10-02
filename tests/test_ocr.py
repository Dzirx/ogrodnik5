"""Strony, na których tekst siedzi w obrazie.

Klient przecina grzbiety książek i przepuszcza je przez skaner - mówił to
wprost na spotkaniu. Taka książka wchodziła jako "gotowa" z zerową liczbą
akapitów, bez słowa ostrzeżenia.
"""

from app.ingest.ocr import MIN_PEWNOSC, MIN_PEWNOSC_SLOWA, ma_tresc


def test_prog_rozdziela_obraz_od_tekstu():
    """Zmierzone na książkach klienta: fotografia krzewów 31%, zdjęcie owocu 45%,
    okładka ze zdjęciem i nazwą instytucji 70%, strona tytułowa 90,6%, stopka
    z adresem 92,6%. Próg musi leżeć między okładką a stroną tytułową."""
    assert MIN_PEWNOSC > 70, "okładka ze zdjęciem przechodziła przy 65"
    assert MIN_PEWNOSC < 90, "strona tytułowa dała 90,6% i ma przechodzić"


def test_szum_z_fotografii_nie_ma_tresci():
    """Zdjęcie krzewów wyprodukowało 168 "słów" z liści i cieni, ale to
    'Rd"', 'AKRZE', '„ZEE'. Sam licznik słów by nie wystarczył - dlatego
    liczy się i treść, i pewność odczytu."""
    assert not ma_tresc('Rd" AKRZE ZEE WBELNS AA ji PDPZ')
    assert not ma_tresc("")


def test_prawdziwy_akapit_ma_tresc():
    assert ma_tresc(
        "Po wysadzeniu rozsady do gruntu należy zadbać o odpowiednie warunki uprawy, "
        "w tym nawodnienie, wentylację i temperaturę otoczenia roślin."
    )


def test_prog_slowa_nizszy_niz_prog_strony():
    """Strona czytelna jako całość może mieć w środku śmieci - na okładce
    nazwa instytucji wyszła poprawnie, a szum wokół niej nie."""
    assert MIN_PEWNOSC_SLOWA < MIN_PEWNOSC


# Strona 26 książki Sułka: akapit o wilkach widać na stronie, ale warstwa
# tekstowa PDF-a ma w tym miejscu podpis spod zdjęcia.
_WARSTWA_S26 = (
    "Wydaje się, że instrukcja obrywania tych niechcianych przyrostów jest oczywista, "
    "a jednak często sprawia wiele problemów i stawia przed trudnym wyborem, co usunąć a co nie.\n"
    "KWIATOSTAN\nZ pędu głównego\n"
    "zawsz e wyras ta kwi atostan , pęd d ziki to mło dy stozek, kw iatos tan będz ie wiąza ł s ię n a czu bku.\n"
    "JAK ROZPOZNAĆ\nPĘD BOCZNY?"
)

_ODCZYT_S26 = [
    ((1, 1), "Pędy boczne (tzw. wilki) należy usunąć jak najszybciej, zanim"),
    ((1, 1), "osiągną długość 10 cm. Robi się to, ponieważ konkurują one"),
    ((1, 1), "niepotrzebnie z pozostałymi liśćmi i owocami o wodę, światło"),
    ((1, 2), "Wydaje się, że instrukcja obrywania tych niechcianych przyrostów jest"),
    ((1, 2), "oczywista, a jednak często sprawia wiele problemów i stawia przed"),
    ((2, 1), "KWIATOSTAN"),
]


def test_dopisuje_akapit_ktorego_nie_ma_w_warstwie():
    from app.ingest.ocr import brakujace_akapity

    wynik = brakujace_akapity(_WARSTWA_S26, _ODCZYT_S26)
    assert len(wynik) == 1
    assert "wilki" in wynik[0] and "osiągną długość 10 cm" in wynik[0]


def test_nie_dubluje_tego_co_warstwa_juz_ma():
    """Zdanie 'Wydaje się...' stoi w warstwie, choć z rozciętymi słowami
    w innym akapicie - nie wolno go dopisać drugi raz."""
    from app.ingest.ocr import brakujace_akapity

    wynik = " ".join(brakujace_akapity(_WARSTWA_S26, _ODCZYT_S26))
    assert "instrukcja obrywania" not in wynik


def test_szum_z_fotografii_nie_jest_dopisywany():
    from app.ingest.ocr import brakujace_akapity

    szum = [((1, 1), "Rd AKRZE ZEE"), ((1, 1), "WBELNS PDPZ")]
    assert brakujace_akapity(_WARSTWA_S26, szum) == []
