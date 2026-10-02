"""Ustawienia z .env i zmiennych środowiska.

Bez pydantic-settings: kilka zmiennych nie uzasadnia zależności.
Zmienna środowiska wygrywa z .env — tak działa docker-compose.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _wczytaj_env(sciezka: Path) -> None:
    if not sciezka.exists():
        return
    for linia in sciezka.read_text(encoding="utf-8").splitlines():
        linia = linia.strip()
        if not linia or linia.startswith("#") or "=" not in linia:
            continue
        klucz, _, wartosc = linia.partition("=")
        os.environ.setdefault(klucz.strip(), wartosc.strip().strip('"').strip("'"))


_wczytaj_env(ROOT / ".env")

DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
ZRODLA_DIR = DATA_DIR / "zrodla"
DB_PATH = DATA_DIR / "ogrodnik.db"

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# Modele wybieramy na testach (etap 4); do tego czasu wartości z ogrodnik4.
ANSWER_MODEL = os.environ.get("ANSWER_MODEL", "")
ANALYSIS_MODEL = os.environ.get("ANALYSIS_MODEL", "")

AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "")

# Odczyt tabel z obrazu strony (dwa wywołania na stronę). W ogrodnik4 szedł
# modelem odpowiedzi i na nim mierzono s. 8 programu ochrony (6/6 wpisów).
TABELE_MODEL = os.environ.get("TABELE_MODEL") or ANSWER_MODEL or "gpt-4o"
