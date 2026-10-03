"""Przebieg pytań testowych: odpowiedź i ślad obok oczekiwań.

    python testy/uruchom.py testy/sulek.yaml --ksiazki sulek-pomidory
    python testy/uruchom.py testy/sulek.yaml --ksiazki sulek-pomidory --tylko rozstaw wilki
    python testy/uruchom.py testy/dwie-ksiazki.yaml     # zakres z pola "ksiazki" pytania

Ocenia człowiek, czytając raport — skrypt niczego nie punktuje, bo
„czy odpowiedź zawiera fakt" to ocena treści, a tej kod nie robi."""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.agent.agent import odpowiedz  # noqa: E402


def _przebieg(test: dict, ksiazki: list[str] | None) -> dict:
    # Pole "ksiazki" w pytaniu wygrywa z --ksiazki: pytania na dwie książki
    # i na jedną mogą leżeć w jednym pliku.
    ksiazki = test.get("ksiazki") or ksiazki
    if not ksiazki:
        raise SystemExit(f"{test['id']}: brak zakresu — podaj --ksiazki albo pole ksiazki")
    pytania = test.get("rozmowa") or [test["pytanie"]]
    historia, tury = [], []
    for pytanie in pytania:
        try:
            wynik = odpowiedz(ksiazki, pytanie, historia)
        except Exception as e:
            # Jeden błąd API (np. brak środków) nie może zabrać wyników
            # pozostałych testów — zapisujemy go przy tym teście.
            tury.append({"pytanie": pytanie, "odpowiedz": f"BŁĄD: {type(e).__name__}: {e}"[:400],
                         "slad": {"czas_s": 0, "zuzycie": {}, "koszt_usd": 0.0, "zdarzenia": []}})
            break
        tury.append({"pytanie": pytanie, "odpowiedz": wynik.tekst, "slad": wynik.slad.do_json()})
        historia += [{"role": "user", "content": pytanie}, {"role": "assistant", "content": wynik.tekst}]
    return {"test": test, "ksiazki": ksiazki, "tury": tury}


def _podsumowanie_sladu(s: dict) -> tuple[list[str], list[str], int, bool]:
    frazy, strony = [], []
    for z in s["zdarzenia"]:
        if z.get("narzedzie") == "szukaj":
            frazy.append(z["argumenty"].get("fraza", "?") if isinstance(z["argumenty"], dict) else "?")
        if z.get("narzedzie") == "czytaj_strony" and isinstance(z["argumenty"], dict):
            od = z["argumenty"].get("od")
            do = z["argumenty"].get("do") or od
            strony.append(f"{od}" if od == do else f"{od}–{do}")
    narzedzi = sum(1 for z in s["zdarzenia"] if "narzedzie" in z)
    budzet = any(z.get("budzet") for z in s["zdarzenia"])
    return frazy, strony, narzedzi, budzet


def _koszt(s: dict) -> str:
    return f"${s['koszt_usd']:.4f}" if s["koszt_usd"] is not None else "?"


def raport(wyniki: list[dict]) -> str:
    ksiazki = sorted({k for w in wyniki for k in w["ksiazki"]})
    linie = [
        f"# Testy {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Książki: {', '.join(ksiazki)}. Orkiestrator: `{config.ORKIESTRATOR_MODEL}`, "
        f"subagent: `{config.SUBAGENT_MODEL}`. Limity rund: {config.ORKIESTRATOR_LIMIT_RUND} / "
        f"{config.SUBAGENT_LIMIT_RUND}.",
        "",
        "| test | rodzaj | czas | narzędzia | koszt | budżet |",
        "|---|---|---|---|---|---|",
    ]
    for w in wyniki:
        for i, t in enumerate(w["tury"]):
            _, _, narzedzi, budzet = _podsumowanie_sladu(t["slad"])
            nazwa = w["test"]["id"] + (f" ({i + 1})" if len(w["tury"]) > 1 else "")
            linie.append(f"| {nazwa} | {w['test']['rodzaj']} | {t['slad']['czas_s']} s | {narzedzi} | "
                         f"{_koszt(t['slad'])} | {'WYCZERPANY' if budzet else ''} |")
    for w in wyniki:
        test = w["test"]
        linie += ["", "---", "", f"## {test['id']} ({test['rodzaj']})", "",
                  f"*Zakres:* {', '.join(w['ksiazki'])}", ""]
        for t in w["tury"]:
            frazy, strony, _, _ = _podsumowanie_sladu(t["slad"])
            linie += [f"**Pytanie:** {t['pytanie']}", "", t["odpowiedz"], "",
                      f"*Szukał:* {', '.join(frazy) or '—'}  ", f"*Czytał s.:* {', '.join(strony) or '—'}", ""]
        linie.append("**Oczekiwane:**")
        for klucz in ("musi", "nie_wolno"):
            for pozycja in test.get(klucz, []):
                linie.append(f"- {'musi' if klucz == 'musi' else 'NIE WOLNO'}: {pozycja}")
        for p in test.get("pokrycie", []):
            linie.append(f"- pokrycie: {p['temat']} (s. {', '.join(map(str, p['strony']))})")
        strony = test.get("strony")
        if isinstance(strony, dict):  # dwie książki: {id: [strony]}
            for id, numery in strony.items():
                linie.append(f"- strony {id}: {', '.join(map(str, numery)) or '—'}")
        elif strony:
            linie.append(f"- strony: {', '.join(map(str, strony))}")
        if test.get("uwagi"):
            linie.append(f"- uwagi: {test['uwagi'].strip()}")
    return "\n".join(linie) + "\n"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("plik", type=Path)
    p.add_argument("--ksiazki", nargs="+", help="zakres dla pytań bez pola ksiazki")
    p.add_argument("--tylko", nargs="*", help="id testów do uruchomienia")
    p.add_argument("--rownolegle", type=int, default=4)
    a = p.parse_args()

    testy = yaml.safe_load(a.plik.read_text(encoding="utf-8"))
    if a.tylko:
        testy = [t for t in testy if t["id"] in a.tylko]
    with ThreadPoolExecutor(max_workers=a.rownolegle) as pula:
        wyniki = list(pula.map(lambda t: _przebieg(t, a.ksiazki), testy))

    # Sekundy i nazwa pliku: dwa przebiegi w tej samej minucie nadpisywały raport.
    katalog = Path(__file__).parent / "wyniki" / f"{datetime.now():%Y-%m-%d_%H%M%S}_{a.plik.stem}"
    (katalog / "slady").mkdir(parents=True, exist_ok=True)
    for w in wyniki:
        (katalog / "slady" / f"{w['test']['id']}.json").write_text(
            json.dumps(w, ensure_ascii=False, indent=2), encoding="utf-8")
    (katalog / "raport.md").write_text(raport(wyniki), encoding="utf-8")

    koszty = [t["slad"]["koszt_usd"] for w in wyniki for t in w["tury"]]
    razem = f"${sum(koszty):.3f}" if None not in koszty else "?"
    print(f"{katalog / 'raport.md'}  ({len(wyniki)} testów, koszt {razem})")


if __name__ == "__main__":
    main()
