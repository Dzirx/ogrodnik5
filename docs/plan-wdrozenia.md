# Ogrodnik 5 — plan wdrożenia

Plan budowy systemu opisanego w `proces.md`. Kolejność jest celowa: każdy
etap daje coś, co da się uruchomić i obejrzeć, zanim zacznie się następny.
Panel jest na końcu — najpierw musi działać to, co odpowiada na pytania.

Stan na 2026-10-02: jest projekt (`proces.md`), ręczny wzorzec przewodnika
(`data/zrodla/sulek-pomidory/ksiazka.md`) i pytania testowe
(`testy/sulek.yaml`). Kodu nie ma.

## Książki do testów

Z `ogrodnik4/_tab/` — pliki klienta, na których mierzono parsowanie:

| Plik | Po co |
|------|-------|
| `Sułek pomidory.pdf` | proza, Canva, strony ze zdjęciami, s. 26 z tekstem tylko w obrazie |
| `Program_ochrony_pomidor_szklarniowy.pdf` | tabele dawek (33 strony z tabelami) |
| `Program_ochrony_pomidora_gruntowego.pdf` | tabele, wzorzec ręczny dla s. 8 (`_tab/wzorzec_s8.json`) |
| `pomidory-uprawa-amatorska-w-ogrodzie.pdf` | proza bez pustych linii między akapitami |
| `PODR Innowacyjna amatorska uprawa pomidorów pod osłonami.pdf` | broszura, jedna tabela, zdjęcia |

Wszystkie są o pomidorze, więc nadają się też do sporów między książkami.
To materiały klienta — zostają lokalnie i na serwerze, nie trafiają do
repozytorium (`data/` w `.gitignore`).

---

## Etap 0. Szkielet

- Repozytorium git w `ogrodnik5`, `.gitignore`: `data/`, `.env`, `__pycache__/`.
- Układ:
  ```
  app/
    config.py        ustawienia z .env (klucz OpenAI, modele, limity)
    ingest/          wgrywanie książki (etap 1–2)
    agent/           narzędzia, orkiestrator, subagent (etap 3–4)
    spory.py         (etap 5)
    db.py            SQLite
    api/             panel (etap 6)
  data/              książki i baza — poza repozytorium
  docs/  testy/
  ```
- `requirements.txt`: fastapi, uvicorn, jinja2, python-multipart, sqlalchemy,
  openai, pymupdf, pyyaml, pytest.
- `Dockerfile`: python:3.12-slim + `tesseract-ocr tesseract-ocr-pol` (ripgrep niepotrzebny — `szukaj` w Pythonie, patrz `proces.md`, etap 3).
- `.env`: klucz OpenAI przepisuje człowiek (z ogrodnik4 albo nowy).

**Gotowe, gdy:** `docker build` przechodzi, `pytest` uruchamia się (pusto).

## Etap 1. Wgrywanie: tekst stron

Przeniesienie z ogrodnik4 (wersja z commitów):

| Skąd | Co bierzemy | Czego nie bierzemy |
|------|-------------|--------------------|
| `app/ingest/pipeline.py` | `_extract_pages` z flagami PyMuPDF (`TEXT_INHIBIT_SPACES`, `TEXT_DEHYPHENATE`) | `process_source`, chunki, Qdrant, konflikty, przepinanie odnośników |
| `app/ingest/ocr.py` | całość | — |
| `app/ingest/tabele.py` | całość | — |
| `tests/test_ocr.py`, `tests/test_tabele.py` | przerobione pod nowy zapis | testy chunków, wyszukiwania, cytatów |

Nowe:

- Zapis wyniku `_extract_pages` do `data/zrodla/<id>/`:
  `original.pdf`, `strony/0001.txt` (pusty plik dla strony bez treści),
  `meta.json` (tytuł, autor, kategorie, status, liczba stron, numery stron
  z OCR i z tabelą).
- Wklejony tekst: `original.txt` + jedna strona `strony/0001.txt`.
- `id` książki ze slugu tytułu (`sulek-pomidory`), z dopiskiem przy kolizji.
- Wywołanie z wiersza poleceń, bez panelu:
  `python -m app.ingest plik.pdf --tytul "..." --kategorie pomidor`.
- Ponowne przetworzenie nadpisuje `strony/` i `meta.json`, nigdy oryginału.

