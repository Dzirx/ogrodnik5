from app.api import widok


def test_strony_zakres_i_lista():
    assert widok.strony("12, 28") == [12, 28]
    assert widok.strony("13–14") == [13, 14]
    assert widok.strony("13-14, 39") == [13, 14, 39]


def test_znaczniki_jako_linki_i_escape():
    html = str(widok.odpowiedz_html(
        "Rozstaw 80 x 40 cm [sulek-pomidory s. 23] <script>x</script> [U17]",
        {"sulek-pomidory": "Sułek, pomidory"}, "/rozmowy/1"))
    assert '<a href="/rozmowy/1?podglad=sulek-pomidory:23&amp;f=Rozstaw%2080%20x%2040%20cm' in html
    assert "Sułek, pomidory s." in html
    assert '<a class="spor-znacznik otwarty" href="/spory#U17"' in html and "spór · U17" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    html = str(widok.odpowiedz_html("x [U17]", {}, statusy={17: "rozstrzygniety"}))
    assert "ustalenie redakcji · U17" in html


def test_akapity_i_lista():
    html = str(widok.odpowiedz_html("Pierwszy.\n\n- a\n- **b**\n\nTrzeci.", {}))
    assert html == "<p>Pierwszy.</p><ul><li>a</li><li><strong>b</strong></li></ul><p>Trzeci.</p>"


def test_zrodla_odpowiedzi():
    assert widok.zrodla_odpowiedzi("x [a s. 12, 28] y [a s. 12] z [b s. 3–4]") == {"a": [12, 28], "b": [3, 4]}


def test_zaznacz_liczby():
    kawalki = widok.zaznacz("gleba ogrzana do 12–13°C, rozstaw 80 x 40 cm", "do 12–13°C [x s. 23]")
    assert [k["tekst"] for k in kawalki if k["zaznacz"]] == ["12–13"]


def test_zaznacz_cale_liczby():
    kawalki = widok.zaznacz("w 1% roztworze, oprysk 10% mlekiem, 0,5 kg", "1% i 0,5")
    assert [k["tekst"] for k in kawalki if k["zaznacz"]] == ["1", "0,5"]
