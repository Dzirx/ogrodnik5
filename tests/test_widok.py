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
    assert 'title="Sułek, pomidory">s. ' in html  # jedna książka: bez indeksu i bez tytułu w tekście
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


def test_kilka_ksiazek_z_indeksami():
    html = str(widok.odpowiedz_html("a [x s. 1] b [y s. 2] c [x s. 3]", {"x": "X", "y": "Y"}))
    assert 'title="X">¹s. ' in html and 'title="Y">²s. ' in html


def test_dwie_ksiazki_w_jednym_nawiasie():
    """Model łamał zasadę „jedna książka w nawiasie" — wyświetlanie ma to znieść."""
    tekst = "F1 nie dają identycznych roślin [a s. 15; b s. 7] i [a s. 14]."
    html = str(widok.odpowiedz_html(tekst, {"a": "Książka A", "b": "Książka B"}, "/r/1"))
    assert "[a s." not in html and "[b s." not in html           # nic nie zostało surowym tekstem
    assert 'title="Książka A">¹s. <a href="/r/1?podglad=a:15' in html
    assert 'title="Książka B">²s. <a href="/r/1?podglad=b:7' in html
    assert widok.zrodla_odpowiedzi(tekst) == {"a": [14, 15], "b": [7]}


def test_naglowek_lista_i_podlista():
    tekst = ("Co się z nimi robi:\n- zwykle się je usuwa [a s. 18]\n- najlepiej wcześnie:\n"
             "  - do 2–3 cm ręcznie [a s. 61][b s. 18]\n  - inaczej do 10 cm [b s. 26]\n- bez noża")
    html = str(widok.odpowiedz_html(tekst, {"a": "A", "b": "B"}))
    assert html.startswith("<p>Co się z nimi robi:</p><ul><li>zwykle się je usuwa")
    assert "<li>najlepiej wcześnie:<ul><li>do 2–3 cm" in html and "<li>inaczej do 10 cm" in html
    assert html.endswith("<li>bez noża</li></ul>") and "<br>- " not in html
    # Sąsiednie znaczniki rozdzielone spacją, nie sklejone.
    assert '</span> <span class="znacznik"' in html
