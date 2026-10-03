"""Trasy panelu. Trzy ekrany: Pracownia, Biblioteka, Do ustalenia.

Redaktor ma robić trzy rzeczy: dodać książkę, zapytać, rozstrzygnąć spór.
Wygląd i układ z ogrodnik4; dane nowe — książki w plikach, reszta w SQLite."""

import json
import re
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import rozmowy, spory, worker
from app.api import widok
from app.ingest import zapis

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["odpowiedz_html"] = widok.odpowiedz_html
templates.env.globals["zrodla_odpowiedzi"] = widok.zrodla_odpowiedzi

# Ile wątków w pasku po lewej, zanim pojawi się „Pokaż więcej".
POKAZ_ROZMOW = 20
ID_KSIAZKI = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def _wspolne() -> dict:
    return {"liczba_sporow": len(spory.lista(status="otwarty"))}


def _ksiazka(id: str) -> dict:
    # Id trafia do ścieżki na dysku — tylko slug, nic, co wyjdzie z data/zrodla.
    if not ID_KSIAZKI.match(id) or not (zapis.katalog(id) / "meta.json").exists():
        raise HTTPException(404, "Nie ma takiej książki")
    return {**zapis.czytaj_meta(id), "id": id}


def _pogrupuj(ksiazki: list[dict]) -> list[tuple[str | None, list[dict]]]:
    """Książki w grupach po kategoriach — zaznaczenie kategorii bierze je
    wszystkie naraz, jak w NotebookLM. Książka z kilkoma kategoriami stoi
    w każdej z nich (pola wyboru trzymają się razem — skrypt w chat.html).
    Bez kategorii — na końcu, bez nagłówka."""
    grupy: dict[str, list[dict]] = {}
    bez: list[dict] = []
    for k in ksiazki:
        for kategoria in k.get("kategorie") or []:
            grupy.setdefault(kategoria, []).append(k)
        if not k.get("kategorie"):
            bez.append(k)
    wynik: list[tuple[str | None, list[dict]]] = sorted(grupy.items())
    if bez:
        wynik.append((None, bez))
    return wynik


def _kategorie(tekst: str) -> list[str]:
    return [k.strip() for k in tekst.split(",") if k.strip()]


# ---------- Pracownia ----------

def _pracownia(request: Request, rozmowa: dict | None, historia: int, podglad: str | None = None,
               f: str = "") -> HTMLResponse:
    gotowe = [k for k in zapis.lista() if k.get("status") == "gotowa"]
    tytuly = {k["id"]: k.get("tytul", k["id"]) for k in zapis.lista()}
    ile = max(POKAZ_ROZMOW, min(historia, 500))
    lista, starsze = rozmowy.lista(ile)
    if rozmowa and all(r["id"] != rozmowa["id"] for r in lista):
        lista.append(rozmowa)
    wiadomosci = rozmowy.wiadomosci(rozmowa["id"]) if rozmowa else []
    wszystkie_spory = spory.lista()
    for w in wiadomosci:
        w["spory"] = [s for s in wszystkie_spory if s["wiadomosc_id"] == w["id"]] if w["rola"] == "assistant" else []
        w["statusy"] = _statusy_w_chwili(wszystkie_spory, w["utworzono"])
    return templates.TemplateResponse(request, "chat.html", {
        "strona": "pytania",
        "rozmowy": lista, "starsze": starsze, "nastepne": ile + POKAZ_ROZMOW,
        "ksiazki": gotowe, "pogrupowane": _pogrupuj(gotowe), "tytuly": tytuly,
        "rozmowa": rozmowa, "wiadomosci": wiadomosci,
        "czeka": any(w["status"] in ("czeka", "w_toku") for w in wiadomosci),
        "podglad": _podglad(podglad, f) if podglad else None,
        **_wspolne(),
    })


