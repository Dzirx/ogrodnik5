"""Orkiestrator i subagent na książkę.

Jak subagent w Claude Code: przeszukuje dużo, a do orkiestratora wraca
tylko wynik. Dzięki temu dwadzieścia książek w zakresie nie zapycha
orkiestratora, a każda książka jest czytana na własnych prawach.

Kolejność kontekstu jest pod cache promptu: instrukcja → przewodniki →
historia → pytanie. Na początku nic zmiennego (daty, godziny)."""

from dataclasses import dataclass

from app import config, spory
from app.agent import narzedzia
from app.agent import petla as _petla
from app.agent.petla import Narzedzie, Slad, _wykonaj, petla
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
- Gdy temat na czytanej stronie urywa się albo zaczyna, przeczytaj też stronę
  następną albo poprzednią.
- Trafienie z szukaj to nie odczyt: każdą stronę, którą podajesz, przeczytaj
  przez czytaj_strony. Przeczytaj też trafienia z innych rozdziałów (choroby,
  ochrona, nawożenie) — tam bywają zalecenia praktyczne do tego tematu.
- Masz kilkanaście rund — nie kończ po jednej. Skończ, gdy masz to, o co prosi
  zadanie, albo gdy kilka wariantów nic nie daje.

Co oddajesz (to czyta orkiestrator, nie redaktor), w dwóch częściach:

