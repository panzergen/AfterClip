from app.application.markdown_html import render_markdown


def test_render_markdown_headings_and_inline_formatting():
    html = render_markdown("# Summary\n\nThis is **bold** and `code`.", heading_offset=1)

    assert "<h2>Summary</h2>" in html
    assert "<strong>bold</strong>" in html
    assert "<code>code</code>" in html


def test_render_markdown_lists_and_tables():
    html = render_markdown(
        "- one\n- two\n\n| Name | Value |\n| --- | --- |\n| A | 1 |\n",
        heading_offset=1,
    )

    assert "<ul><li>one</li><li>two</li></ul>" in html
    assert "<table><thead><tr><th>Name</th><th>Value</th></tr></thead>" in html
    assert "<td>A</td><td>1</td>" in html


def test_render_markdown_escapes_html():
    html = render_markdown("<script>alert(1)</script>")

    assert "<script>" not in html
    assert "&lt;script&gt;" in html