**Gotowe, gdy:**
- Sułek: 51 plików stron, strony 1, 5, 37, 38 puste albo z samym szumem
  odrzuconym przez OCR, strona 26 zawiera akapit o wilkach.
- Program ochrony gruntowego, s. 8: blok tabeli zgodny z `wzorzec_s8.json`
  (6/6 wpisów — tak jak mierzono w ogrodnik4).
- Wszystkie pięć książek testowych wgrane, plus jeden wklejony tekst.

## Etap 2. Wgrywanie: przewodnik `ksiazka.md`

- Prompt, który z tekstu stron (ze znacznikami numerów) pisze przewodnik
  w układzie ze wzorca: co to jest, czego tu nie ma, mapa stron ze słowami
  książki, pułapki.
- Długa książka (nie mieści się w jednym wywołaniu): przewodnik po kawałkach,
  potem złożenie w jeden.
- Wynik zapisywany do `ksiazka.md`; ponowne wygenerowanie na żądanie.

**Gotowe, gdy:**
- Przewodnik Sułka porównany z ręcznym wzorcem: te same tematy, zbliżone
  zakresy stron, kolumna „szukaj też jako" niepusta (ogławianie, wilki,
  pikowanie, zaprawianie).
- Przewodniki pozostałych czterech książek przejrzane przez człowieka.
- Ręczny wzorzec Sułka poprawiony po pełnym tekście z etapu 1
  (powstał z samego pdftotext).

## Etap 3. Narzędzia

Zwykłe funkcje Pythona, bez modelu, każda z testem:

| Narzędzie | Zachowanie |
|-----------|------------|
| `szukaj(fraza, ksiazki?)` | dosłowne szukanie (w Pythonie, jak grep) po `strony/*.txt` zakresu, bez rozróżniania wielkości liter; książka, strona, fragment wokół trafienia; limit trafień z informacją „jest więcej" |
| `czytaj_strony(ksiazka, od, do)` | tekst stron ze znacznikami numerów; limit stron na wywołanie |
| `przewodnik(ksiazka)` | treść `ksiazka.md` |
| `poza_zakresem(fraza)` | tytuły i numery stron trafień poza zakresem, bez tekstu |

Zakres jest parametrem narzędzi ustawianym przez kod — książka spoza zakresu
zwraca błąd, a nie treść.

**Gotowe, gdy:** testy jednostkowe na Sułku: `szukaj("ogławianie")` trafia
w s. 12 i 28, `czytaj_strony` respektuje limit, książka spoza zakresu jest
niewidoczna.

## Etap 4. Agent

- **Subagent:** jedna książka. Dostaje pytanie, przewodnik swojej książki
  (później też jej spory), narzędzia zawężone do tej książki. Oddaje fakty
  ze stronami albo „nic tu nie ma".
- **Orkiestrator:** dostaje instrukcję, przewodniki zakresu, historię
  i pytanie. Wybiera książki, uruchamia subagentów równolegle, pisze
  odpowiedź ze znacznikami `[ksiazka s. N]`. Gdy nic nie ma — „nie ma
  w zaznaczonych książkach" i podpowiedź z `poza_zakresem`.
- Kolejność kontekstu pod cache: instrukcja → przewodniki → (spory) →
  historia i pytanie. Nic zmiennego na początku.
- Budżet: luźny limit wywołań na subagenta i na orkiestratora, w `config.py`.
- Ślad: każde wywołanie narzędzia z argumentami i rozmiarem wyniku,
  zapisywany do pliku JSON przy wywołaniu z wiersza poleceń, później do SQLite.
- Wywołanie z wiersza poleceń:
  `python -m app.agent --ksiazki sulek-pomidory "Kiedy obcinać czubki?"`.
- Skrypt testowy: przechodzi `testy/*.yaml`, zapisuje odpowiedź i ślad obok
  oczekiwań do `testy/wyniki/<data>/`. Ocenia człowiek, czytając raport.

**Gotowe, gdy:**
- Testy rodzaju `brak` (kiedy-siac, dawka-signum, dawki-npk, papryka) nie
  dopisują wiedzy spoza książki.
- `odkazanie-nasion` znajduje s. 39 mimo braku w przewodniku.
- Ślady przejrzane; na ich podstawie ustalony budżet pętli
  (ostatnie otwarte pytanie z `proces.md`).
