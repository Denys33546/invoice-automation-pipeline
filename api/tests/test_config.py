from app.config import Settings, get_settings


def test_defaults():
    settings = Settings()
    assert settings.api_key == ""
    assert settings.max_upload_mb == 10
    assert settings.max_upload_bytes == 10 * 1024 * 1024
    assert settings.max_pages == 20


def test_settings_come_from_prefixed_environment_variables(monkeypatch):
    monkeypatch.setenv("EXTRACTOR_API_KEY", "from-env")
    monkeypatch.setenv("EXTRACTOR_MAX_PAGES", "5")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.api_key == "from-env"
        assert settings.max_pages == 5
        assert get_settings() is settings  # cached
    finally:
        get_settings.cache_clear()
