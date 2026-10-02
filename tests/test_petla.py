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
