from app.application.language import (
    detect_language,
    language_label,
    language_verdict,
    normalize_code,
)


def test_normalize_code_handles_case_and_region():
    assert normalize_code("TR-tr") == "tr"
    assert normalize_code(" EN ") == "en"
    assert normalize_code(None) == ""


def test_language_label_uses_name_when_known():
    assert language_label("tr") == "tr (Turkish)"
    assert language_label("xx") == "xx"


def test_turkish_titles_are_not_english():
    assert language_verdict("Zaman dil ayarları ve sertifika aktivasyonu", "tr") is True
    assert language_verdict("Zaman dil ayarları ve sertifika aktivasyonu", "en") is False


def test_english_titles_are_recognised():
    assert language_verdict("Dashboard shortcuts for quick navigation", "en") is True
    assert language_verdict("Dashboard shortcuts for quick navigation", "tr") is False


def test_foreign_titles_are_rejected_for_turkish():
    assert language_verdict("VPanel Funktionen und zukünftige Entwicklungen", "tr") is False
    assert language_verdict("Accès et gestion des comptes VPanel", "tr") is False
    assert language_verdict("Gestión de usuarios y páginas de moderador", "tr") is False
    assert language_verdict("Automatizimi i aktivizimit të anketës", "tr") is False


def test_product_names_and_unknown_languages_have_no_verdict():
    assert language_verdict("VPanel Version 2", "tr") is None
    assert language_verdict("VPanel Version 2", "xx") is None


def test_detect_language_names_a_clear_source_and_skips_neutral_titles():
    assert detect_language("Sugerències per a la gestió de registres") == "ca"
    assert detect_language("VPanel Version 2") is None


def test_azerbaijani_text_is_not_turkish():
    text = "Hesabat: Sertifika Yönetimi və Platform"
    assert language_verdict(text, "tr") is False
    assert language_verdict(text, "az") is True
    assert detect_language(text) == "az"


def test_non_latin_scripts_are_compared_by_script():
    assert language_verdict("Настройки отчёта", "ru") is True
    assert language_verdict("Настройки отчёта", "en") is False
    assert language_verdict("Report settings", "ru") is False
