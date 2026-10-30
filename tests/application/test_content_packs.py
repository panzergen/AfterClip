from app.domain.content_packs import CONTENT_PACKS, find_pack, pack_labels
from app.domain.prompts import TEMPLATE_NAMES, PromptSet, validate_template


def test_slides_starter_is_available():
    pack = find_pack("slides")
    assert pack is not None
    assert pack.label == "Slides / presentation"
    assert find_pack(pack.label) is pack
    assert "Slides / presentation" in pack_labels()


def test_pack_prompts_are_valid_templates():
    for pack in CONTENT_PACKS:
        for name, text in pack.prompts.items():
            assert name in TEMPLATE_NAMES, (pack.name, name)
            assert validate_template(name, text) == [], (pack.name, name)


def test_slides_starter_renders_with_existing_placeholders():
    pack = find_pack("slides")
    assert pack is not None
    prompts = PromptSet().with_overrides(pack.prompts)

    summary = prompts.render(
        "summary", lang="en", transcript="Slide one. Slide two."
    )
    assert "slide-by-slide" in summary
    assert "{lang}" not in summary and "{transcript}" not in summary

    highlights = prompts.render(
        "highlights", lang="tr", srt_content="1\n00:00:00,000 --> 00:00:01,000\nHi"
    )
    assert "'{lang}'" not in highlights
    assert "JSON array" in highlights

    vision = prompts.render(
        "vision_frame",
        user_desc="",
        audio_context="Welcome",
        lang="en",
    )
    assert "SLIDE TEXT" in vision
    assert "{lang}" not in vision and "{audio_context}" not in vision
