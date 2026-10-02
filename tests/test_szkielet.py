def test_config_sie_wczytuje():
    from app import config

    assert config.ZRODLA_DIR.name == "zrodla"
