"""SQLite: stan panelu — spory, rozmowy, wiadomości, kolejka zadań.

Treść książek leży w plikach — tu tylko to, co redaktor ustala i co agent
zgłasza. Zwykłe sqlite3 zamiast SQLAlchemy: kilka tabel, jeden plik."""

import sqlite3
from contextlib import contextmanager

from app import config

SCHEMAT = """
CREATE TABLE IF NOT EXISTS spory (
  id               INTEGER PRIMARY KEY,
  czego_dotyczy    TEXT NOT NULL,
  warunek          TEXT NOT NULL DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'otwarty',  -- otwarty | rozstrzygniety | odrzucony
  przyjeta_wartosc TEXT,
  skad             TEXT,                              -- ksiazka | redakcja
  wiadomosc_id     INTEGER,
  utworzono        TEXT NOT NULL DEFAULT (datetime('now')),
  rozstrzygnieto   TEXT
);
CREATE TABLE IF NOT EXISTS spor_opcje (
  spor_id  INTEGER NOT NULL REFERENCES spory(id),
  ksiazka  TEXT NOT NULL,
  strona   INTEGER,
  wartosc  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS spor_opcje_ksiazka ON spor_opcje(ksiazka);

CREATE TABLE IF NOT EXISTS rozmowy (
  id        INTEGER PRIMARY KEY,
  tytul     TEXT NOT NULL,
  utworzono TEXT NOT NULL DEFAULT (datetime('now'))
);
-- Zakres rozmowy: zmiana działa od następnego pytania.
CREATE TABLE IF NOT EXISTS rozmowa_ksiazki (
  rozmowa_id INTEGER NOT NULL REFERENCES rozmowy(id),
  ksiazka    TEXT NOT NULL,
  PRIMARY KEY (rozmowa_id, ksiazka)
);
CREATE TABLE IF NOT EXISTS wiadomosci (
  id                INTEGER PRIMARY KEY,
  rozmowa_id        INTEGER NOT NULL REFERENCES rozmowy(id),
  rola              TEXT NOT NULL,                     -- user | assistant
  tekst             TEXT NOT NULL DEFAULT '',
  status            TEXT NOT NULL DEFAULT 'gotowa',    -- czeka | w_toku | gotowa | blad
  blad              TEXT,
  poprawiony_tekst  TEXT,                              -- ręczna poprawka redaktora
  ksiazki           TEXT,                              -- zakres w chwili pytania (JSON)
  slad              TEXT,                              -- ślad szukania (JSON), tylko do diagnozy
  utworzono         TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS wiadomosci_status ON wiadomosci(status);
-- Wgrywanie i przewodnik w tle — tekst stron, OCR i model nie mieszczą się
-- w żądaniu HTTP.
-- Prompty edytowane w panelu: tylko dopisujemy, bieżący to ostatni wiersz klucza.
-- tekst NULL = „wróć do domyślnego z kodu".
CREATE TABLE IF NOT EXISTS prompty (
  id        INTEGER PRIMARY KEY,
  klucz     TEXT NOT NULL,
  tekst     TEXT,
  zapisano  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS prompty_klucz ON prompty(klucz, id);

CREATE TABLE IF NOT EXISTS zadania (
  id        INTEGER PRIMARY KEY,
  rodzaj    TEXT NOT NULL,                             -- przetworz | przewodnik
  ksiazka   TEXT NOT NULL,
  status    TEXT NOT NULL DEFAULT 'czeka',             -- czeka | w_toku | gotowe | blad
  blad      TEXT,
  utworzono TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@contextmanager
def polaczenie():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # timeout: panel i proces roboczy piszą do jednego pliku naraz.
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMAT)
    try:
        yield con
        con.commit()
    finally:
        con.close()
