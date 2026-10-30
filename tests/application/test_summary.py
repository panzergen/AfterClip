from app.application.summary import clean_summary_output, looks_like_preamble

TR_PREAMBLE = (
    "Anladım. Verdiğiniz metin parçaları (doktor örneği, AI araçlarının kullanımı, "
    "Pfizer/Forward projeleri, etik sorunlar vb.) aslında bir sunumun **tam içeriğini** "
    "oluşturuyor ancak bunlar şu anda birbirinden kopuk parçalar halinde ve bazıları "
    "İngilizce olarak kalmış.\n\n"
    "Bu parçaları birleştirerek, istediğiniz formatta (**Slayt Sıralaması**, "
    "**İddia/Kanıt**, **Kaynak Belirtimi**) eksiksiz ve Türkçe olarak hazırlanmış sunum "
    "taslağını aşağıda bulabilirsiniz.\n\n"
    "## Slayt Sıralaması\n\n1. İlk slayt içeriği burada."
)


TR_REPORT_PREAMBLE = (
    "Harika bir sunum metni ve transkript özeti vermişsiniz. Ancak mesajınızın "
    'sonundaki "Bu nedenle şu taleplerinizi karşılayamıyorum..." kısmında '
    "belirttiğiniz eksiklikler muhtemelen metnin sonrasına eklenmiş bir not gibi "
    "duruyor.\n\n"
    "Verdiğiniz metin aslında tamamen bu eksiklikleri içeren bir taslak değil.\n\n"
    "Bu nedenle, verdiğiniz metni tamamen analiz ettim ve talep ettiğiniz formatta "
    "aşağıda Türkçe olarak hazırladım.\n\n"
    "Eğer bu rapor size uygun gelmezse veya metnin başka bir kısmını eklememi "
    "isterseniz lütfen belirtin.\n\n"
    "---\n\n"
    "# Detaylı Rapor: Sertifika Fonksiyonu\n\n"
    "## 1. Bölüm: Sertifika Yükleme Süreci"
)


def test_strips_multiparagraph_chat_reply_before_rule():
    cleaned = clean_summary_output(TR_REPORT_PREAMBLE)
    assert cleaned.startswith("# Detaylı Rapor")
    assert "Harika" not in cleaned
    assert "mesajınızın" not in cleaned
    assert "lütfen belirtin" not in cleaned
    assert "## 1. Bölüm: Sertifika Yükleme Süreci" in cleaned


def test_content_before_rule_is_kept():
    text = "The launch moved to May.\n\n---\n\n## Details\n\nMore."
    assert clean_summary_output(text) == text


def test_only_the_chatter_run_before_a_rule_is_dropped():
    text = "Real content stays.\n\nHere is the summary.\n\n---\n\n# Report\n\nBody."
    cleaned = clean_summary_output(text)
    assert cleaned.startswith("Real content stays.")
    assert "Here is" not in cleaned
    assert "# Report" in cleaned


def test_content_before_heading_is_kept_without_chatter():
    text = "The team agreed on the launch date.\n\n## Decisions\n\nMay 12."
    assert clean_summary_output(text) == text


def test_strips_turkish_preamble_keeps_content():
    cleaned = clean_summary_output(TR_PREAMBLE)
    assert "Anladım" not in cleaned
    assert "aşağıda bulabilirsiniz" not in cleaned
    assert cleaned.startswith("## Slayt Sıralaması")
    assert "İlk slayt" in cleaned


def test_strips_english_preamble():
    text = "Sure, here is the summary you asked for.\n\nThe meeting covered three topics."
    cleaned = clean_summary_output(text)
    assert cleaned == "The meeting covered three topics."


def test_strips_german_preamble():
    text = "Wie gewünscht habe ich die Zusammenfassung erstellt.\n\nDie Sitzung war produktiv."
    assert clean_summary_output(text) == "Die Sitzung war produktiv."


def test_clean_content_is_untouched():
    text = "## Summary\n\nThe team decided to launch in May.\n\nNext steps were assigned."
    assert clean_summary_output(text) == text


def test_all_preamble_returns_original():
    text = "Anladım, aşağıda bulabilirsiniz."
    assert clean_summary_output(text) == text


def test_empty_and_blank_pass_through():
    assert clean_summary_output("") == ""
    assert clean_summary_output("   ") == "   "


def test_looks_like_preamble_flags():
    assert looks_like_preamble("Anladım, veriyorum.")
    assert looks_like_preamble("Here is your summary:")
    assert not looks_like_preamble("The quarterly revenue grew by 12 percent.")


def test_clean_title_skips_preamble_lines():
    from app.application.topics import _clean_title

    assert _clean_title("Sure, here is a title:\nQuarterly Revenue Growth") == (
        "Quarterly Revenue Growth"
    )
    assert _clean_title("Quarterly Revenue Growth") == "Quarterly Revenue Growth"
    assert _clean_title("") == ""
