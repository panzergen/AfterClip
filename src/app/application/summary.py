"""Summary output cleaning (chatty-model safety net).

Small local models often acknowledge the task before delivering it
("Anladım...", "Here is...", "Wie gewünscht...") even when the prompt forbids
preambles. The prompt structure (constraints last) is the first line of
defence; this module removes a leftover leading preamble so it never reaches
``AI_Analysis.md``. Only leading paragraphs are ever touched — once a
paragraph looks like content, the rest of the text is kept verbatim. When
nothing looks like content, the original text is returned unchanged.
"""

import re

#: Case-insensitive signals that a leading paragraph is meta-commentary about
#: the task rather than the summary itself (Turkish, English, German).
PREAMBLE_SIGNALS = (
    # Turkish acknowledgements / delivery phrases.
    "anladım",
    "anladim",
    "verdiğiniz",
    "verdiginiz",
    "aşağıda",
    "asagida",
    "bulabilirsiniz",
    "bulabilirsin",
    "istediğiniz",
    "istediginiz",
    "formatta",
    "parçaları",
    "parcalari",
    "birleştirerek",
    "birlestirerek",
    "taslağını",
    "taslagini",
    "hazırlanmış",
    "hazirlanmis",
    "sunum tasla",
    "eksiksiz",
    # English acknowledgements / delivery phrases.
    "here is",
    "here's",
    "here are",
    "below you",
    "you'll find",
    "you will find",
    "sure,",
    "certainly",
    "of course",
    "i have combined",
    "i've combined",
    "i understand",
    "understood",
    "as requested",
    "in the format",
    "acknowledg",
    # German acknowledgements / delivery phrases.
    "hier ist",
    "hier sind",
    "wie gewünscht",
    "verstanden",
    "ich habe",
    "nachfolgend",
    "unten finden",
)

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")


def looks_like_preamble(paragraph: str) -> bool:
    """True when a paragraph reads as task meta-commentary, not content."""
    lowered = paragraph.lower()
    return any(signal in lowered for signal in PREAMBLE_SIGNALS)


def strip_preamble(text: str) -> str:
    """Drop leading meta-commentary paragraphs; keep everything else verbatim."""
    if not text or not text.strip():
        return text
    paragraphs = _PARAGRAPH_SPLIT.split(text.strip())
    index = 0
    while index < len(paragraphs) - 1 and looks_like_preamble(paragraphs[index]):
        index += 1
    if index == len(paragraphs):
        return text
    if index > 0 and looks_like_preamble(paragraphs[index]):
        # Every paragraph matched: nothing looks like content, keep original.
        return text
    return "\n\n".join(paragraphs[index:]).strip()


def clean_summary_output(text: str) -> str:
    """Public entry point: preamble-stripped summary, never empty on success."""
    if not text or not text.strip():
        return text
    return strip_preamble(text)
