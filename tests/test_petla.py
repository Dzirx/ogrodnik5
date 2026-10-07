import json

import pytest

from app.agent import petla as p


class _Wywolanie:
    def __init__(self, id, nazwa, argumenty):
        self.id = id
        self.function = type("F", (), {"name": nazwa, "arguments": json.dumps(argumenty)})

    def model_dump(self):
        return {"id": self.id, "type": "function",
                "function": {"name": self.function.name, "arguments": self.function.arguments}}


def _odp(tresc=None, wywolania=None):
    msg = type("M", (), {"content": tresc, "tool_calls": wywolania})
    usage = type("U", (), {"prompt_tokens": 100, "completion_tokens": 10,
                           "prompt_tokens_details": type("D", (), {"cached_tokens": 50})})
    return type("R", (), {"model": "gpt-5.4-mini-2026-03-17", "usage": usage,
                          "choices": [type("C", (), {"message": msg})]})


@pytest.fixture
def model(monkeypatch):
    kolejka, zapytania = [], []

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    zapytania.append(kw)
                    return kolejka.pop(0)

    monkeypatch.setattr(p, "_openai", Fake)
    return kolejka, zapytania


def _narzedzie():
    return p.Narzedzie("szukaj", "", {"type": "object", "properties": {}},
                       lambda fraza: {"trafienia": [fraza]})


def test_narzedzie_potem_odpowiedz_i_slad(model):
    kolejka, zapytania = model
    kolejka += [_odp(wywolania=[_Wywolanie("1", "szukaj", {"fraza": "ogław"})]), _odp("Odpowiedź.")]
    slad = p.Slad()
    assert p.petla("m", [{"role": "user", "content": "?"}], [_narzedzie()], 5, slad, "test",
                   wymus_narzedzie=True) == "Odpowiedź."
    assert zapytania[0]["tool_choice"] == "required" and "tool_choice" not in zapytania[1]
    assert zapytania[1]["messages"][-1] == {"role": "tool", "tool_call_id": "1",
                                             "content": '{"trafienia": ["ogław"]}'}
    assert [z["narzedzie"] for z in slad.zdarzenia if "narzedzie" in z] == ["szukaj"]
    # 2 wywołania × (50 zwykłych × 0,75 + 50 z cache × 0,075 + 10 wyjścia × 4,5) / 1e6
    assert slad.koszt() == pytest.approx(2 * (50 * 0.75 + 50 * 0.075 + 10 * 4.5) / 1e6)


def test_budzet_wymusza_odpowiedz_bez_narzedzi(model):
    kolejka, zapytania = model
    kolejka += [_odp(wywolania=[_Wywolanie(str(i), "szukaj", {"fraza": "x"})]) for i in range(2)]
    kolejka += [_odp("Z tym, co mam.")]
    slad = p.Slad()
    assert p.petla("m", [], [_narzedzie()], 2, slad, "test") == "Z tym, co mam."
    assert "tools" not in zapytania[2]
    assert zapytania[2]["messages"][-1]["content"] == p.KONIEC_BUDZETU
    assert any(z.get("budzet") == "wyczerpany" for z in slad.zdarzenia)


def test_zly_argument_wraca_do_modelu_jako_blad(model):
    kolejka, zapytania = model
    kolejka += [_odp(wywolania=[_Wywolanie("1", "szukaj", {"zle": 1})]), _odp("ok")]
    p.petla("m", [], [_narzedzie()], 3, p.Slad(), "test")
    assert "blad" in json.loads(zapytania[1]["messages"][-1]["content"])



