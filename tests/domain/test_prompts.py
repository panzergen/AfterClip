import pytest

from app.domain.prompts import (
    DEFAULT_PROMPTS,
    TEMPLATE_NAMES,
    PromptSet,
    build_prompt_set,
    validate_prompt_set,
    validate_template,
)


def test_defaults_cover_all_templates():
    prompt_set = PromptSet()
    assert set(prompt_set.to_dict()) == set(TEMPLATE_NAMES)
    assert all(prompt_set.template(name) for name in TEMPLATE_NAMES)


def test_render_substitutes_named_placeholders():
    rendered = PromptSet().render("summary", lang="tr", transcript="merhaba")
    assert "language code 'tr'" in rendered
    assert rendered.endswith("Transcript:\nmerhaba")
    assert "{lang}" not in rendered


def test_render_is_safe_with_stray_braces_in_values():
    rendered = PromptSet().render("summary", lang="en", transcript="{not_a_field} {a.b}")
    assert "{not_a_field}" in rendered
    assert "{a.b}" in rendered


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        PromptSet().render("nope")


def test_validate_template_reports_unknown_and_missing():
    assert validate_template("summary", "has {lang} and {transcript}") == []
    assert any("unknown" in problem for problem in validate_template("summary", "{lang} {extra}"))
    assert any("missing" in problem for problem in validate_template("summary", "only {lang}"))


def test_validate_prompt_set_only_lists_invalid_templates():
    assert validate_prompt_set(PromptSet()) == {}
    problems = validate_prompt_set(build_prompt_set({"highlights": "no placeholders here"}))
    assert "highlights" in problems
    assert "summary" not in problems


def test_build_prompt_set_ignores_unknown_and_empty_overrides():
    prompt_set = build_prompt_set(
        {"summary": "custom {lang} {transcript}", "bogus": "x", "highlights": ""}
    )
    assert prompt_set.summary.startswith("custom")
    assert prompt_set.highlights == DEFAULT_PROMPTS["highlights"]


def test_with_overrides_returns_new_instance():
    base = PromptSet()
    other = base.with_overrides({"summary": "x {lang} {transcript}"})
    assert base.summary != other.summary
    assert other.summary == "x {lang} {transcript}"