def _statusy_w_chwili(wszystkie: list[dict], chwila: str) -> dict[int, str]:
    """Stan sporów, gdy odpowiedź powstawała. Stare odpowiedzi się nie
    zmieniają: wartość, która była sporna, nie może po rozstrzygnięciu
    dostać etykiety „ustalenie redakcji" — zwłaszcza ta, której nie przyjęto."""
    statusy = {}
    for s in wszystkie:
        decyzja_pozniej = s["rozstrzygnieto"] and s["rozstrzygnieto"] >= chwila
        statusy[s["id"]] = "otwarty" if decyzja_pozniej else s["status"]
    return statusy


def _podglad(podglad: str, fraza: str) -> dict | None:
    """Tekst strony z zaznaczonymi liczbami ze zdania odpowiedzi — bez obrazu
    PDF (proces.md, Panel)."""
    id, _, numer = podglad.partition(":")
    if not numer.isdigit() or not ID_KSIAZKI.match(id):
        return None
    sciezka = zapis.katalog(id) / "strony" / f"{int(numer):04d}.txt"
    if not sciezka.exists():
        return None
    meta = zapis.czytaj_meta(id)
    n = int(numer)
    return {
        "ksiazka": id, "tytul": meta.get("tytul", id), "strona": n,
        "kawalki": widok.zaznacz(sciezka.read_text(encoding="utf-8"), fraza),
        "tabela": n in meta.get("strony_tabela", []), "ocr": n in meta.get("strony_ocr", []),
        "poprzednia": n - 1 if n > 1 else None,
        "nastepna": n + 1 if n < meta.get("liczba_stron", 0) else None,
    }


@router.get("/", response_class=HTMLResponse)
def pracownia(request: Request, historia: int = POKAZ_ROZMOW):
    return _pracownia(request, None, historia)


@router.get("/rozmowy/{rozmowa_id}", response_class=HTMLResponse)
def rozmowa(request: Request, rozmowa_id: int, podglad: str | None = None, f: str = "",
            historia: int = POKAZ_ROZMOW):
    r = rozmowy.pobierz(rozmowa_id)
    if r is None:
        raise HTTPException(404, "Nie ma takiej rozmowy")
    return _pracownia(request, r, historia, podglad, f)


@router.get("/rozmowy/{rozmowa_id}/stan")
def stan_rozmowy(rozmowa_id: int):
    """Do odświeżania strony, gdy odpowiedź jest gotowa — zamiast przeładowywać
    co 3 s całą stronę razem z otwartym podglądem."""
    return {"czeka": any(w["status"] in ("czeka", "w_toku") for w in rozmowy.wiadomosci(rozmowa_id))}


@router.post("/pytania")
def nowe_pytanie(pytanie: str = Form(...), ksiazki: list[str] = Form(default=[])):
    tekst = pytanie.strip()
    if not tekst:
        return RedirectResponse("/", status_code=303)
    # Nic nie zaznaczone = wszystkie gotowe książki (tak jak domyślnie w formularzu).
    zakres = ksiazki or [k["id"] for k in zapis.lista() if k.get("status") == "gotowa"]
    id = rozmowy.nowa(tekst, zakres)
    rozmowy.zapytaj(id, tekst)
    return RedirectResponse(f"/rozmowy/{id}", status_code=303)


@router.post("/rozmowy/{rozmowa_id}/pytania")
def kolejne_pytanie(rozmowa_id: int, pytanie: str = Form(...)):
    if rozmowy.pobierz(rozmowa_id) is None:
        raise HTTPException(404, "Nie ma takiej rozmowy")
    if pytanie.strip():
        rozmowy.zapytaj(rozmowa_id, pytanie.strip())
    return RedirectResponse(f"/rozmowy/{rozmowa_id}", status_code=303)


@router.post("/rozmowy/{rozmowa_id}/zakres")
def zmien_zakres(rozmowa_id: int, ksiazki: list[str] = Form(default=[])):
    """Działa od następnego pytania; wcześniejsze odpowiedzi mają zapisany
    zakres, z którego powstały."""
    if rozmowy.pobierz(rozmowa_id) is None:
        raise HTTPException(404, "Nie ma takiej rozmowy")
    rozmowy.ustaw_zakres(rozmowa_id, ksiazki)
    return RedirectResponse(f"/rozmowy/{rozmowa_id}", status_code=303)


