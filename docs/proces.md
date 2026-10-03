# Ogrodnik 5 — jak działa

Stan: etapy 0–5 zrobione, następny etap 6 (panel). Ustalenia z 1–2 października 2026.

## Zasada

Model sam szuka odpowiedzi w książkach, tak jak Claude Code szuka w kodzie:
grepuje, czyta strony, szuka dalej innymi słowami, aż uzna, że wie dość.
Bez wektorów, bez chunków, bez kontroli cytatów i bez wieloetapowego
składania odpowiedzi.

Oryginał książki jest jedynym źródłem prawdy. Wszystko inne (tekst stron,
przewodnik) jest z niego wyprowadzone i da się odtworzyć.

## Przechowywanie

```
data/
  zrodla/<id>/
    original.pdf      oryginał, nigdy nie zmieniany
    meta.json         tytuł, autor, kategorie, status, liczba stron,
                      strony z OCR i strony z tabelą
    ksiazka.md        przewodnik dla modelu (patrz niżej)
    strony/0001.txt   czysty tekst jednej strony, numer = numer strony PDF
  ogrodnik.db         SQLite: rozmowy, wiadomości, ślady szukania
```

- Plik na stronę: wynik grepa niesie numer strony w nazwie pliku.
- Strona z tabelą: zamiast poszarpanego tekstu blok czytelnego tekstu
  z modelu tabel (obraz + warstwa tekstowa, dwa wywołania).
- Strona bez warstwy tekstowej: odczyt OCR (Tesseract, polski).
- Strony bez treści (same zdjęcia) mają pusty plik — numeracja zostaje ciągła.
- Wklejony tekst: redaktor może dodać do źródeł własny tekst zamiast pliku.
  To „książka" z jedną stroną `strony/0001.txt`, bez `original.pdf` —
  oryginałem jest zapisany tekst (`original.txt`). Ma kategorie i przewodnik
  jak każda inna.

## Wgrywanie książki

