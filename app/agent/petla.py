"""Pętla narzędzi i ślad — wspólne dla orkiestratora i subagenta.

Kod pilnuje tu tylko dwóch rzeczy z trzech (trzecia, zakres, siedzi
w narzędziach): budżetu rund i zapisu śladu. Treści nie ogląda."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from openai import OpenAI

from app import config

_openai = OpenAI(api_key=config.OPENAI_API_KEY)

KONIEC_BUDZETU = (
    "Budżet wywołań narzędzi się skończył. Odpowiedz teraz z tym, co już masz; "
    "jeśli czegoś nie sprawdziłeś, powiedz to wprost."
)


@dataclass
class Narzedzie:
    nazwa: str
    opis: str
    parametry: dict
    funkcja: Callable[..., dict | str]

    def schemat(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.nazwa, "description": self.opis, "parameters": self.parametry},
        }


@dataclass
class Slad:
    """Co agent szukał i czytał — tylko do diagnozy, redaktor tego nie widzi."""

    zdarzenia: list[dict] = field(default_factory=list)
    zuzycie: dict[str, dict[str, int]] = field(default_factory=dict)
    _blokada: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _start: float = field(default_factory=time.monotonic, repr=False)

    def zdarzenie(self, **dane) -> None:
        with self._blokada:
            self.zdarzenia.append({"t": round(time.monotonic() - self._start, 2), **dane})

    def zuzyte(self, model: str, usage) -> None:
        cache = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        with self._blokada:
            z = self.zuzycie.setdefault(model, {"wejscie": 0, "z_cache": 0, "wyjscie": 0, "wywolan": 0})
            z["wejscie"] += usage.prompt_tokens
            z["z_cache"] += cache
            z["wyjscie"] += usage.completion_tokens
            z["wywolan"] += 1

    def koszt(self) -> float | None:
        """Koszt w USD albo None, gdy któregoś modelu nie ma w cenniku."""
        razem = 0.0
        for model, z in self.zuzycie.items():
            # Najdłuższa pasująca nazwa — „gpt-5.4-mini-…" nie może dostać ceny „gpt-5.4".
            pasujace = [n for n in config.CENY if model.startswith(n)]
            cena = config.CENY[max(pasujace, key=len)] if pasujace else None
            if cena is None:
                return None
            wej, cache, wyj = cena
            razem += ((z["wejscie"] - z["z_cache"]) * wej + z["z_cache"] * cache + z["wyjscie"] * wyj) / 1e6
        return razem

    def do_json(self) -> dict:
        return {
            "czas_s": round(time.monotonic() - self._start, 1),
            "zuzycie": self.zuzycie,
            "koszt_usd": self.koszt(),
            "zdarzenia": self.zdarzenia,
        }


def _wykonaj(narzedzie: Narzedzie, argumenty: str, slad: Slad, kto: str) -> str:
    try:
        arg = json.loads(argumenty or "{}")
        wynik = narzedzie.funkcja(**arg)
    except Exception as e:  # zły argument od modelu — oddajemy mu błąd, niech poprawi
        arg, wynik = argumenty, {"blad": f"{type(e).__name__}: {e}"}
    tekst = wynik if isinstance(wynik, str) else json.dumps(wynik, ensure_ascii=False)
    slad.zdarzenie(kto=kto, narzedzie=narzedzie.nazwa, argumenty=arg, znakow=len(tekst))
    return tekst


def petla(
    model: str,
    wiadomosci: list[dict],
    narzedzia: list[Narzedzie],
    limit_rund: int,
    slad: Slad,
    kto: str,
    wymus_narzedzie: bool = False,
) -> str:
    """Model woła narzędzia, aż sam uzna, że wie dość, albo skończy się budżet.

    Wywołania z jednej rundy idą równolegle — orkiestrator puszcza tak
    subagentów na kilka książek naraz."""
    po_nazwie = {n.nazwa: n for n in narzedzia}
    schematy = [n.schemat() for n in narzedzia]
    for runda in range(limit_rund + 1):
        dodatki = {}
        if runda < limit_rund:
            dodatki["tools"] = schematy
            if runda == 0 and wymus_narzedzie:
                dodatki["tool_choice"] = "required"
        else:
            slad.zdarzenie(kto=kto, budzet="wyczerpany")
            wiadomosci.append({"role": "user", "content": KONIEC_BUDZETU})
        odp = _openai.chat.completions.create(model=model, messages=wiadomosci, **dodatki)
        slad.zuzyte(odp.model, odp.usage)
        msg = odp.choices[0].message
        if not msg.tool_calls:
            return (msg.content or "").strip()

        wiadomosci.append({
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
        })
        with ThreadPoolExecutor(max_workers=8) as pula:
            wyniki = list(pula.map(
                lambda tc: _wykonaj(po_nazwie[tc.function.name], tc.function.arguments, slad, kto)
                if tc.function.name in po_nazwie
                else json.dumps({"blad": f"nie ma narzędzia {tc.function.name}"}),
                msg.tool_calls,
            ))
        for tc, wynik in zip(msg.tool_calls, wyniki):
            wiadomosci.append({"role": "tool", "tool_call_id": tc.id, "content": wynik})
    return ""  # nieosiągalne: ostatnia runda idzie bez narzędzi
