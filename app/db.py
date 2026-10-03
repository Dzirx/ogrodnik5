"""SQLite: stan panelu (spory; w etapie 6 rozmowy i wiadomości).

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
"""


@contextmanager
def polaczenie():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMAT)
    try:
        yield con
        con.commit()
    finally:
        con.close()