- Zmierzony czas i koszt jednej odpowiedzi i jednego artykułu.
- Wybrane modele OpenAI (orkiestrator, subagent) po porównaniu dwóch na testach.
- Dopisane pytania testowe do drugiej książki (np. PODR).

## Etap 5. Spory

- Tabele `spory` i `spor_opcje` w SQLite (schemat w `proces.md`).
- Narzędzie orkiestratora `zglos_spor` — zapisuje spór, nic nie sprawdza.
- Subagent dostaje spory swojej książki (wszystkie statusy) pod przewodnikiem;
  stosuje ustalenia przy tym samym warunku; otwartych i odrzuconych nie
  zgłasza ponownie.
- Znacznik `[U17]` w odpowiedzi.
- Rozstrzyganie z wiersza poleceń (przed panelem):
  `python -m app.spory rozstrzygnij 17 --wartosc "100 x 80 cm"`.

**Gotowe, gdy:**
- Pytanie z zakresem dwóch książek o pomidorze zgłasza co najmniej jeden spór
  o liczbę, a ten sam spór przy drugim pytaniu nie wraca.
- Po rozstrzygnięciu odpowiedź używa przyjętej wartości ze znacznikiem `[U..]`.
- Dopisany test: ustalenie dla gruntu, pytanie o tunel — ustalenie nie może
  zostać przeniesione.

## Etap 6. Panel

Wygląd i układ z ogrodnik4 (`base.html`, `chat.html`, `zrodla.html`,
`zrodlo.html`, `konflikty.html`), przepisane pod nowe dane:

- Odpowiedzi liczone w tle — bez Redisa i RQ: osobny proces roboczy, który
  bierze z SQLite wiadomości o statusie `pending`.
- **Pracownia:** historia wątków, zakres z kategoriami (grupowanie
  i zaznaczanie grupy jak w `wybor_zrodel`), odpowiedź ze znacznikami
  zamienionymi na linki, podgląd strony jako zwykły tekst z zaznaczonym
  fragmentem, ramka sporu pod odpowiedzią, ręczna poprawka odpowiedzi.
- **Biblioteka:** dodawanie (plik, tytuł, autor, kategorie), edycja,
  ponowne przetworzenie, edycja przewodnika, pobranie oryginału, etykieta
  przy stronach z tabelą.
- **Do ustalenia:** spory otwarte i rozstrzygnięte, te same przyciski co
  w ramce pod odpowiedzią.
- Logowanie hasłem jak w ogrodnik4 (`auth_username`, `auth_password`).

**Gotowe, gdy:** redaktor przechodzi całą drogę w panelu: dodaje książkę,
zaznacza kategorię, pyta, klika odnośnik, rozstrzyga spór, a kolejna
odpowiedź używa ustalenia.

## Etap 7. Serwer

- `docker-compose.yml` z dwiema usługami z jednego obrazu: panel i proces
  roboczy; wolumen na `data/`. Bez Postgresa, Qdranta, Redisa, MinIO.
- Port wolny na VPS (w ogrodnik4 8002, bo 8001 zajęty) — do ustalenia przy
  wdrożeniu, żeby oba projekty mogły stać obok siebie.
- Kopia zapasowa: kopiowanie katalogu `data/` (książki + `ogrodnik.db`).
- Przeniesienie biblioteki klienta z ogrodnik4: oryginały z MinIO
  przetworzone od nowa nowym wgrywaniem (tytuły, autorzy i etykiety jako
  kategorie) — bez migracji bazy.

**Gotowe, gdy:** klient pracuje na serwerze, a kopia zapasowa została raz
odtworzona na próbę.

---

## Ryzyka

- **Czas odpowiedzi.** Pętla z subagentami to wiele wywołań modelu.
  Mierzymy w etapie 4, zanim zbudujemy panel.
- **Jakość przewodników.** Od nich zależy, czy agent trafia we właściwe
  strony. Etap 2 kończy się przeglądem przez człowieka, nie automatem.
- **Polska odmiana bez wektorów.** Zależy od tego, czy model szuka kilkoma
  wariantami. Testy rodzaju `laik` to sprawdzają.
- **Brak kontroli cytatów i sporów w kodzie** — świadoma decyzja
  (`proces.md`). Odpowiedź przed publikacją sprawdza człowiek, zwłaszcza
  dawki środków ochrony roślin.
