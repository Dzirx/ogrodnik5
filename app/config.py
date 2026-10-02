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

# Przewodnik ksiazka.md: jedno wywołanie na książkę (albo na kawałek
# grubej książki). Porównanie na Sułku 2026-10-02: gpt-4o-mini przesuwał
# mapę stron i zmyślał słowa, gpt-4.1 sklejał 14 stron w wiersz, gpt-5.5
# najdokładniejszy, gpt-5.4-mini prawie tak samo dobry za ułamek ceny.
PRZEWODNIK_MODEL = os.environ.get("PRZEWODNIK_MODEL") or "gpt-5.4-mini"
# Ile stron idzie do jednego wywołania. Zmierzone tylko na książkach
# do ~110 stron — dla grubej książki do sprawdzenia (proces.md, „Otwarte").
PRZEWODNIK_STRON_NA_KAWALEK = int(os.environ.get("PRZEWODNIK_STRON_NA_KAWALEK", "300"))

# Limity narzędzi agenta (etap 3). Luźne na start — właściwe ustalimy
# ze śladów testów w etapie 4.
SZUKAJ_LIMIT_TRAFIEN = int(os.environ.get("SZUKAJ_LIMIT_TRAFIEN", "20"))
CZYTAJ_LIMIT_STRON = int(os.environ.get("CZYTAJ_LIMIT_STRON", "5"))

# Agent (etap 4). Modele wybieramy na testach; start od taniego.
ORKIESTRATOR_MODEL = os.environ.get("ORKIESTRATOR_MODEL") or "gpt-5.4-mini"
SUBAGENT_MODEL = os.environ.get("SUBAGENT_MODEL") or "gpt-5.4-mini"
# Budżet: ile rund wywołań narzędzi, zanim kod każe odpowiedzieć z tym, co
# jest. Luźny na start — właściwy ustalimy ze śladów (proces.md, „Otwarte").
ORKIESTRATOR_LIMIT_RUND = int(os.environ.get("ORKIESTRATOR_LIMIT_RUND", "6"))
SUBAGENT_LIMIT_RUND = int(os.environ.get("SUBAGENT_LIMIT_RUND", "12"))

# Ceny za 1M tokenów (wejście, wejście z cache, wyjście) — tylko do raportu
# kosztu w testach. Model spoza tabeli: koszt nieznany, liczymy same tokeny.
CENY = {
    "gpt-5.4-mini": (0.75, 0.075, 4.50),
    # gpt-5.4: tylko cena wejścia z cennika ($2,50); cache i wyjście do
    # potwierdzenia — przyjęte w tej samej proporcji co mini (×1/10, ×6).
    "gpt-5.4": (2.50, 0.25, 15.00),
}
