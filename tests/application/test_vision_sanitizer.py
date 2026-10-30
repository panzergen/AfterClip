from app.application.service import vision_analysis_label
from app.application.vision_sanitizer import (
    VisionSanitizerConfig,
    has_vision_content,
    is_blank_vision_response,
    sanitize_description,
)


def test_clean_description_is_left_alone():
    text = "The browser shows a control panel with a search box and a chat window."
    result = sanitize_description(text)
    assert result.text == text
    assert result.changed is False
    assert result.reason == ""


def test_consecutive_duplicate_clauses_collapse():
    result = sanitize_description("hello world. hello world. hello world.")
    assert result.text == "hello world."
    assert result.changed is True
    assert result.reason == "repetition"


def test_skeleton_loop_with_varying_quotes_collapses():
    text = (
        'sayfanın üst kısmında, "Control Panel Access | Vip" sekmesinin hemen yanında, '
        "adres çubuğunun hemen yanında, sayfanın üst kısmında, "
        '"Chat moderation | Control" sekmesinin hemen yanında, adres çubuğunun hemen yanında, '
        'sayfanın üst kısmında, "Foo" sekmesinin hemen yanında, adres çubuğunun hemen yanında, '
        'sayfanın üst kısmında, "Bar" sekmesinin hemen yanında, adres çubuğunun hemen yanında'
    )
    result = sanitize_description(text)
    assert result.reason == "repetition"
    assert result.text == (
        'sayfanın üst kısmında, "Control Panel Access | Vip" sekmesinin hemen yanında, '
        "adres çubuğunun hemen yanında"
    )


def test_short_or_non_looping_text_is_not_collapsed():
    text = "First clause, second clause, third clause."
    result = sanitize_description(text)
    assert result.text == text
    assert result.changed is False


def test_quoted_name_list_is_not_mistaken_for_a_loop():
    text = (
        'burada "Nejla KE...", "Metin ...", "Kubra ...", "Yusuf ...", '
        '"Ertunc E...", "Ozer OZ...", "Mutlu ..." gibi kullanıcı isimleri görülmektedir.'
    )
    result = sanitize_description(text)
    assert result.text == text
    assert result.changed is False


def test_drifting_loop_with_trailing_fragment_collapses():
    text = (
        "Ekranda bir tarayıcı penceresi açıktır. "
        'sayfanın üst kısmında, "A" sekmesinin hemen yanında, adres çubuğunun hemen yanında, '
        'sayfanın üst kısmında, "B" sekmesinin hemen yanında, adres çubuğunun hemen yanında, '
        'sayfanın üst kısmında, "B" sekmesinin hemen yanında, adres çubuğunun, '
        'sayfanın üst kısmında, "B" sekmesinin hemen yanında, adres çubuğunun hemen yanında, '
        'sayfanın üst kısmında, "B" sekmesinin hemen yanında, adres çubuğunun hemen yanında'
    )
    result = sanitize_description(text)
    assert result.reason == "repetition"
    assert result.text.startswith("Ekranda bir tarayıcı penceresi açıktır.")
    assert result.text.count("adres çubuğunun hemen yanında") <= 2


def test_length_ceiling_truncates_at_word_boundary():
    text = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima"
    result = sanitize_description(text, VisionSanitizerConfig(max_chars=30))
    assert result.reason == "length"
    assert result.text.endswith("\u2026")
    assert result.text.startswith("alpha bravo")
    assert len(result.text) <= 32


def test_disabled_config_only_normalizes_whitespace():
    result = sanitize_description(
        "hello world. hello world. hello world.", VisionSanitizerConfig(enabled=False)
    )
    assert result.text == "hello world. hello world. hello world."
    assert result.changed is False


def test_placeholder_only_vision_responses_have_no_content():
    assert not has_vision_content(
        "TITLE: [none] SLIDE TEXT: [none] VISUALS: [none] HIGHLIGHT: [none]"
    )
    assert not has_vision_content(
        "Başlık: [none] İçerik: [none] Grafik: [none] Öne Çıkan: [none]"
    )
    assert not has_vision_content("TITLE: [none] SLIDE TEXT: [unreadable] VISUALS: [none]")
    assert not has_vision_content("")
    # HIGHLIGHT is often the transcript leaking in; it must not count as a
    # description when every other field is empty.
    assert not has_vision_content(
        "TITLE: [none] SLIDE TEXT: [none] VISUALS: [none] HIGHLIGHT: 'so I need to go to rocket'"
    )


def test_real_vision_field_values_count_as_content():
    assert has_vision_content("TITLE: Registration Management SCREEN TEXT: Email settings")
    assert has_vision_content("URL: vistreamtemplate1.vistream.tv/vipanel/v2/login")
    assert has_vision_content("The screen shows a dashboard with a user table.")
    assert not is_blank_vision_response("TITLE: Dashboard")
    assert is_blank_vision_response("BLANK: true")


def test_config_round_trip_and_invalid_values_fall_back():
    config = VisionSanitizerConfig(max_repetition=4, keep_cycles=2, max_chars=500)
    assert VisionSanitizerConfig.from_dict(config.to_dict()) == config
    assert VisionSanitizerConfig.from_dict(None) == VisionSanitizerConfig()
    assert VisionSanitizerConfig.from_dict({"max_repetition": "bad"}).max_repetition == 3


def test_vision_analysis_label_uses_provider_and_model():
    class Provider:
        provider_name = "gemini"
        model = "gemini-flash-latest"

    assert vision_analysis_label(Provider()) == "Vision analysis (gemini: gemini-flash-latest)"
    assert vision_analysis_label(object()) == "Vision analysis (ollama)"
