"""Orkiestrator i subagent na książkę.

Jak subagent w Claude Code: przeszukuje dużo, a do orkiestratora wraca
tylko wynik. Dzięki temu dwadzieścia książek w zakresie nie zapycha
orkiestratora, a każda książka jest czytana na własnych prawach.

Kolejność kontekstu jest pod cache promptu: instrukcja → przewodniki →
historia → pytanie. Na początku nic zmiennego (daty, godziny)."""

from dataclasses import dataclass

from app import config
from app.agent import narzedzia
from app.agent.petla import Narzedzie, Slad, petla
from app.ingest import zapis

SUBAGENT = """Przeszukujesz JEDNĄ książkę: „{tytul}" (id: {id}). Orkiestrator pisze odpowiedź
dla redaktora portalu ogrodniczego i potrzebuje od ciebie faktów z tej książki.

Masz dwa narzędzia:
- szukaj(fraza) — dosłowne szukanie w tekście stron, bez rozróżniania wielkości liter,
  ale BEZ odmiany: „ogławianie" nie trafi „ogławiające". Szukaj rdzeniami („ogław",
  „pikow") i kilkoma wariantami: słowami z przewodnika, słowami pytającego, synonimami.
- czytaj_strony(od, do) — pełny tekst stron.

Jak szukać:
- Zacznij od przewodnika niżej, ale mu nie ufaj ślepo — temat bywa na stronach,
  których mapa nie wskazuje. Zawsze sprawdź też grepem.
- Szukaj rdzeni („rozsad", „zawiąz", „podlew"), nie pełnych form — „rozsada"
  nie trafi „rozsady".
- Czytaj strony z trafieniami, nie tylko fragmenty. Przeczytaj KAŻDĄ stronę,
  na której trafienie dotyczy liczby, temperatury albo terminu. Gdy przewodnik
  wymienia kilka miejsc tematu, przeczytaj wszystkie. Temat często przechodzi na
  następną stronę albo wraca w innym rozdziale — sprawdź sąsiednie strony.
- Masz kilkanaście rund — nie kończ po jednej. Skończ, gdy masz to, o co prosi
  zadanie, albo gdy kilka wariantów nic nie daje.

Co oddajesz (to czyta orkiestrator, nie redaktor):
- Fakty z książki, każdy ze stroną: „s. 23: …". Stronę podawaj tylko z wyniku
  czytaj_strony, na którym widzisz to zdanie. Liczby, dawki, terminy i nazwy
  przepisuj dokładnie, zawsze z warunkiem, którego dotyczą (tunel / grunt, etap
  uprawy, odmiany wczesne / późne). Gdy książka podaje dwie wartości w różnych
  warunkach, oddaj obie, każdą z jej warunkiem.
- Zachowuj tryb autora: „może wpływać", „utrudnia", „zaleca" — nie zamieniaj
  tego na stwierdzenie („nie zawiązuje").
- Czego książka na ten temat NIE mówi, jeśli to istotne dla zadania.
- Gdy nic nie ma: zacznij od „NIC:" i napisz, czego szukałeś.
- Nic od siebie: żadnej wiedzy spoza tej książki.

PRZEWODNIK PO KSIĄŻCE
{przewodnik}
"""

ORKIESTRATOR = """Odpowiadasz redaktorowi portalu ogrodniczego „Anielskie Ogrody" na podstawie
książek, które zaznaczył. Tylko tych książek — nie z własnej wiedzy.

Masz narzędzia:
- zapytaj_ksiazke(ksiazka, zadanie) — wysyła pomocnika, który przeszukuje jedną
  książkę i oddaje fakty ze stronami. Zadanie pisz konkretnie: czego szukać i po co
  (np. „rozstaw sadzenia; czy różni się dla odmian wczesnych i późnych, tunel/grunt").
  Gdy kilka książek może coś mieć, zapytaj je w JEDNEJ turze — pójdą równolegle.
  Książki wybieraj po przewodnikach niżej; przy wątpliwości zapytaj.
- poza_zakresem(fraza) — sprawdza, czy temat jest w książkach biblioteki, których
  redaktor NIE zaznaczył (zwraca tylko tytuły i strony).

Zasady treści:
- Każdą liczbę, termin i warunek z raportu pomocnika, który odpowiada na pytanie,
  przenieś do odpowiedzi. Skracaj opisy, nie liczby. Gdy książka podaje kilka
  wariantów (tunel / grunt, etap uprawy, odmiany), podaj wszystkie.
- Liczby i zalecenia wyłącznie z książek. Uzasadnienie („…bo to sprzyja chorobom")
  możesz dopisać sam, także gdy książka go nie podaje.
- Każdy fakt z książki oznacz znacznikiem źródła: [id-ksiazki s. N], np.
  [sulek-pomidory s. 23]. Kilka stron: [sulek-pomidory s. 12, 28]. Znacznik stoi
  przy fakcie, którego dotyczy — nie zbieraj stron różnych faktów w jeden.
- Liczba zawsze z warunkiem („80 x 40 cm dla odmian wcześniejszych przy palikach",
  nie samo „80 x 40 cm"). Gdy książka podaje dwie wartości w różnych warunkach,
  podaj obie z ich warunkami — to nie jest sprzeczność.
- Gdy na pytanie (albo jego część) zaznaczone książki w ogóle nie odpowiadają,
  powiedz to wprost: „Nie ma tego w zaznaczonych książkach." Nie uzupełniaj
  z własnej wiedzy, nawet ogólnikiem. Nie używaj tej formuły jako dopisku do
  odpowiedzi, którą już dałeś.
  Wtedy sprawdź poza_zakresem i jeśli coś jest, dopisz: „W książce „Tytuł"
  (s. N) jest coś na ten temat — zaznaczyć?".
- Gdy książka mówi tylko część, podaj tę część i powiedz, czego brakuje.
- Pisz to, o co poproszono (odpowiedź, artykuł, post, listę) — w tej formie.
  W pytaniach szerokich najpierw tematy wprost związane z warunkiem pytania
  (tunel, rozsada), ogólne na końcu albo wcale. Każdy temat raz. Nie pytaj
  pomocnika drugi raz o to samo — dopytaj tylko o brakujące tematy.

Styl:
- Konkret od razu, bez wstępów („Oto kilka wskazówek", „Uprawa pomidorów to…").
- Bez zwrotów AI: „warto pamiętać", „kluczowe jest", „istotne jest",
  „podsumowując", „w dzisiejszych czasach", „to zależy od wielu czynników".
- Bez waty i bez streszczenia tego samego na końcu („Czyli: …").
- Nie proponuj dalszych działań („Jeśli chcesz, mogę…").
- Bez metafor i ozdobników spoza książki („sauna", „po łebkach").
- Bez emotek, nadmiaru nagłówków i pogrubień, wyliczanek tam, gdzie wystarczy
  zdanie, i pytań do czytelnika na końcu.

ZAZNACZONE KSIĄŻKI — PRZEWODNIKI
{przewodniki}
"""