def test_wariant_jeden_agent_ma_szukaj_i_czytaj_na_calym_zakresie(model, monkeypatch, tmp_path):
    from app import config
    from app.agent import agent
    from app.ingest import zapis

    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ogrodnik.db")
    monkeypatch.setattr(config, "AGENT", "jeden")
    a = zapis.wgraj_tekst("Pomidor lubi ciepło.", "Książka A")
    b = zapis.wgraj_tekst("Pomidor lubi światło.", "Książka B")
    kolejka, zapytania = model
    # Trzecia odpowiedź: przy dwóch książkach bez zgłoszenia kod raz pyta o spór.
    kolejka += [_odp(wywolania=[_Wywolanie("1", "szukaj", {"fraza": "pomidor"})]), _odp("Gotowe [ksiazka-a s. 1]."),
                _odp(wywolania=[_Wywolanie("2", "brak_sporu", {})])]
    wynik = agent.odpowiedz([a, b], "Co lubi pomidor?", [{"role": "user", "content": "wcześniej"}])
    nazwy = [t["function"]["name"] for t in zapytania[0]["tools"]]
    assert nazwy == ["szukaj", "czytaj_strony", "lista", "zglos_spor", "poza_zakresem"]  # bez zapytaj_ksiazke
    assert zapytania[0]["tool_choice"] == "required"
    # Historia rozmowy idzie wprost do agenta, a przewodniki obu książek są w prompcie.
    assert zapytania[0]["messages"][1] == {"role": "user", "content": "wcześniej"}
    assert "=== ksiazka-a" in zapytania[0]["messages"][0]["content"] and "=== ksiazka-b" in zapytania[0]["messages"][0]["content"]
    # Wynik szukania obejmuje obie książki naraz.
    # (lista wiadomości jest ta sama i rośnie dalej — szukamy po roli, nie „ostatniej")
    wyniki = json.loads(next(m for m in zapytania[1]["messages"] if m.get("role") == "tool")["content"])
    assert {t["ksiazka"] for t in wyniki["trafienia"]} == {a, b}
    assert wynik.tekst == "Gotowe [ksiazka-a s. 1]."


def test_wariant_dwa_szukacz_zbiera_a_pisarz_pisze(model, monkeypatch, tmp_path):
    from app import config
    from app.agent import agent
    from app.ingest import zapis

    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ogrodnik.db")
    monkeypatch.setattr(config, "AGENT", "dwa")
    monkeypatch.setattr(config, "SZUKACZ_MODEL", "mini")
    monkeypatch.setattr(config, "PISARZ_MODEL", "duzy")
    a = zapis.wgraj_tekst("Pomidor lubi ciepło.", "Książka A")
    b = zapis.wgraj_tekst("Pomidor lubi światło.", "Książka B")
    kolejka, zapytania = model
    kolejka += [
        _odp(wywolania=[_Wywolanie("1", "szukaj", {"fraza": "pomidor"})]),                    # szukacz szuka
        _odp("[ksiazka-a s. 1] Pomidor lubi ciepło.\n[ksiazka-b s. 1] Pomidor lubi światło."),  # notatki
        _odp(wywolania=[_Wywolanie("2", "brak_sporu", {})]),                                   # kontrola sporu
        _odp("Pomidor lubi ciepło i światło [ksiazka-a s. 1][ksiazka-b s. 1]."),               # pisarz
    ]
    historia = [{"role": "user", "content": "wcześniej"}, {"role": "assistant", "content": "odp"}]
    wynik = agent.odpowiedz([a, b], "Co lubi pomidor?", historia)

    # Zbieranie i kontrola sporu na modelu szukacza, pisanie na modelu pisarza.
    assert [z["model"] for z in zapytania] == ["mini", "mini", "mini", "duzy"]
    szukacz, pisarz = zapytania[0], zapytania[3]
    assert [t["function"]["name"] for t in szukacz["tools"]] == ["szukaj", "czytaj_strony", "lista", "zglos_spor", "poza_zakresem"]
    # Pisarz: bez narzędzi, bez przewodników i tytułów, z rozmową i notatkami.
    assert "tools" not in pisarz
    system = pisarz["messages"][0]["content"]
    assert "=== ksiazka-a" not in system and "Książka A" not in system
    assert pisarz["messages"][1:3] == historia
    ostatnia = pisarz["messages"][-1]["content"]
    assert "PYTANIE REDAKTORA:\nCo lubi pomidor?" in ostatnia and "[ksiazka-a s. 1] Pomidor lubi ciepło." in ostatnia
    # Szukacz widzi rozmowę i przewodniki; notatki trafiają do śladu (diagnoza).
    assert szukacz["messages"][1:3] == historia and "=== ksiazka-a" in szukacz["messages"][0]["content"]
    assert any("notatki" in z for z in wynik.slad.zdarzenia)
    assert wynik.tekst == "Pomidor lubi ciepło i światło [ksiazka-a s. 1][ksiazka-b s. 1]."


