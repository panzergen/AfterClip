from app.domain.content_packs import CONTENT_PACKS, find_pack, pack_labels
from app.domain.prompts import TEMPLATE_NAMES, PromptSet, validate_template


def test_all_six_starters_are_available():
    assert len(CONTENT_PACKS) == 6
    names = [pack.name for pack in CONTENT_PACKS]
    assert names == [
        "meeting",
        "slides",
        "software_demo",
        "product_demo",
        "narrative",
        "travel_documentary",
    ]
    for pack in CONTENT_PACKS:
        assert find_pack(pack.name) is pack
        assert find_pack(pack.label) is pack
        assert pack.label in pack_labels()


def test_pack_frame_defaults_are_sane():
    for pack in CONTENT_PACKS:
        assert pack.frame_modes
        assert pack.frame_interval > 0
        assert pack.frame_resolution in {"full", "mid", "low"}
    slides = find_pack("slides")
    assert slides is not None
    assert slides.frame_modes == ("scene",)
    assert slides.frame_interval == 30
    assert slides.frame_resolution == "full"


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
    assert "{task}" not in summary and "{vision_context}" not in summary

    highlights = prompts.render(
        "highlights", lang="tr", srt_content="1\n00:00:00,000 --> 00:00:01,000\nHi"
    )
    assert "'{lang}'" not in highlights
    assert "JSON array" in highlights
    assert "{task}" not in highlights and "{vision_context}" not in highlights

    vision = prompts.render(
        "vision_frame",
        user_desc="",
        audio_context="Welcome",
        lang="en",
    )
    assert "SLIDE TEXT" in vision
    assert "{lang}" not in vision and "{audio_context}" not in vision
    assert "{timestamp}" not in vision