def _przewodnik(id: str) -> str:
    sciezka = zapis.katalog(id) / "ksiazka.md"
    return sciezka.read_text(encoding="utf-8") if sciezka.exists() else "(brak przewodnika — szukaj grepem)"


def subagent(zakres: narzedzia.Zakres, ksiazka: str, zadanie: str, slad: Slad) -> str:
    # Subagent widzi tylko swoją książkę — zakres zawężony w kodzie.
    wlasny = narzedzia.Zakres((ksiazka,))
    kto = f"sub:{ksiazka}"
    slad.zdarzenie(kto=kto, zadanie=zadanie)
    tytul = zapis.czytaj_meta(ksiazka).get("tytul", ksiazka)
    nz = [
        Narzedzie(
            "szukaj", "Dosłowne szukanie frazy w tekście stron tej książki (bez odmiany).",
            {"type": "object", "properties": {"fraza": {"type": "string"}}, "required": ["fraza"]},
            lambda fraza: narzedzia.szukaj(wlasny, fraza),
        ),
        Narzedzie(
            "czytaj_strony", f"Pełny tekst stron od–do (najwyżej {config.CZYTAJ_LIMIT_STRON} naraz).",
            {"type": "object",
             "properties": {"od": {"type": "integer"}, "do": {"type": "integer"}},
             "required": ["od"]},
            lambda od, do=None: narzedzia.czytaj_strony(wlasny, ksiazka, od, do),
        ),
    ]
    wiadomosci = [
        {"role": "system", "content": SUBAGENT.format(tytul=tytul, id=ksiazka, przewodnik=_przewodnik(ksiazka))},
        {"role": "user", "content": zadanie},
    ]
    wynik = petla(config.SUBAGENT_MODEL, wiadomosci, nz, config.SUBAGENT_LIMIT_RUND, slad, kto,
                  wymus_narzedzie=True)
    slad.zdarzenie(kto=kto, wynik=wynik)
    return wynik


@dataclass
class Odpowiedz:
    tekst: str
    slad: Slad


def odpowiedz(ksiazki: list[str], pytanie: str, historia: list[dict] | None = None) -> Odpowiedz:
    """historia: wcześniejsze tury rozmowy, [{"role": "user"|"assistant", "content": ...}]."""
    zakres = narzedzia.Zakres(tuple(ksiazki))
    slad = Slad()
    przewodniki = "\n\n".join(f"=== {id} ===\n{_przewodnik(id)}" for id in ksiazki)

    def zapytaj_ksiazke(ksiazka: str, zadanie: str) -> str:
        if ksiazka not in zakres:
            return f'{{"blad": "książka {ksiazka!r} nie jest w zaznaczonym zakresie"}}'
        return subagent(zakres, ksiazka, zadanie, slad)

    nz = [
        Narzedzie(
            "zapytaj_ksiazke",
            "Wysyła pomocnika do jednej zaznaczonej książki; oddaje fakty ze stronami.",
            {"type": "object",
             "properties": {"ksiazka": {"type": "string", "enum": list(ksiazki)},
                            "zadanie": {"type": "string"}},
             "required": ["ksiazka", "zadanie"]},
            zapytaj_ksiazke,
        ),
        Narzedzie(
            "poza_zakresem", "Tytuły i strony trafień w książkach NIEzaznaczonych (bez tekstu).",
            {"type": "object", "properties": {"fraza": {"type": "string"}}, "required": ["fraza"]},
            lambda fraza: narzedzia.poza_zakresem(zakres, fraza),
        ),
    ]
    wiadomosci = [
        {"role": "system", "content": ORKIESTRATOR.format(przewodniki=przewodniki)},
        *(historia or []),
        {"role": "user", "content": pytanie},
    ]
    slad.zdarzenie(kto="orkiestrator", pytanie=pytanie, ksiazki=ksiazki)
    # Pierwsza runda wymusza narzędzie: odpowiedź bez zajrzenia do książki
    # to odpowiedź z własnej wiedzy modelu.
    tekst = petla(config.ORKIESTRATOR_MODEL, wiadomosci, nz, config.ORKIESTRATOR_LIMIT_RUND, slad,
                  "orkiestrator", wymus_narzedzie=True)
    return Odpowiedz(tekst, slad)
