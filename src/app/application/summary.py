"""Summary output cleaning (chatty-model safety net).

Small local models often answer the *prompt* instead of analysing the
transcript: they open with an acknowledgement ("Anladım...", "Here is...",
"Harika bir sunum metni vermişsiniz...") before the actual report. The prompt
structure (constraints last) is the first line of defence; this module removes
a leftover leading preamble so it never reaches ``AI_Analysis.md``.

Two passes are used:

* A structural pass: when a leading block of paragraphs is followed by a
  horizontal rule or a heading, and that block reads as chatter, the whole
  block is dropped (this catches multi-paragraph replies that discuss the
  prompt itself).
* A conservative paragraph pass: leading paragraphs that individually look
  like chatter are skipped, exactly until the first content paragraph.

Only leading text is ever touched. When nothing looks like content, the
original text is returned unchanged.
"""

import re

_HORIZONTAL_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_HEADING = re.compile(r"^\s*#{1,6}\s+\S")

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
    "hazırladım",
    "hazirladim",
    "sunum tasla",
    "eksiksiz",
    "mesajınız",
    "mesajiniz",
    "belirttiğiniz",
    "belirttiginiz",
    "vermişsiniz",
    "vermissiniz",
    "yazdığınız",
    "yazdiginiz",
    "paylaştığınız",
    "paylastiginiz",
    "eklememi isterseniz",
    "uygun gelmezse",
    "lütfen belirt",
    "lutfen belirt",
    "yardımcı olmaktan",
    "işte özet",
    "iste ozet",
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
    "i've prepared",
    "i have prepared",
    "i've analyzed",
    "i have analyzed",
    "i analyzed",
    "your message",
    "your request",
    "your transcript",
    "the transcript you",
    "let me know",
    "feel free",
    "hope this helps",
    "as an ai",
    # German acknowledgements / delivery phrases.
    "hier ist",
    "hier sind",
    "wie gewünscht",
    "verstanden",
    "ich habe",
    "nachfolgend",
    "unten finden",
    "sie haben",
    "ihre nachricht",
)

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

#: Strong signals that the model is talking to the user about the task, rather
#: than reporting content. Used for the structural pass so one stray greeting
#: cannot swallow an otherwise valid leading paragraph.
_CHATTER_PATTERNS = (
    re.compile(
        r"\b(?:mesaj(?:ınız|iniz|ını|ini)?|talebiniz|isteğiniz|isteginiz|"
        r"metniniz|transkriptiniz|promptunuz)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:vermişsiniz|vermissiniz|verdiğiniz|verdiginiz|belirttiğiniz|"
        r"belirttiginiz|yazdığınız|yazdiginiz|paylaştığınız|paylastiginiz|"
        r"istediğiniz|istediginiz|isterseniz|eklememi)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:your|you)\b[^.\n]{0,80}\b(?:message|request|transcript|prompt|instructions?)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i|we)\s+(?:have\s+)?(?:prepared|analyzed|analysed|reviewed|combined|"
        r"summarized|summarised)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:sie|ihr)\b[^.\n]{0,80}\b(?:nachricht|aufforderung|transkript)\b",
        re.IGNORECASE,
    ),
)


def looks_like_preamble(paragraph: str) -> bool:
    """True when a paragraph reads as task meta-commentary, not content."""
    lowered = paragraph.lower()
    return any(signal in lowered for signal in PREAMBLE_SIGNALS)


def _looks_like_chatter(paragraph: str) -> bool:
    """True when a paragraph addresses the user/prompt instead of the content."""
    return any(pattern.search(paragraph) for pattern in _CHATTER_PATTERNS)


def _is_chatter(paragraph: str) -> bool:
    return looks_like_preamble(paragraph) or _looks_like_chatter(paragraph)


def _chatter_run_before(paragraphs: list[str], boundary: int) -> int:
    """Start index of the contiguous chatter run ending just before ``boundary``."""
    start = boundary
    while start > 0 and _is_chatter(paragraphs[start - 1]):
        start -= 1
    return start


def _strip_leading_block(paragraphs: list[str]) -> list[str] | None:
    """Drop a chatter run that sits before a rule/heading, else ``None``.

    Only the paragraphs directly before the boundary are removed, so a chatty
    lead-in can never swallow real summary text that came earlier.
    """
    rule = next(
        (index for index, item in enumerate(paragraphs) if _HORIZONTAL_RULE.match(item)),
        None,
    )
    if rule is not None and rule > 0:
        start = _chatter_run_before(paragraphs, rule)
        if start < rule:
            end = rule
            while end < len(paragraphs) and _HORIZONTAL_RULE.match(paragraphs[end]):
                end += 1
            return paragraphs[:start] + paragraphs[end:]
    heading = next(
        (index for index, item in enumerate(paragraphs) if _HEADING.match(item)),
        None,
    )
    if heading is not None and heading > 0:
        start = _chatter_run_before(paragraphs, heading)
        if start < heading:
            return paragraphs[:start] + paragraphs[heading:]
    return None


def strip_preamble(text: str) -> str:
    """Drop leading meta-commentary paragraphs; keep everything else verbatim."""
    if not text or not text.strip():
        return text
    paragraphs = _PARAGRAPH_SPLIT.split(text.strip())
    stripped = _strip_leading_block(paragraphs)
    if stripped is not None and stripped:
        return "\n\n".join(stripped).strip()
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