def test_prompty_dwa_maja_spojny_protokol_notatek():
    """Szukacz i pisarz muszą znać te same słowa kluczowe notatek — rozjazd
    oznaczałby, że pisarz nie rozumie tego, co oddaje szukacz."""
    from app.agent import agent
    for slowo in ("BRAK", "POZA ZAKRESEM", "SPÓR U", "USTALENIE U"):
        assert slowo in agent.SZUKACZ, slowo
        assert slowo in agent.PISARZ, slowo
    agent.SZUKACZ.format(przewodniki="x", spory="y")     # placeholdery poprawne


def test_prompty_dwa_nie_maja_tokenu_bez_nowego_materialu():
    """Jedno słowo od taniego modelu decydowało, czy pisarz dostanie fakty, a pisarz bez
    materiału przerabiał poprzednią odpowiedź i wymyślał znaczniki (2026-10-06)."""
    from app.agent import agent
    assert "BEZ NOWEGO MATERIAŁU" not in agent.SZUKACZ and "BEZ NOWEGO MATERIAŁU" not in agent.PISARZ
    assert "Nie udało się zebrać materiału" in agent.PISARZ


def _dwie_ksiazki(monkeypatch, tmp_path):
    from app import config
    from app.ingest import zapis

    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "ogrodnik.db")
    monkeypatch.setattr(config, "SZUKACZ_MODEL", "mini")
    monkeypatch.setattr(config, "PISARZ_MODEL", "duzy")
    return (zapis.wgraj_tekst("Pomidor lubi ciepło.", "Książka A"),
            zapis.wgraj_tekst("Pomidor lubi światło.", "Książka B"))


def test_wariant_strony_pisarz_dostaje_dosłowny_tekst_wskazanych_stron(model, monkeypatch, tmp_path):
    from app import config
    from app.agent import agent

    monkeypatch.setattr(config, "AGENT", "strony")
    monkeypatch.setattr(config, "PLANISTA", False)
    a, b = _dwie_ksiazki(monkeypatch, tmp_path)
    kolejka, zapytania = model
    kolejka += [
        _odp(wywolania=[_Wywolanie("1", "szukaj", {"fraza": "pomidor"})]),   # szukacz szuka
        _odp(f"STRONY: {a} 1\nSTRONY: {b} 1\nSTRONY: nie-ma-takiej 3\nBRAK: nawożenia"),
        _odp(wywolania=[_Wywolanie("2", "brak_sporu", {})]),                  # kontrola sporu
        _odp(f"Pomidor lubi ciepło i światło [{a} s. 1][{b} s. 1]."),           # pisarz
    ]
    historia = [{"role": "user", "content": "wcześniej"}, {"role": "assistant", "content": "odp"}]
    wynik = agent.odpowiedz([a, b], "Co lubi pomidor?", historia)

    assert [z["model"] for z in zapytania] == ["mini", "mini", "mini", "duzy"]
    szukacz, pisarz = zapytania[0], zapytania[3]
    assert "STRONY:" in szukacz["messages"][0]["content"]
    # Pisarz: bez narzędzi, bez przewodników i tytułów, z rozmową i dosłownymi stronami.
    assert "tools" not in pisarz
    system = pisarz["messages"][0]["content"]
    assert "=== ksiazka-a" not in system and "Książka A" not in system
    assert pisarz["messages"][1:3] == historia
    ostatnia = pisarz["messages"][-1]["content"]
    assert "PYTANIE REDAKTORA:\nCo lubi pomidor?" in ostatnia
    assert f"=== [{a} s. 1] ===\nPomidor lubi ciepło." in ostatnia
    assert f"=== [{b} s. 1] ===\nPomidor lubi światło." in ostatnia
    # Książka spoza zakresu odpada, uwagi szukacza (BRAK) idą dalej, linie STRONY nie.
    assert "nie-ma-takiej" not in ostatnia and "BRAK: nawożenia" in ostatnia and "STRONY:" not in ostatnia
    assert wynik.tekst.startswith("Pomidor lubi ciepło i światło")
    assert any(z.get("strony") == [f"{a} s. 1", f"{b} s. 1"] for z in wynik.slad.zdarzenia)