ODPOWIEDŹ WPROST
- s. N: fakt, który odpowiada na zadanie (liczba, termin, warunek, zalecenie,
  opis „jak wygląda"). Jedna linia = jedna strona; bez linii zbiorczych
  „s. 22–26: …".

TŁO
- s. N: to, co pomaga zrozumieć, ale na zadanie wprost nie odpowiada.

Zasady raportu:
- Każdy fakt ze stroną. Stronę podawaj tylko z wyniku
  czytaj_strony, na którym widzisz to zdanie. Liczby, dawki, terminy i nazwy
  przepisuj dokładnie, zawsze z warunkiem, którego dotyczą (tunel / grunt, etap
  uprawy, odmiany wczesne / późne). Gdy książka podaje dwie wartości w różnych
  warunkach, oddaj obie, każdą z jej warunkiem.
- Zachowuj tryb autora: „może wpływać", „utrudnia", „zaleca" — nie zamieniaj
  tego na stwierdzenie („nie zawiązuje").
- Zasad ogólnych rozdziału (np. „monitoring", „tablice lepowe") nie przypisuj
  pierwszemu tematowi pod nimi.
- Czego książka NIE mówi — tylko o tym, o co prosi zadanie.
- Raport zwykłym tekstem: bez pogrubień, nagłówków, wstępu i propozycji
  dalszych działań.
- Gdy nic nie ma: zacznij od „NIC:" i napisz, czego szukałeś.
- Nic od siebie: żadnej wiedzy spoza tej książki.

PRZEWODNIK PO KSIĄŻCE
{przewodnik}

SPORY TEJ KSIĄŻKI
Spory z innymi książkami, które zgłoszono wcześniej (U-numer, status):
- rozstrzygnięty — gdy zadanie dotyczy tej samej rzeczy w TYM SAMYM warunku
  (grunt / tunel, etap uprawy, odmiany), oddaj przyjętą wartość z numerem:
  „s. 23: 100 x 80 cm — ustalenie U17". Ustalenie jest ważniejsze niż książka.
  Inny warunek — ustalenie nie dotyczy, oddaj wartość z książki bez numeru.
- otwarty — oddaj wartość z książki z dopiskiem „spór U22 nierozstrzygnięty".
- odrzucony — to nie spór; oddaj zwykłą wartość z książki.
{spory}
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
  redaktor NIE zaznaczył (zwraca tylko tytuły i strony). Fraza działa jak grep:
  rdzeń jednego słowa („wysiew", „przędziork"), nie zdanie.

Zasady treści:
- Raport pomocnika ma część ODPOWIEDŹ WPROST. KAŻDY jej punkt musi trafić do
  odpowiedzi — także drugi wariant, opis wyglądu, czas trwania, tańsza
  alternatywa. Zanim oddasz tekst, sprawdź punkt po punkcie, czy są wszystkie.
  Z części TŁO bierz tylko to, co pasuje do pytania. Skracaj opisy, nie liczby. Przy pytaniu „co to /
  dlaczego" podaj też, co książka każe zrobić. Gdy książka podaje kilka
  wariantów (tunel / grunt, etap uprawy, odmiany), podaj wszystkie.
- Nazwy i kategorie bierz z książki, nie z pytania: gdy książka mówi
  „tolerancja", nie pisz „odporność".
- Liczby i zalecenia wyłącznie z książek. Uzasadnienie („…bo to sprzyja chorobom")
  możesz dopisać sam, także gdy książka go nie podaje.
- Każdy fakt z książki oznacz znacznikiem źródła: [id-ksiazki s. N] — zawsze
  z id, także przy jednej książce, np.
  [sulek-pomidory s. 23]. Kilka stron: [sulek-pomidory s. 12, 28]. Znacznik stoi
  przy fakcie, którego dotyczy — nie zbieraj stron różnych faktów w jeden.
- Liczba zawsze z warunkiem („80 x 40 cm dla odmian wcześniejszych przy palikach",
  nie samo „80 x 40 cm"). Gdy książka podaje dwie wartości w różnych warunkach,
  podaj obie z ich warunkami — to nie jest sprzeczność.
- Gdy na pytanie (albo jego część) zaznaczone książki w ogóle nie odpowiadają,
  powiedz to wprost: „Nie ma tego w zaznaczonych książkach." Nie uzupełniaj
  z własnej wiedzy, nawet ogólnikiem. Nie używaj tej formuły jako dopisku do
  odpowiedzi, którą już dałeś.
  Gdy książka odpowiada częściowo, najpierw podaj tę część, a „nie ma" powiedz
  tylko o brakującym kawałku.
- Gdy czegoś brakuje (całości albo części), sprawdź poza_zakresem. Jeśli coś
  zwróciło, podpowiedź jest obowiązkowa i wymienia KAŻDĄ zwróconą książkę
  z tytułem i stronami, np.: „W książkach „Sułek, pomidory" (s. 8, 10, 22)
  i „Pomidory, uprawa amatorska w ogrodzie" (s. 4, 18) jest coś na ten temat —
  zaznaczyć?". Nigdy ogólnie („w innych książkach"). Gdy odpowiedź jest pełna,
  podpowiedzi nie dawaj.
  Książek spoza zakresu nigdy nie nazywaj „zaznaczonymi".
- Gdy książka mówi tylko część, podaj tę część i powiedz, czego brakuje — tylko
  o rzeczach, o które zapytano.
- Kilka książek: nazywaj je tytułem, nie „druga książka". Gdy pomocnik jednej
  oddał NIC, napisz jednym zdaniem, że w „Tytuł" tego nie ma. Gdy wartości
  z dwóch książek się zazębiają, powiedz to jednym zdaniem.
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
- Nie przenoś pogrubień i nagłówków z raportów pomocników.
- Bez metafor i ozdobników spoza książki („sauna", „po łebkach").
- Bez emotek, nadmiaru nagłówków i pogrubień, wyliczanek tam, gdzie wystarczy
  zdanie, i pytań do czytelnika na końcu.

Spory między książkami:
- Gdy dwie RÓŻNE książki podają różne liczby (pH, temperatura, rozstaw, termin,
  dawka, stężenie, czas) dla tej samej rzeczy, tej samej rośliny i w tym samym
  warunku (tunel / grunt, etap uprawy), to jest spór. Zanim napiszesz
  odpowiedź, MUSISZ wywołać zglos_spor — samo pokazanie obu wartości
  w odpowiedzi nie wystarcza, bo bez zgłoszenia redaktor nie może go
  rozstrzygnąć. Jedno zgłoszenie na jedną rzecz (np. stężenie i czas tego
  samego zabiegu to jeden spór). Potem w odpowiedzi pokaż obie wartości,
  każdą ze źródłem, a numer [U..] ze zgłoszenia raz, przy tej rzeczy. Odpowiedź nie czeka na
  decyzję redaktora.
- To NIE jest spór: dwie wartości z jednej książki, różne warunki, zakresy,
  które się zazębiają (pH 5,5–6,5 i 6,0–7,0), górne granice („przed 10 cm"
  i „najwyżej 2–3 cm"). Nie zgłaszaj też sporu, który jest już na liście niżej
  (w dowolnym statusie) albo który pomocnik oznaczył numerem U.
- Wartość z ustalenia redakcji oznacz numerem obok źródła: „100 x 80 cm
  [sulek-pomidory s. 23] [U17]" — panel pokaże przy nim „ustalenie redakcji".
  Przy sporze otwartym podaj obie wartości ze źródłami i numer [U22].

ZAZNACZONE KSIĄŻKI — PRZEWODNIKI
{przewodniki}

SPORY ZAZNACZONYCH KSIĄŻEK
{spory}
"""


DOPYTANIE_O_SPOR = """Sprawdź swoją odpowiedź wyżej: czy pokazuje dwie RÓŻNE liczby z dwóch RÓŻNYCH
książek dla tej samej rzeczy w tym samym warunku (i nie są to zazębiające się zakresy
ani górne granice)? Jeśli tak — wywołaj zglos_spor (jedno zgłoszenie na rzecz; spór
już zgłoszony narzędzie rozpozna samo). Jeśli nie — wywołaj brak_sporu."""

PO_ZGLOSZENIU = """Napisz odpowiedź od nowa, z numerem [U..] przy spornej rzeczy — raz, nie przy
każdej wartości. Gdy spór jest rozstrzygnięty (status w wyniku narzędzia), podaj
przyjętą wartość jako ustalenie redakcji z jej numerem. Zwróć tylko odpowiedź."""


def _openai_petli():
    # Przez moduł pętli, żeby testy podmieniały jednego klienta.
    return _petla._openai


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
        # Tylko spory tej książki — lista rośnie z liczbą sporów jednej książki,
        # nie całej biblioteki.
        {"role": "system", "content": SUBAGENT.format(
            tytul=tytul, id=ksiazka, przewodnik=_przewodnik(ksiazka), spory=spory.blok([ksiazka]))},
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


def odpowiedz(ksiazki: list[str], pytanie: str, historia: list[dict] | None = None,
              wiadomosc_id: int | None = None) -> Odpowiedz:
    """historia: wcześniejsze tury rozmowy, [{"role": "user"|"assistant", "content": ...}]."""
    zakres = narzedzia.Zakres(tuple(ksiazki))
    slad = Slad()
    tytuly = {id: zapis.czytaj_meta(id).get("tytul", id) for id in ksiazki}
    # Tytuł obok id: w odpowiedzi książki nazywamy tytułem, w znaczniku — id.
    przewodniki = "\n\n".join(f"=== {id} — „{tytuly[id]}\" ===\n{_przewodnik(id)}" for id in ksiazki)

    def zapytaj_ksiazke(ksiazka: str, zadanie: str) -> str:
        if ksiazka not in zakres:
            return f'{{"blad": "książka {ksiazka!r} nie jest w zaznaczonym zakresie"}}'
        return subagent(zakres, ksiazka, zadanie, slad)

    zgloszone: list[int] = []

    def zglos_spor(czego_dotyczy: str, warunek: str, a: dict, b: dict) -> dict:
        # Kod pilnuje tylko zakresu; czy to spór — ocenia model, poprawia redaktor.
        for opcja in (a, b):
            if opcja.get("ksiazka") not in zakres:
                return {"blad": f"książka {opcja.get('ksiazka')!r} nie jest w zaznaczonym zakresie"}
        if stary := spory.istniejacy([a, b]):
            zgloszone.append(stary["id"])
            return {"istnieje": f"U{stary['id']}", "nie_zgloszono_ponownie": True,
                    "spor": spory.opis(stary)}
        spor_id = spory.zglos(czego_dotyczy, warunek, [a, b], wiadomosc_id)
        zgloszone.append(spor_id)
        return {"zgloszono": f"U{spor_id}"}

    opcja = {"type": "object",
             "properties": {"ksiazka": {"type": "string", "enum": list(ksiazki)},
                            "strona": {"type": "integer"}, "wartosc": {"type": "string"}},
             "required": ["ksiazka", "strona", "wartosc"]}
    nz = [
        Narzedzie(
            "zglos_spor",
            "Zgłasza redaktorowi spór: dwie książki podają różne liczby dla tej samej rzeczy "
            "w tym samym warunku. Wywołaj ZAWSZE, gdy odpowiedź ma pokazać dwie różne "
            "wartości z dwóch książek dla tej samej rzeczy i warunku — przed napisaniem "
            "odpowiedzi. Zwraca numer sporu (U..).",
            {"type": "object",
             "properties": {"czego_dotyczy": {"type": "string"},
                            "warunek": {"type": "string", "description": "np. grunt, tunel, rozsada; puste, gdy ogólne"},
                            "a": opcja, "b": opcja},
             "required": ["czego_dotyczy", "warunek", "a", "b"]},
            zglos_spor,
        ),
        Narzedzie(
            "zapytaj_ksiazke",
            "Wysyła pomocnika do jednej zaznaczonej książki; oddaje fakty ze stronami. "
            + "Książki: " + "; ".join(f"{id} = „{t}\"" for id, t in tytuly.items()),
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
        {"role": "system", "content": ORKIESTRATOR.format(przewodniki=przewodniki, spory=spory.blok(ksiazki))},
        *(historia or []),
        {"role": "user", "content": pytanie},
    ]
    slad.zdarzenie(kto="orkiestrator", pytanie=pytanie, ksiazki=ksiazki)
    # Pierwsza runda wymusza narzędzie: odpowiedź bez zajrzenia do książki
    # to odpowiedź z własnej wiedzy modelu.
    tekst = petla(config.ORKIESTRATOR_MODEL, wiadomosci, nz, config.ORKIESTRATOR_LIMIT_RUND, slad,
                  "orkiestrator", wymus_narzedzie=True)
    # Model po raportach pomocników pisał odpowiedź z dwiema wartościami i nie
    # wołał zglos_spor (testy 2026-10-03: 1 zgłoszenie na 4). Kod nie sprawdza,
    # czy spór jest — pyta raz, z wymuszonym wyborem: zgłoś albo brak.
    if len(ksiazki) >= 2 and not zgloszone:
        tekst = _sprawdz_spor(wiadomosci, tekst, nz[0], slad)
    return Odpowiedz(tekst, slad)


def _sprawdz_spor(wiadomosci: list[dict], tekst: str, zglos: Narzedzie, slad: Slad) -> str:
    brak = Narzedzie("brak_sporu", "W odpowiedzi nie ma sporu do zgłoszenia.",
                     {"type": "object", "properties": {}}, lambda: {"ok": True})
    wiadomosci += [{"role": "assistant", "content": tekst},
                   {"role": "user", "content": DOPYTANIE_O_SPOR}]
    odp = _openai_petli().chat.completions.create(
        model=config.ORKIESTRATOR_MODEL, messages=wiadomosci,
        tools=[zglos.schemat(), brak.schemat()], tool_choice="required")
    slad.zuzyte(odp.model, odp.usage)
    msg = odp.choices[0].message
    wywolania = msg.tool_calls or []
    if not any(tc.function.name == "zglos_spor" for tc in wywolania):
        slad.zdarzenie(kto="orkiestrator", sprawdzenie_sporu="brak")
        return tekst
    wiadomosci.append({"role": "assistant", "content": msg.content,
                       "tool_calls": [tc.model_dump() for tc in wywolania]})
    for tc in wywolania:
        narzedzie = zglos if tc.function.name == "zglos_spor" else brak
        wiadomosci.append({"role": "tool", "tool_call_id": tc.id,
                           "content": _wykonaj(narzedzie, tc.function.arguments, slad, "orkiestrator")})
    wiadomosci.append({"role": "user", "content": PO_ZGLOSZENIU})
    odp = _openai_petli().chat.completions.create(model=config.ORKIESTRATOR_MODEL, messages=wiadomosci)
    slad.zuzyte(odp.model, odp.usage)
    return (odp.choices[0].message.content or tekst).strip()