@router.post("/rozmowy/{rozmowa_id}/wiadomosci/{wiadomosc_id}")
def popraw_odpowiedz(rozmowa_id: int, wiadomosc_id: int, tekst: str = Form("")):
    w = rozmowy.wiadomosc(wiadomosc_id)
    if w is None or w["rozmowa_id"] != rozmowa_id:
        raise HTTPException(404, "Nie ma takiej wiadomości")
    rozmowy.popraw(wiadomosc_id, tekst)
    return RedirectResponse(f"/rozmowy/{rozmowa_id}", status_code=303)


# ---------- Biblioteka ----------

@router.get("/zrodla", response_class=HTMLResponse)
def biblioteka(request: Request, szukaj: str = "", kategoria: str | None = None, blad: str | None = None):
    wszystkie = zapis.lista()
    fraza = szukaj.strip().lower()
    wybrane = [
        k for k in wszystkie
        if (not fraza or fraza in k.get("tytul", "").lower() or fraza in k.get("autor", "").lower())
        and (not kategoria or kategoria in (k.get("kategorie") or []))
    ]
    kategorie: dict[str, int] = {}
    for k in wszystkie:
        for kat in k.get("kategorie") or []:
            kategorie[kat] = kategorie.get(kat, 0) + 1
    teksty = {
        k["id"]: (zapis.katalog(k["id"]) / "original.txt").read_text(encoding="utf-8")
        for k in wybrane if k.get("rodzaj") == "tekst" and (zapis.katalog(k["id"]) / "original.txt").exists()
    }
    return templates.TemplateResponse(request, "zrodla.html", {
        "strona": "zrodla", "ksiazki": wybrane, "wszystkich": len(wszystkie), "teksty": teksty,
        "szukaj": szukaj.strip(), "kategoria": kategoria, "kategorie": sorted(kategorie.items()),
        "blad": blad, **_wspolne(),
    })


@router.post("/zrodla")
async def dodaj(tytul: str = Form(...), kategorie: str = Form(""), autor: str = Form(""),
                plik: UploadFile | None = None, tekst: str = Form("")):
    """Książka od razu idzie do przetworzenia — tekst stron, potem przewodnik."""
    pdf = await plik.read() if plik is not None and plik.filename else None
    if not pdf and not tekst.strip():
        return RedirectResponse("/zrodla?blad=Wybierz+plik+PDF+albo+wklej+tekst", status_code=303)
    if pdf and not pdf.startswith(b"%PDF"):
        return RedirectResponse("/zrodla?blad=To+nie+jest+plik+PDF", status_code=303)
    id = zapis.utworz(tytul.strip(), autor.strip(), _kategorie(kategorie), pdf=pdf, tekst=None if pdf else tekst)
    worker.zlec("przetworz", id)
    return RedirectResponse("/zrodla", status_code=303)


@router.get("/zrodla/{id}", response_class=HTMLResponse)
def ksiazka(request: Request, id: str, strona: int = 1, powrot: str | None = None):
    meta = _ksiazka(id)
    liczba = meta.get("liczba_stron", 0)
    biezaca = min(max(strona, 1), liczba) if liczba else 0
    sciezka = zapis.katalog(id) / "strony" / f"{biezaca:04d}.txt"
    przewodnik = zapis.katalog(id) / "ksiazka.md"
    return templates.TemplateResponse(request, "zrodlo.html", {
        "strona": "zrodla", "k": meta, "biezaca": biezaca, "liczba": liczba,
        "tekst": sciezka.read_text(encoding="utf-8") if sciezka.exists() else "",
        "tabela": biezaca in meta.get("strony_tabela", []), "ocr": biezaca in meta.get("strony_ocr", []),
        "przewodnik": przewodnik.read_text(encoding="utf-8") if przewodnik.exists() else "",
        # Tylko powrót wewnątrz panelu — nie przekierowujemy na cudzy adres.
        "powrot": powrot if powrot and powrot.startswith("/rozmowy/") else None,
        **_wspolne(),
    })