def test_wariant_strony_bez_wskazania_pisarz_dostaje_informacje_o_porazce(model, monkeypatch, tmp_path):
    from app import config
    from app.agent import agent

    monkeypatch.setattr(config, "AGENT", "strony")
    monkeypatch.setattr(config, "PLANISTA", False)
    a, _ = _dwie_ksiazki(monkeypatch, tmp_path)
    kolejka, zapytania = model
    kolejka += [_odp(wywolania=[_Wywolanie("1", "szukaj", {"fraza": "pomidor"})]), _odp("coś bez formatu"),
                _odp("Nie udało się zebrać materiału z książek — spróbuj ponownie.")]
    agent.odpowiedz([a], "Co lubi pomidor?")
    # Proza poza formatem odpada — pisarz nie dostaje cudzych zdań, tylko informację o porażce.
    assert "coś bez formatu" not in zapytania[2]["messages"][-1]["content"]
    assert "(szukacz nie wskazał żadnych stron)" in zapytania[2]["messages"][-1]["content"]


def test_numery_stron_i_limit_po_rowno_z_ksiazek(monkeypatch, tmp_path):
    from app import config
    from app.agent import agent
    from app.agent.narzedzia import Zakres
    from app.ingest import zapis

    monkeypatch.setattr(config, "ZRODLA_DIR", tmp_path / "zrodla")
    assert agent._numery_stron("11–14, 20; 3-4, x") == [11, 12, 13, 14, 20, 3, 4]
    a = zapis.wgraj_tekst("jedna strona", "Książka A")
    zakres = Zakres((a,))
    strony, inne = agent._wskazane_strony(f"- STRONY: {a} 1, 1, 5\nBRAK: czegoś\nSTRONY: obca 2", zakres)
    assert strony == {a: [1, 5]} and inne == ["BRAK: czegoś"]   # strona 5 odpadnie dopiero przy czytaniu
    # Szukacz bywa, że wpisuje kilka książek w jednej linii — żadna nie może zginąć.
    b = zapis.wgraj_tekst("druga", "Książka B")
    dwie = agent._wskazane_strony(f"STRONY: {a} 1, 3–4; {b} 2", Zakres((a, b)))[0]
    assert dwie == {a: [1, 3, 4], b: [2]}
    material, wybrane = agent._material_ze_stron(strony, zakres, 12)
    assert material.count("=== [") == 1 and wybrane == [f"{a} s. 1", f"{a} s. 5"]


