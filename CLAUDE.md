# Ogrodnik 5

Panel dla „Anielskich Ogrodów": redaktor wgrywa książki ogrodnicze, zaznacza
zakres (kategorie / książki, jak w NotebookLM) i zadaje pytania. Agent sam
szuka odpowiedzi w tekście stron — grep i czytanie, jak Claude Code w kodzie.
Następca `~/projekt/ogrodnik4` (RAG z wektorami — porzucony).

## Przeczytaj najpierw

- `docs/proces.md` — jak system działa. Wszystkie ustalenia z rozmów
  1–2 października 2026.
- `docs/plan-wdrozenia.md` — etapy 0–7 z kryteriami „gotowe, gdy".

## Stan

- Etap 0 gotowy (2026-10-02): git, `app/`, `requirements.txt`, `Dockerfile`
  (build przechodzi), `pytest`. Lokalnie `.venv/`.
- Etap 1 gotowy (2026-10-02): parsowanie przeniesione (`app/ingest/strony.py`,
  `ocr.py`, `tabele.py`), zapis `app/ingest/zapis.py`, CLI
  `python -m app.ingest`. Wgrane: 5 książek testowych + notatka testowa;
  wszystkie 56 stron z tabelą mają blok z modelu, s. 8 programu gruntowego
  6/6 ze wzorcem.
- Etap 2 w toku: `app/ingest/przewodnik.py`, model z `.env`
  (`gpt-5.4-mini`). Przewodniki są dla wszystkich książek: Sułek —
  `gpt-5.4-mini`, pozostałe — `gpt-5.5` (z porównania modeli). Zostało:
  przegląd przewodników przez człowieka.
- Etap 3 gotowy (2026-10-02): `app/agent/narzedzia.py` — szukaj,
  czytaj_strony, przewodnik, poza_zakresem; testy, w tym na Sułku.
- Następny krok: etap 4 (subagent, orkiestrator, testy z `testy/sulek.yaml`).
- `.env` skopiowany z ogrodnik4 (2026-10-02) — nie odczytuj go ani nie
  wyświetlaj. Zostały w nim: `OPENAI_API_KEY`, `AUTH_USERNAME`,
  `AUTH_PASSWORD`, `ANSWER_MODEL`, `ANALYSIS_MODEL`; dopisane
  `PRZEWODNIK_MODEL=gpt-5.4-mini`. Pozostałe zmienne z ogrodnik4 usunięte.
  Lista wszystkich zmiennych: `.env.example`.
- Ręczny wzorzec przewodnika (historia, z samego pdftotext, ma błędy):
  `data/zrodla/sulek-pomidory/ksiazka.wzorzec-reczny.md`. Agent go nie czyta.
- Pytania testowe: `testy/sulek.yaml`.
- Książki testowe: `~/projekt/ogrodnik4/_tab/*.pdf` (materiały klienta —
  nie do repozytorium).

## Decyzje, których nie podważać

Podjęte przez właściciela projektu świadomie:

- **Bez wektorów i chunków.** Strona PDF = plik `strony/NNNN.txt`; agent
  grepuje i czyta strony. Przewodnik `ksiazka.md` wyznacza drogę, nie
  zawiera treści.
- **Model ocenia wszystko, kod niczego nie sprawdza w treści.** Bez kontroli
  cytatów, bez regexów na wartościach, bez bramek na sporach. Kod pilnuje
  tylko zakresu, budżetu wywołań i zapisuje ślad. Pomyłki modelu poprawia
  redaktor.
- **Spory** zgłasza agent podczas odpowiedzi (`zglos_spor`), zapis w SQLite,
  pogrupowane po książkach; subagent dostaje spory swojej książki.
- **Orkiestrator + subagent na książkę.**
- **Panel jak w ogrodnik4** (trzy ekrany); podgląd źródła to zwykły tekst
  strony, bez obrazu PDF.
- **Parsowanie bierzemy z ogrodnik4** (`_extract_pages`, `ocr.py`,
  `tabele.py`); reszty ogrodnik4 nie przenosimy.
- OpenAI, SQLite, pliki na dysku; bez Postgresa, Qdranta, Redisa, MinIO.
- Źródłem może być PDF albo wklejony tekst (jedna strona, `original.txt`).
- Bez osobnych form odpowiedzi (artykuł / post / lista).
- Styl: zasady w `docs/proces.md` („Styl odpowiedzi"). Liczby i zalecenia
  tylko z książek; uzasadnienia model może dopisać sam.

## Sposób pracy

- Odpowiadaj po polsku.
- Komentarze w kodzie po polsku, w stylu ogrodnik4: dlaczego, nie co.
- Po każdej decyzji zaktualizuj `docs/proces.md` (i stan powyżej).