1. Redaktor dodaje plik PDF albo wkleja tekst, podaje tytuł, autora
   i kategorie (np. „pomidor").
2. Tekst każdej strony do `strony/`; tabele i OCR tam, gdzie trzeba.
3. Model czyta tekst książki i pisze `ksiazka.md`.

### Przewodnik `ksiazka.md`

Nie zawiera treści książki, tylko drogę do niej:

- **Co to jest** — rodzaj książki, dla kogo, jaka uprawa (tunel, grunt).
- **Czego tu nie ma** — żeby model nie szukał na darmo (np. „brak dawek ŚOR").
- **Mapa stron** — zakres stron, temat, **słowa, pod którymi temat stoi
  w książce** („ogławianie" = obcinanie czubków). To zastępuje synonimy,
  które dawały wektory.
- **Pułapki** — rozdziały przechodzące przez strony, strony ze zdjęciami,
  osobiste rekomendacje autora.

Pierwszy wzorzec napisany ręcznie:
`data/zrodla/sulek-pomidory/ksiazka.wzorzec-reczny.md` (z samego pdftotext,
ma błędy). Od 2026-10-02 `ksiazka.md` Sułka to przewodnik z `gpt-5.4-mini`.
Redaktor może przewodnik poprawić.

## Pytanie

1. **Zakres** — redaktor zaznacza kategorię i książki, jak w NotebookLM.
   Zakres jest zapisany przy rozmowie; zmiana działa od następnego pytania.
2. **Start** — model dostaje instrukcję i przewodniki zaznaczonych książek.
   Ta część jest stała w obrębie rozmowy, więc korzysta z cache promptu.
   Na początku promptu nie ma nic zmiennego (daty, godziny).
3. **Szukanie** — pętla narzędzi, aż model uzna, że wie dość.
4. **Odpowiedź** — model pisze ją sam, z odnośnikami do stron, z których
   korzystał. Odnośnik otwiera w panelu tekst tej strony.
5. **Gdy nic nie ma** — mówi wprost „nie ma w zaznaczonych książkach"
   i nie uzupełnia z własnej wiedzy. Jeśli coś jest w bibliotece poza
   zakresem, dodaje podpowiedź: „w książce X (s. N) jest coś na ten temat —
   zaznaczyć?".

### Narzędzia

| Narzędzie | Co robi | Zasięg |
|-----------|---------|--------|
| `szukaj(fraza, ksiazki?)` | grep bez rozróżniania wielkości liter; zwraca książkę, stronę i 2–3 linijki wokół; limit trafień | tylko zakres |
| `czytaj_strony(ksiazka, od, do)` | pełny tekst stron; limit stron na wywołanie | tylko zakres |
| `przewodnik(ksiazka)` | ponownie `ksiazka.md`, gdy wypadł z uwagi | tylko zakres |
| `poza_zakresem(fraza)` | same tytuły i numery stron trafień w reszcie biblioteki, bez tekstu | cała biblioteka |
| `zglos_spor(...)` | zgłasza różnicę liczb między dwiema książkami; patrz „Do ustalenia" | tylko zakres |

Zakres pilnuje kod, nie prompt: narzędzie po prostu nie widzi książek spoza
zaznaczenia. `poza_zakresem` nie zwraca treści, więc odpowiedź nadal stoi
wyłącznie na zaznaczonych książkach.

### Co robi kod

Tylko trzy rzeczy:

- pilnuje zakresu w narzędziach,
- pilnuje budżetu (liczba wywołań narzędzi i stron na pytanie),
- zapisuje ślad: co model szukał i co czytał („szukałem: ogławianie,
  obcinanie czubków; czytałem s. 12, 28") — tylko do diagnozy, redaktor go
  nie widzi.

## Styl odpowiedzi

Zasady dla orkiestratora:

- Konkret od razu — bez wstępów („Oto kilka wskazówek", „Uprawa pomidorów
  to fascynujący proces").
- Bez typowych zwrotów AI: „warto pamiętać", „kluczowe jest", „istotne
  jest", „podsumowując", „w dzisiejszych czasach", „to zależy od wielu
  czynników".
- Bez waty: zdań, które nic nie mówią, i streszczenia tego samego na końcu.
- Liczby zawsze z warunkiem („80 x 40 cm dla odmian wcześniejszych przy
  palikach", nie samo „80 x 40 cm").
- Bez ozdobników: emotek, nadmiaru nagłówków i pogrubień, wyliczanek tam,
  gdzie wystarczy zdanie, pytań do czytelnika na końcu.

Granica wiedzy własnej modelu: **liczby i zalecenia tylko z książek;
uzasadnienia („…bo to sprzyja chorobom") model może dopisać sam**, także
gdy książka ich nie podaje.

Do sprawdzenia z klientem w etapie 4: pokazać 2–3 odpowiedzi z testów
i zapytać, czy o taki styl chodzi.

## Świadome decyzje i ich cena

- **Bez kontroli cytatów.** Odnośnik do strony to wskazówka, nie gwarancja:
  model może podać złą stronę albo przekręcić liczbę. Odpowiedź przed
  publikacją sprawdza człowiek — zwłaszcza dawki środków ochrony roślin.
- **Bez rozdzielenia zbierania i pisania.** W ogrodnik4 to rozdzielenie
  zdejmowało z odpowiedzi urzędowy język książek. Jeśli wróci, poprawiamy
  promptem, nie dokładając etapów.
- **Bez wektorów.** Odmianę i synonimy łapią: model (szuka kilkoma
  wariantami) i kolumna słów w przewodniku.

## Panel

Wygląd i układ jak w ogrodnik4 (`base.html`), trzy ekrany:

- **Pracownia** — rozmowy: historia wątków, wybór zakresu (kategorie grupują
  książki, zaznaczenie całej kategorii jednym kliknięciem), odpowiedź ze
  znacznikami stron i ustaleń, pod nią ramka sporu. Podgląd źródła to
  **zwykły tekst strony** z zaznaczonym fragmentem, bez obrazu PDF.
  Ręczna poprawka odpowiedzi zostaje.
- **Biblioteka** — dodawanie książki z kategoriami, edycja, ponowne
  przetworzenie, przewodnik do poprawienia, pobranie oryginału.
  Strona z tabelą ma etykietę „tabela odczytana automatycznie — sprawdź
  wartości".
- **Do ustalenia** — spory otwarte i rozstrzygnięte.

## Orkiestrator i subagenci

Pytanie obsługuje orkiestrator. Dostaje przewodniki zakresu, decyduje, które
książki warto przeczytać, i na każdą z nich puszcza subagenta — równolegle.
Subagent ma te same narzędzia, ale tylko dla swojej książki, i oddaje
orkiestratorowi to, co znalazł, ze stronami. Orkiestrator pisze odpowiedź.

Jak subagent w Claude Code: przeszukuje dużo, a do głównego kontekstu wraca
tylko wynik. Dzięki temu dwadzieścia książek w kategorii nie zapycha
orkiestratora, a każda książka jest czytana na własnych prawach.

## Do ustalenia (konflikty)

Spory wyłapuje agent podczas odpowiedzi, nie program przy wgrywaniu książki.
Pytanie mówi, co jest „tą samą rzeczą" — bez niego trzeba by zgadywać,
co z czym porównać, a fałszywy spór kosztuje więcej niż przeoczony
(lekcje z ogrodnik4, `app/answer/konflikty.py`; pierwsza wersja poległa
m.in. na kolejce 51 pozycji, przy których redaktor nie wiedział, co kliknąć).

Przebieg:

1. Gdy dwie książki z zakresu podają różne liczby dla tej samej rzeczy,
   orkiestrator wywołuje `zglos_spor(czego dotyczy, warunek, wartość A
   z książką i stroną, wartość B z książką i stroną)`.
2. Odpowiedź nie czeka na decyzję — pokazuje obie wartości ze źródłami.
3. Pod odpowiedzią redaktor widzi pytanie: wybór A, B, własna wartość
   albo „to nie jest spór".
4. Wybór staje się ustaleniem. Przy kolejnych pytaniach subagent czytający
   książkę dostaje jej spory i stosuje ustalenia; w odpowiedzi są oznaczone
   jako ustalenie redakcji. Ustalenie jest ważniejsze niż książka.
5. Ekran „Do ustalenia" zostaje jako lista sporów otwartych i rozstrzygniętych.

### Zapis

SQLite (`data/ogrodnik.db`) — to stan panelu, nie treść książki. Spór zawsze
dotyczy dwóch książek, więc opcje leżą w osobnej tabeli: po niej szukamy
sporów danej książki.

```sql
CREATE TABLE spory (
  id               INTEGER PRIMARY KEY,
  czego_dotyczy    TEXT,     -- własnymi słowami agenta
  warunek          TEXT,     -- "grunt", "tunel", "" gdy ogólne
  status           TEXT,     -- otwarty | rozstrzygniety | odrzucony
  przyjeta_wartosc TEXT,
  skad             TEXT,     -- ksiazka | redakcja (własna wartość)
  wiadomosc_id     INTEGER,  -- odpowiedź, pod którą powstał
  utworzono        TEXT,
  rozstrzygnieto   TEXT
);

CREATE TABLE spor_opcje (
  spor_id  INTEGER REFERENCES spory(id),
  ksiazka  TEXT,             -- id katalogu, np. "sulek-pomidory"
  strona   INTEGER,
  wartosc  TEXT
);
```

Przykład — spór o rozstaw, zgłoszony przy odpowiedzi 512:

| spory.id | czego_dotyczy | warunek | status | przyjeta_wartosc | skad |
|---|---|---|---|---|---|
| 17 | rozstaw odmian późnych pomidora | grunt | rozstrzygniety | 100 x 80 cm | ksiazka |

| spor_id | ksiazka | strona | wartosc |
|---|---|---|---|
| 17 | sulek-pomidory | 23 | 100 x 80 cm |
| 17 | ksiazka-x | 41 | 70 x 50 cm |

- Zgłasza agent narzędziem `zglos_spor`; status zmienia redaktor w panelu.
- „To nie jest spór" = `odrzucony`; wiersz zostaje, żeby agent go widział.
- Rozstrzygnięcie działa od następnego pytania; stare odpowiedzi się
  nie zmieniają.

### Jak agent korzysta ze sporów

Spory są pogrupowane po książkach. Każdy subagent dostaje na start
przewodnik swojej książki i **tylko jej spory** (wszystkie statusy):

```
SPORY TEJ KSIĄŻKI
U17 [rozstrzygnięty] rozstaw odmian późnych pomidora, grunt
    przyjęto: 100 x 80 cm (ze źródła)
    sulek-pomidory s. 23: 100 x 80 cm | ksiazka-x s. 41: 70 x 50 cm
U22 [otwarty] pH podłoża do siewu
    sulek-pomidory s. 14: 6,0–6,5 | ksiazka-z s. 8: 5,0–5,5
U31 [odrzucony – to nie spór] temperatura kiełkowania
```

Dzięki temu lista w kontekście rośnie z liczbą sporów jednej książki,
nie całej biblioteki.

Ustalenie stosuje **subagent** — tylko przy tym samym warunku (grunt / tunel,
etap uprawy). Oddaje orkiestratorowi wartość z numerem ustalenia
(„100 x 80 cm, s. 23, ustalenie U17"). Przy sporze otwartym podaje wartość
z książki z dopiskiem „spór U22 nierozstrzygnięty"; otwartych i odrzuconych
nie zgłasza drugi raz.

W odpowiedzi orkiestrator oznacza źródła znacznikami, panel zamienia je na
linki: `[sulek-pomidory s. 23]` otwiera tekst strony, `[U17]` pokazuje
etykietę „ustalenie redakcji" i otwiera spór z obiema wartościami.

Reguły sporu:

- tylko różne książki — dwie wartości w jednej książce to prawie zawsze dwa
  konteksty (Sułek: s. 31 „poniżej 14° nie zawiązuje", s. 34 „średnia dobowa
  poniżej 16°C utrudnia"),
- tylko liczby: pH, temperatury, rozstawy, terminy, dawki,
- ta sama roślina i ten sam warunek (tunel / grunt, etap uprawy),
- zakresy, które się zazębiają, nie są sporem (pH 5,5–6,5 i 6,0–7,0);
  górne granice też nie (pędy boczne: Sułek „zanim osiągną 10 cm", PODR
  „nie więcej niż 2–3 cm" — decyzja właściciela 2026-10-03).

Reguły ocenia wyłącznie model. Kod niczego nie sprawdza, tylko zapisuje
zgłoszenie. Porównywanie wartości w kodzie (regexy, jak `zakres()` w ogrodnik4)
myli się w obie strony: „80 x 40 cm" i „100 x 80 cm" dają przedziały 40–80
i 80–100, które „się zazębiają", więc prawdziwy spór o rozstaw by przepadł;
„3–5 kg/m²" łapie dwójkę z „m²". Pomyłki modelu redaktor usuwa przyciskiem
„to nie jest spór".

## Ustalone 2026-10-02

- Brak osobnych form odpowiedzi (artykuł, post, lista jak w ogrodnik4) —
  agent odpowiada na to, o co go poproszono, bez rozpoznawania formy.
- Modele OpenAI ustawiane w `config.py`, wybór na podstawie testów (etap 4).
- Książki z ogrodnik4 przenosimy, przetwarzając oryginały od nowa nowym
  wgrywaniem — bez migracji bazy.
- Ślad szukania widzimy tylko my, redaktor nie.
- Parsowanie (tekst stron, OCR, tabele) przenosimy z ogrodnik4
  (`_extract_pages`, `ocr.py`, `tabele.py`, wersja z commitów — uzupełnianie
  akapitów z OCR jest już zacommitowane); podział na akapity, Qdrant,
  Postgres i MinIO zostają w ogrodnik4.

## Ustalone przy etapie 0–1 (2026-10-02)

- `meta.json`: `tytul`, `autor`, `kategorie`, `rodzaj` (`pdf` | `tekst`),
  `liczba_stron`, `strony_ocr`, `strony_tabela`, `status` (`strony` — są
  strony, brak przewodnika; `gotowa` — jest `ksiazka.md`).
- Ponowne przetworzenie nadpisuje `strony/` i `meta.json` (zachowując tytuł,
  autora, kategorie), nie rusza oryginału ani `ksiazka.md`. Strony zapisywane
  do katalogu obok i podmieniane na końcu.
- Nieudane wgranie usuwa katalog książki (nie zajmuje id).
- `pymupdf==1.25.1` przypięte — na tej wersji mierzono parsowanie w ogrodnik4.
- Model tabel: `TABELE_MODEL` w `.env`, domyślnie `ANSWER_MODEL`, potem `gpt-4o`.
- `docs/tabele.md` przeniesione z ogrodnik4 jako opis reguł odczytu tabel.
- `meta.json` → `odczyt_tabel`: dla każdej strony z tabelą `"ok"` albo
  przyczyna porażki (np. `RateLimitError: …`). Wtedy w pliku strony jest
  surowa warstwa — wystarczy `--przetworz`. Opisu poprawek modelu 2
  (`poprawki`) świadomie nie zapisujemy.

## Ustalone przy etapie 2 (2026-10-02)

- Przewodnik: `python -m app.ingest.przewodnik <id>` (`--nadpisz`,
  `--wyjscie`). Istniejącego `ksiazka.md` nie nadpisuje bez `--nadpisz` —
  mógł go poprawić redaktor.
- Model przewodnika: `PRZEWODNIK_MODEL`, domyślnie `gpt-5.4-mini`
  ($0,75 / $4,50 za 1M tokenów wejścia / wyjścia, ok. 3 centy za książkę
  do 110 stron). Porównanie na Sułku (sprawdzone w tekście stron):
  `gpt-4o-mini` przesuwał mapę od s. 29 i zmyślał („brak GMO", tabela na
  s. 11, słowa spoza książki); `gpt-4.1` trafny, ale sklejał s. 33–46 w jeden
  wiersz (stary prompt); `gpt-5.5` — mapa zgodna w 30/30 wierszach, ale
  drogi; `gpt-5.4-mini` — mapa trafna, nieco szersze wiersze, mniej słów.
  Przewodniki wygenerowane 2026-10-02 przez `gpt-5.5` zostają (wszystkie
  książki poza Sułkiem); Sułek — `gpt-5.4-mini`.
- Wzorca Sułka nie dajemy modelowi jako przykładu — przepisałby jego tematy.
- Kolumna „Szukaj też jako": pojedyncze słowa albo rdzenie („pikow",
  „zapraw"), nie frazy — łamanie linii i OCR rozbijają frazy w tekście.
  Po tej zmianie 98–100% słów stoi dosłownie w tekście książek.
- Znacznik strony także na końcu (`=== KONIEC STRONY N ===`). Bez niego
  model przewodnika (także `gpt-5.5`) brał numer wydrukowany na początku
  strony zamiast numeru pliku — w PODR cała mapa od s. 40 była przesunięta
  o jeden. Sama instrukcja w prompcie nie pomogła (było gorzej), znacznik
  końca tak: 0 przesuniętych wierszy.
- Wiersz mapy najwyżej 3 strony — bez tego `gpt-5.4-mini` sklejał rozdział
  chorób (s. 22–31) w jeden wiersz. Model nie zawsze słucha (PODR: 22–28).
- Ręczny wzorzec ma błędy względem pełnego tekstu (np. s. 3 to gleba, nie
  rozsada; s. 35 bez „wybarwiania"; słowa w formie słownikowej, których grep
  nie trafi: „przepikowanie", „hartowanie", „przymrozki").

## Ustalone przy etapie 3 (2026-10-02)

- Narzędzia: `app/agent/narzedzia.py`; zakres to parametr `Zakres` ustawiany
  przez kod, książka spoza niego daje `{"blad": ...}`, nie treść.
- `szukaj` w czystym Pythonie zamiast ripgrep (lokalnie brak `rg`, a tak
  testy działają wszędzie). Zachowanie jak grep: dosłowna fraza, bez
  wielkości liter, bez odmiany. Białe znaki złączone, więc fraza przełamana
  końcem linii też trafia. Wynik: strona, liczba trafień na stronie
  i fragment ±200 znaków wokół pierwszego (okno znaków, nie linijki —
  tabela z modelu to jedna długa linia na pole).
- Limity w `.env`: `SZUKAJ_LIMIT_TRAFIEN=20` stron, `CZYTAJ_LIMIT_STRON=5`;
  przy przekroczeniu narzędzie mówi, ile pominęło i skąd czytać dalej.
- `czytaj_strony` dopisuje przy stronie „tabela odczytana automatycznie"
  albo „część tekstu z OCR".
- Kryterium planu „`szukaj("ogławianie")` trafia w s. 12 i 28" jest
  nieścisłe: dosłownie słowo stoi na s. 11 i 28; s. 12 ma „ogławiające",
  które trafia rdzeń „ogław". Test sprawdza oba przypadki.

## Ustalone przy etapie 4 (2026-10-02)

- Agent: `app/agent/agent.py` (orkiestrator + subagent), `petla.py` (pętla
  narzędzi, budżet rund, ślad), CLI `python -m app.agent --ksiazki … "pytanie"`
  (`--slad plik.json`). Orkiestrator ma `zapytaj_ksiazke(ksiazka, zadanie)`
  i `poza_zakresem`; wywołania z jednej rundy idą równolegle. Pierwsza runda
  orkiestratora i subagenta wymusza narzędzie (bez tego model mógłby
  odpowiedzieć z własnej wiedzy, nie zaglądając do książki).
- Testy: `python testy/uruchom.py testy/sulek.yaml --ksiazki sulek-pomidory`
  → `testy/wyniki/<data>/raport.md` + `slady/`. Ocenia człowiek (albo
  subagent Claude Code na prośbę) — skrypt niczego nie punktuje.
- Modele: orkiestrator i subagent `gpt-5.4-mini` (w `.env`). Subagent
  `gpt-5.4` porównany na 5 trudnych testach: naprawił jeden (dwie
  temperatury s. 31 i 34), w pytaniach szerokich nie był lepszy, a był 3–4×
  droższy i wolniejszy.
- Czas i koszt (`gpt-5.4-mini`, Sułek): pytanie 5–10 s, ok. $0,01–0,02;
  artykuł / post / lista 13–20 s, ok. $0,03–0,05. 20 testów ≈ $0,37.
- Budżet: przy limitach 6 rund orkiestratora / 12 subagenta nigdzie nie
  wyczerpany; maksimum 3 / 5. Zostaje luźny — na jednej cienkiej książce
  nie ma podstaw go obniżać; wrócić przy grubej książce i wielu książkach.
- Po pierwszym przebiegu poprawki promptów (z oceny odpowiedzi):
  orkiestrator przenosi każdą liczbę i warunek od pomocnika, znacznik przy
  fakcie, „nie ma w zaznaczonych" tylko gdy naprawdę nie ma, bez „Jeśli
  chcesz…" i podsumowań; subagent szuka rdzeniami, czyta każdą stronę
  z liczbą, stronę podaje tylko z przeczytanego tekstu, zachowuje tryb autora
  („utrudnia", nie „nie zawiązuje"). Efekt: obcinanie-czubkow i
  podlewanie-kroplowe pełne, „Jeśli chcesz…" z 6 do 1 odpowiedzi.
- Druga runda poprawek (2026-10-03): raport subagenta w dwóch częściach
  (ODPOWIEDŹ WPROST — linia na stronę, potem TŁO), orkiestrator przenosi
  każdy punkt pierwszej części; tytuły książek w kontekście orkiestratora;
  `poza_zakresem` zwraca najwyżej 5 stron (z największą liczbą trafień)
  i 3 książki. Na 6 testach, które wcześniej gubiły fakty: 5 w pełni.
- Rozrzut między przebiegami jest duży — ten sam test raz przechodzi, raz
  nie. Pojedynczy przebieg nie rozstrzyga o poprawce promptu.
- Podpowiedź „zaznaczyć?" niestabilna z `gpt-5.4-mini` jako orkiestratorem:
  w trzech przebiegach termin-siewu raz zła książka z 22 stronami, raz
  ogólnik bez tytułu, raz brak (model sam wyliczył „marzec" z 6–8 tygodni).
  Decyzja właściciela 2026-10-03: zostawiamy tak — podpowiedź to dodatek,
  odpowiedź bez niej jest poprawna. Wracamy przy panelu.
- Koszt testów: pełny przebieg 38 pytań ≈ $0,80. Od 2026-10-03 poprawki
  sprawdzamy na wybranych testach (`--tylko`), pełny zestaw przed
  zamknięciem etapu i za zgodą właściciela.
- Znany błąd: temperatura-zawiazywania z `gpt-5.4-mini` czyta tylko s. 34
  (przewodnik przypisuje tam zawiązywanie) i pomija „poniżej 14°" z s. 31.
- Testy poprawione po pełnym tekście z OCR: kiedy-siac (s. 17 podaje marzec
  — to już nie test „brak"), artykul-rozsada (dwa czasy rozsady),
  lista-chorob („wybarwianie" z s. 35 nie istnieje w tekście).

## Ustalone przy etapie 5 (2026-10-03)

- Kod: `app/db.py` (sqlite3, bez SQLAlchemy — dwie tabele, jeden plik),
  `app/spory.py` (zglos, lista, rozstrzygnij, odrzuc, blok dla modelu; CLI
  `python -m app.spory lista|pokaz|rozstrzygnij|odrzuc`). Schemat jak wyżej.
- Orkiestrator dostaje spory zaznaczonych książek (za przewodnikami — nie
  psują cache), subagent — spory swojej książki z regułami: ustalenie tylko
  przy tym samym warunku, otwarty z dopiskiem, odrzucony = zwykła wartość.
- `zglos_spor(czego_dotyczy, warunek, a, b)`; kod pilnuje tylko zakresu.
- Sprawdzenie sporu: `gpt-5.4-mini` sam z siebie prawie nie wołał
  `zglos_spor` (1 zgłoszenie na 4, choć pokazywał obie wartości). Gdy zakres
  ma ≥ 2 książki, a odpowiedź powstała bez zgłoszenia, kod raz pyta model
  z wymuszonym wyborem `zglos_spor` / `brak_sporu`; przy zgłoszeniu model
  pisze odpowiedź od nowa z [U..]. Kod nie ocenia, czy spór jest — pyta,
  bo narzędzie nie zostało użyte. Koszt: jedno wywołanie więcej przy
  pytaniach z kilku książek (ok. $0,002–0,005).
- Zaakceptowane przez właściciela 2026-10-03: `zglos_spor` nie tworzy nowego sporu dla
  tej samej pary (książka, strona) — zwraca istniejący numer i status.
  Porównuje tylko oznaczenia źródeł, nie wartości. Bez tego ten sam spór
  wracał przy każdym pytaniu (U2, U3, U4), a ustalenie przepadało.
- Scenariusze: `python testy/spory.py testy/spory.yaml` (własna baza
  przebiegu w `testy/wyniki/`). Wynik 2026-10-03: nadmanganian — zgłoszony,
  nie wraca, po rozstrzygnięciu odpowiedź z przyjętą wartością i [U2],
  pytanie o ziemię nie przenosi ustalenia, ale model zgłosił fałszywy spór
  „nasiona / ziemia" (do odrzucenia przez redaktora). Temperatura gleby —
  subagent za pierwszym razem nie zauważył „ok. 15°C", spór zgłoszony
  dopiero przy drugim pytaniu.

## Otwarte


- Budżet pętli — trudno powiedzieć z góry. Zaczynamy od luźnego limitu
  i ustalamy na podstawie śladów z testów.
- Testy: `testy/sulek.yaml` (20 pytań wg rodzajów, nie wg klienta) —
  do przejrzenia po przeniesieniu parsowania, bo prototyp powstał
  z samej warstwy tekstowej (pdftotext), a strona 26 ma akapit tylko w obrazie.
- Grube książki: wszystkie książki testowe mają do ok. 50 stron i są
  o pomidorze. Przewodnik generowany po kawałkach (300 stron) i zakres
  z kilkunastu książek sprawdzimy dopiero na prawdziwej grubej książce
  od klienta, najlepiej skanie — do zdobycia.
- Literówki OCR: redaktor nie może poprawić tekstu strony. Na razie
  akceptujemy; wracamy, jeśli skany będą słabej jakości.