@router.post("/zrodla/{id}/edytuj")
def edytuj(id: str, tytul: str = Form(...), kategorie: str = Form(""), autor: str = Form(""),
           tekst: str = Form("")):
    """Tytuł, autor, kategorie — a dla wklejonego tekstu także treść. Zmiana
    treści przetwarza książkę od nowa; sama zmiana kategorii — nie."""
    meta = _ksiazka(id)
    meta.pop("id")
    meta.update(tytul=tytul.strip() or meta.get("tytul", id), autor=autor.strip(), kategorie=_kategorie(kategorie))
    zapis.zapisz_meta(id, meta)
    oryginal = zapis.katalog(id) / "original.txt"
    if meta.get("rodzaj") == "tekst" and tekst.strip() and oryginal.exists() \
            and tekst != oryginal.read_text(encoding="utf-8"):
        oryginal.write_text(tekst, encoding="utf-8")
        worker.zlec("przetworz", id)
    return RedirectResponse("/zrodla", status_code=303)


@router.post("/zrodla/{id}/przetworz")
def przetworz(id: str):
    _ksiazka(id)
    worker.zlec("przetworz", id)
    return RedirectResponse("/zrodla", status_code=303)


@router.post("/zrodla/{id}/przewodnik")
def zapisz_przewodnik(id: str, tekst: str = Form(...)):
    """Poprawka przewodnika przez redaktora — ponowne przetworzenie jej nie rusza."""
    _ksiazka(id)
    (zapis.katalog(id) / "ksiazka.md").write_text(tekst.strip() + "\n", encoding="utf-8")
    return RedirectResponse(f"/zrodla/{id}", status_code=303)


@router.post("/zrodla/{id}/przewodnik/generuj")
def generuj_przewodnik(id: str):
    _ksiazka(id)
    worker.zlec("przewodnik", id)
    return RedirectResponse(f"/zrodla/{id}", status_code=303)


@router.get("/zrodla/{id}/plik")
def plik(id: str):
    meta = _ksiazka(id)
    kat = zapis.katalog(id)
    sciezka = kat / ("original.pdf" if (kat / "original.pdf").exists() else "original.txt")
    nazwa = re.sub(r"[^\w\- ]", "", meta.get("tytul", id)).strip()[:80] or id
    return FileResponse(sciezka, filename=f"{nazwa}{sciezka.suffix}")


# ---------- Do ustalenia ----------

@router.get("/spory", response_class=HTMLResponse)
def lista_sporow(request: Request):
    wszystkie = spory.lista()
    tytuly = {k["id"]: k.get("tytul", k["id"]) for k in zapis.lista()}
    return templates.TemplateResponse(request, "spory.html", {
        "strona": "spory",
        "otwarte": [s for s in wszystkie if s["status"] == "otwarty"],
        "rozstrzygniete": [s for s in reversed(wszystkie) if s["status"] == "rozstrzygniety"],
        "odrzucone": [s for s in reversed(wszystkie) if s["status"] == "odrzucony"],
        "tytuly": tytuly, **_wspolne(),
    })


@router.post("/spory/{spor_id}")
def rozstrzygnij(spor_id: int, wybor: str = Form(...), wlasna: str = Form(""), powrot: str = Form("/spory")):
    """Wybór A, B, własna wartość albo „to nie jest spór". Działa od
    następnego pytania; stare odpowiedzi się nie zmieniają."""
    spor = spory.pobierz(spor_id)
    if spor is None:
        raise HTTPException(404, "Nie ma takiego sporu")
    cel = powrot if powrot.startswith(("/spory", "/rozmowy/")) else "/spory"
    if wybor == "__odrzuc__":
        spory.odrzuc(spor_id)
    elif wybor == "__wlasna__":
        if not wlasna.strip():
            return RedirectResponse(cel, status_code=303)
        spory.rozstrzygnij(spor_id, wlasna.strip()[:255], "redakcja")
    elif wybor.isdigit() and int(wybor) < len(spor["opcje"]):
        spory.rozstrzygnij(spor_id, spor["opcje"][int(wybor)]["wartosc"], "ksiazka")
    return RedirectResponse(cel, status_code=303)


templates.env.filters["fromjson"] = lambda s: json.loads(s) if s else None