def test_wariant_strony_planista_ustala_temat_i_forme(model, monkeypatch, tmp_path):
    from app import config
    from app.agent import agent

    monkeypatch.setattr(config, "AGENT", "strony")
    monkeypatch.setattr(config, "PLANISTA", True)
    monkeypatch.setattr(config, "PLANISTA_MODEL", "plan")
    a, b = _dwie_ksiazki(monkeypatch, tmp_path)
    kolejka, zapytania = model
    kolejka += [
        _odp("TEMAT: pomidor, ciepło i światło, szeroko.\nFORMA: post na Facebooku z faktów ze stron."),  # planista
        _odp(wywolania=[_Wywolanie("1", "szukaj", {"fraza": "pomidor"})]),                               # szukacz
        _odp(f"Jasne — mogę, ale nie napiszę posta.\nSTRONY: {a} 1\nSTRONY: {b} 1"),                    # lista z prozą
        _odp(wywolania=[_Wywolanie("2", "brak_sporu", {})]),                                             # kontrola sporu
        _odp(f"Post o pomidorze [{a} s. 1]."),                                                           # pisarz
    ]
    historia = [{"role": "user", "content": "wcześniej"}, {"role": "assistant", "content": "odp"}]
    wynik = agent.odpowiedz([a, b], "napisz o tym post", historia)

    assert [z["model"] for z in zapytania] == ["plan", "mini", "mini", "mini", "duzy"]
    planista, szukacz, pisarz = zapytania[0], zapytania[1], zapytania[4]
    # Planista: bez narzędzi, z rozmową i pytaniem; nie widzi książek.
    assert "tools" not in planista and planista["messages"][1:3] == historia
    assert planista["messages"][-1] == {"role": "user", "content": "napisz o tym post"}
    assert "=== ksiazka-a" not in planista["messages"][0]["content"]
    # Szukacz dostaje oryginalne pytanie ORAZ ustalenia planisty.
    pytanie_szukacza = szukacz["messages"][3]["content"]   # system, 2 wiadomości historii, pytanie
    assert pytanie_szukacza.startswith("napisz o tym post") and "TEMAT: pomidor, ciepło i światło" in pytanie_szukacza
    # Pisarz: forma od planisty, bez prozy szukacza, z dosłownymi stronami.
    ostatnia = pisarz["messages"][-1]["content"]
    assert "FORMA: post na Facebooku" in ostatnia and "TEMAT:" not in ostatnia
    assert "Jasne" not in ostatnia and f"=== [{a} s. 1] ===" in ostatnia
    assert any(z.get("kto") == "planista" and "brief" in z for z in wynik.slad.zdarzenia)


def test_wariant_strony_blad_planisty_nie_blokuje_odpowiedzi(monkeypatch, tmp_path):
    from app import config
    from app.agent import agent
    from app.agent import petla as p

    monkeypatch.setattr(config, "AGENT", "strony")
    monkeypatch.setattr(config, "PLANISTA", True)
    a, _ = _dwie_ksiazki(monkeypatch, tmp_path)
    odpowiedzi = [None, _odp(wywolania=[_Wywolanie("1", "szukaj", {"fraza": "pomidor"})]),
                  _odp(f"STRONY: {a} 1"), _odp(f"Pomidor lubi ciepło [{a} s. 1].")]
    zapytania = []

    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    zapytania.append(kw)
                    if (o := odpowiedzi.pop(0)) is None:
                        raise RuntimeError("brak limitu")
                    return o

    monkeypatch.setattr(p, "_openai", Fake)
    wynik = agent.odpowiedz([a], "Co lubi pomidor?")
    assert wynik.tekst.startswith("Pomidor lubi ciepło")
    assert zapytania[1]["messages"][1]["content"] == "Co lubi pomidor?"      # bez briefu
    assert any(z.get("kto") == "planista" and "blad" in z for z in wynik.slad.zdarzenia)


def test_pisarz_uzywa_promptu_z_panelu_i_zapisuje_to_w_sladzie(model, monkeypatch, tmp_path):
    from app import config, prompty
    from app.agent import agent

    monkeypatch.setattr(config, "AGENT", "strony")
    monkeypatch.setattr(config, "PLANISTA", False)
    a, _ = _dwie_ksiazki(monkeypatch, tmp_path)

    def odpowiedz():
        kolejka, zapytania = model
        kolejka += [_odp(wywolania=[_Wywolanie("1", "szukaj", {"fraza": "pomidor"})]),
                    _odp(f"STRONY: {a} 1"), _odp("Gotowe.")]
        wynik = agent.odpowiedz([a], "Co lubi pomidor?")
        return zapytania[-1]["messages"][0]["content"], wynik.slad

    system, slad = odpowiedz()
    assert system == agent.PISARZ_STRON
    assert {"kto": "pisarz", "prompt": "domyslny"}.items() <= next(z for z in slad.zdarzenia if z.get("kto") == "pisarz").items()

    prompty.zapisz(prompty.PISARZ_STRONY, "Piszesz krótko. {nawiasy} zostają bez zmian.")
    system, slad = odpowiedz()
    assert system == "Piszesz krótko. {nawiasy} zostają bez zmian."          # bez .format — klamry są bezpieczne
    assert next(z for z in slad.zdarzenia if z.get("kto") == "pisarz")["prompt"] == "wlasny"
