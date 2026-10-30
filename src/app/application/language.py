"""Small deterministic language guard for generated labels.

Not a general-purpose detector. It recognises the language families AfterClip
commonly meets so a short generated label (a topic title) returned in the wrong
language can be caught and re-asked. Ambiguous text (a product name, an acronym,
a title with no function words) yields no verdict, so the caller accepts it.

The guard is deliberately conservative: it only reports a mismatch when another
language has distinctly more evidence than the requested one.
"""

import re
from dataclasses import dataclass, field

LATIN = "latin"
CYRILLIC = "cyrillic"
ARABIC = "arabic"
HEBREW = "hebrew"
GREEK = "greek"
DEVANAGARI = "devanagari"
HAN = "han"
KANA = "kana"
HANGUL = "hangul"
THAI = "thai"

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "tr": "Turkish",
    "az": "Azerbaijani",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "ca": "Catalan",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sq": "Albanian",
    "ro": "Romanian",
    "pl": "Polish",
    "cs": "Czech",
    "hu": "Hungarian",
    "sv": "Swedish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "id": "Indonesian",
    "vi": "Vietnamese",
    "ru": "Russian",
    "uk": "Ukrainian",
    "ar": "Arabic",
    "fa": "Persian",
    "he": "Hebrew",
    "el": "Greek",
    "hi": "Hindi",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "th": "Thai",
}

#: Report-language choices for the UI: an empty code means English (default).
#: English itself is not repeated; selecting the first entry is the default.
REPORT_LANGUAGE_CHOICES: tuple[tuple[str, str], ...] = (
    ("", "English (default)"),
    *[
        (code, name)
        for code, name in sorted(LANGUAGE_NAMES.items(), key=lambda item: item[1])
        if code != "en"
    ],
)


@dataclass(frozen=True)
class LanguageProfile:
    name: str
    script: str = LATIN
    #: Characters that are strong evidence for this language (3 points each).
    unique_chars: frozenset[str] = field(default_factory=frozenset)
    #: Function words typical for the language (1.5 points each).
    words: frozenset[str] = field(default_factory=frozenset)
    #: Word endings typical for the language (0.75 points each).
    suffixes: tuple[str, ...] = ()

    def score(self, text: str) -> float:
        lowered = text.lower()
        score = 0.0
        for char in self.unique_chars:
            if char in lowered:
                score += 3.0
        for token in _WORD.findall(lowered):
            if token in self.words:
                score += 1.5
            elif len(token) >= 6 and token.endswith(self.suffixes):
                score += 0.75
        return score


_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

_SCRIPTS: dict[str, re.Pattern[str]] = {
    LATIN: re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿĀ-ž]"),
    CYRILLIC: re.compile(r"[\u0400-\u04ff]"),
    ARABIC: re.compile(r"[\u0600-\u06ff\u0750-\u077f]"),
    HEBREW: re.compile(r"[\u0590-\u05ff]"),
    GREEK: re.compile(r"[\u0370-\u03ff]"),
    DEVANAGARI: re.compile(r"[\u0900-\u097f]"),
    HAN: re.compile(r"[\u4e00-\u9fff]"),
    KANA: re.compile(r"[\u3040-\u30ff]"),
    HANGUL: re.compile(r"[\uac00-\ud7af]"),
    THAI: re.compile(r"[\u0e00-\u0e7f]"),
}

#: Languages whose script itself is a reliable verdict.
_NON_LATIN = {
    "ru": CYRILLIC,
    "uk": CYRILLIC,
    "ar": ARABIC,
    "fa": ARABIC,
    "he": HEBREW,
    "el": GREEK,
    "hi": DEVANAGARI,
    "zh": HAN,
    "ja": HAN,
    "ko": HANGUL,
    "th": THAI,
}

_PROFILES: dict[str, LanguageProfile] = {
    "en": LanguageProfile(
        "English",
        words=frozenset(
            {
                "the", "and", "for", "with", "from", "this", "that", "these", "those",
                "into", "over", "under", "about", "how", "what", "when", "where",
                "which", "who", "is", "are", "was", "were", "be", "been", "being",
                "to", "of", "in", "on", "at", "as", "by", "or", "not", "but", "if",
                "then", "so", "we", "you", "they", "it", "its", "our", "your",
                "their", "can", "will", "should", "must", "may", "new", "using",
                "use", "user", "users", "settings", "setup", "access", "report",
                "reports", "dashboard", "management", "overview", "introduction",
                "next", "steps", "summary", "highlights", "topics", "session",
                "local", "vendor", "vendors", "empower", "empowers", "launched",
                "launch", "available", "feature", "features", "account",
                "accounts", "sections", "roadmap", "phase", "phases",
                "configuration", "create", "form", "errors", "bugs", "product",
                "backlog", "live", "streaming", "embed", "codes", "parameter",
                "registration", "activation", "password", "zone", "certificate",
                "generation", "survey", "questions", "login", "names",
                "selecting", "fonts", "active", "date", "host", "country",
                "affects", "reporting", "better", "panel", "coming", "soon",
                "familiarization", "usage",
            }
        ),
        suffixes=("tion", "tions", "ment", "ments", "ing", "ings", "ness", "ship"),
    ),
    "tr": LanguageProfile(
        "Turkish",
        unique_chars=frozenset({"ı", "ş", "ğ"}),
        words=frozenset(
            {
                "ve", "bir", "bu", "şu", "için", "ile", "da", "de", "ki", "mi", "mı",
                "mu", "mü", "çok", "daha", "gibi", "kadar", "ama", "ancak", "olarak",
                "sonra", "yeni", "tüm", "her", "ne", "nasıl", "neden", "değil", "var",
                "yok", "olan", "üzerinde", "içinde", "arasında", "önce", "göre",
                "kullanıcı", "kullanıcılar", "ayarları", "ayarlar", "rapor", "raporu",
                "sertifika", "aktivasyon", "oturum", "eğitim", "yönetim", "erişim",
                "sürüm",
                "oluşturma", "düzenleme", "görünüm", "tasarlama", "sorunlar",
            }
        ),
        suffixes=(
            "ları", "leri", "lık", "lik", "luk", "lük", "yor", "mış", "miş", "muş",
            "müş", "acak", "ecek", "ması", "mesi", "ım", "im", "um", "üm", "ın",
            "in", "un", "ün", "dı", "di", "du", "dü", "tı", "ti", "tu", "tü",
            "ma", "me", "sı", "si", "su", "sü",
        ),
    ),
    "az": LanguageProfile(
        "Azerbaijani",
        unique_chars=frozenset({"ə"}),
        words=frozenset(
            {
                "və", "üçün", "deyil", "hesabat", "slayd", "istifadəçi",
                "istifadəçilər", "qeyd", "xülasə", "təqdim", "yoxlama", "ilə", "bu",
                "bir", "olan", "həm", "də", "ki", "nə", "çox", "daha", "amma",
                "lakin", "hər", "kimi", "qədər", "yeni", "bütün", "var", "yox",
                "olur", "edir", "edilir", "olaraq", "sonra", "əvvəl", "görə",
                "arasında", "daxilində", "üzərində", "sertifikat", "aktivasiya",
                "panel", "istifadə",
            }
        ),
        suffixes=("lıq", "lik", "luq", "lük", "sı", "si", "su", "sü", "ın", "in",
                  "un", "ün", "dan", "dən", "lar", "lər"),
    ),
    "de": LanguageProfile(
        "German",
        unique_chars=frozenset({"ß"}),
        words=frozenset(
            {
                "der", "die", "das", "den", "dem", "des", "und", "oder", "aber",
                "für", "mit", "von", "zu", "im", "in", "am", "an", "auf", "aus",
                "bei", "nach", "über", "unter", "vor", "ist", "sind", "war",
                "werden", "wird", "neue", "neuen", "ein", "eine", "einer", "eines",
                "nicht", "auch", "wie", "als", "um", "zur", "zum", "benutzer",
                "einstellungen", "bericht", "funktionen", "entwicklungen",
            }
        ),
        suffixes=("ung", "ungen", "keit", "heit", "lich", "isch", "schaft"),
    ),
    "fr": LanguageProfile(
        "French",
        words=frozenset(
            {
                "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou",
                "mais", "pour", "avec", "sans", "sur", "sous", "dans", "par", "au",
                "aux", "ce", "cette", "ces", "est", "sont", "être", "pas", "plus",
                "comme", "qui", "que", "dont", "où", "gestion", "compte", "comptes",
                "utilisateurs", "utilisateur", "rapport", "paramètres", "accès",
            }
        ),
        suffixes=("tion", "tions", "ment", "ments", "eux", "euse", "ique", "iques",
                  "ance", "ence", "ière", "ières"),
    ),
    "es": LanguageProfile(
        "Spanish",
        unique_chars=frozenset({"ñ", "¿", "¡"}),
        words=frozenset(
            {
                "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del",
                "y", "o", "pero", "para", "con", "sin", "sobre", "en", "por", "al",
                "es", "son", "está", "están", "como", "que", "más", "gestión",
                "usuarios", "usuario", "informes", "informe", "configuración",
                "páginas", "página", "sertifikas", "ajustes", "acceso",
            }
        ),
        suffixes=("ción", "ciones", "dad", "dades", "ado", "ada", "iendo", "ando"),
    ),
    "ca": LanguageProfile(
        "Catalan",
        words=frozenset(
            {
                "el", "la", "els", "les", "un", "una", "de", "del", "i", "o",
                "però", "per", "amb", "sense", "sobre", "en", "al", "als", "és",
                "són", "com", "que", "més", "gestió", "usuaris", "usuari",
                "comptes", "compte", "configuració", "pàgines", "pàgina", "accés",
                "informe", "registres", "registre",
            }
        ),
        suffixes=("ció", "cions", "tat", "tats", "ment", "ments", "ança", "ances"),
    ),
    "it": LanguageProfile(
        "Italian",
        words=frozenset(
            {
                "il", "lo", "la", "i", "gli", "le", "un", "una", "di", "del", "e",
                "o", "ma", "per", "con", "senza", "su", "in", "da", "al", "è",
                "sono", "come", "che", "più", "gestione", "utenti", "utente",
                "rapporto", "impostazioni", "accesso", "pagina", "pagine",
            }
        ),
        suffixes=("zione", "zioni", "mente", "ità", "aggio", "aggi"),
    ),
    "pt": LanguageProfile(
        "Portuguese",
        unique_chars=frozenset({"ã", "õ"}),
        words=frozenset(
            {
                "o", "a", "os", "as", "um", "uma", "de", "do", "da", "e", "ou",
                "mas", "para", "com", "sem", "sobre", "em", "por", "ao", "é",
                "são", "como", "que", "mais", "gestão", "usuários", "usuário",
                "relatório", "configuração", "páginas", "página", "acesso",
            }
        ),
        suffixes=("ção", "ções", "dade", "mente", "agem", "agens"),
    ),
    "nl": LanguageProfile(
        "Dutch",
        words=frozenset(
            {
                "de", "het", "een", "en", "of", "maar", "voor", "met", "zonder",
                "op", "in", "van", "aan", "is", "zijn", "als", "dat", "die",
                "meer", "gebruikers", "gebruiker", "rapport", "instellingen",
            }
        ),
        suffixes=("ing", "ingen", "heid", "lijk"),
    ),
    "sq": LanguageProfile(
        "Albanian",
        unique_chars=frozenset({"ë"}),
        words=frozenset(
            {
                "dhe", "e", "të", "i", "në", "me", "nga", "për", "si", "por",
                "se", "nuk", "është", "janë", "më", "shumë", "aktivizimi",
                "anketës", "përdorues", "raporti", "cilësimet", "qasja",
            }
        ),
        suffixes=("imi", "imit", "ës", "ët", "ore", "ues"),
    ),
    "ro": LanguageProfile(
        "Romanian",
        unique_chars=frozenset({"ă", "ș", "ț"}),
        words=frozenset(
            {
                "și", "în", "cu", "pentru", "de", "la", "un", "o", "este", "sunt",
                "care", "mai", "utilizatori", "utilizator", "raport", "setări",
                "acces",
            }
        ),
        suffixes=("ție", "ții", "tate", "mente"),
    ),
    "pl": LanguageProfile(
        "Polish",
        unique_chars=frozenset({"ł", "ą", "ę", "ś", "ż", "ź", "ć", "ń"}),
        words=frozenset(
            {
                "i", "w", "z", "na", "do", "dla", "nie", "jest", "są", "oraz",
                "użytkownicy", "użytkownik", "raport", "ustawienia", "dostęp",
            }
        ),
        suffixes=("anie", "enie", "ność", "ości"),
    ),
    "cs": LanguageProfile(
        "Czech",
        unique_chars=frozenset({"ř", "ě", "ů"}),
        words=frozenset(
            {
                "a", "v", "na", "s", "z", "je", "jsou", "který", "uživatelé",
                "uživatel", "zpráva", "nastavení", "přístup",
            }
        ),
        suffixes=("ování", "ení", "ost", "osti"),
    ),
    "hu": LanguageProfile(
        "Hungarian",
        unique_chars=frozenset({"ő", "ű"}),
        words=frozenset(
            {
                "a", "az", "és", "vagy", "de", "hogy", "nem", "is", "van",
                "vannak", "felhasználók", "felhasználó", "jelentés", "beállítások",
            }
        ),
        suffixes=("ás", "és", "és", "ság", "ség"),
    ),
    "sv": LanguageProfile(
        "Swedish",
        unique_chars=frozenset({"å"}),
        words=frozenset(
            {
                "och", "att", "för", "med", "av", "på", "är", "som", "inte",
                "användare", "rapport", "inställningar", "åtkomst",
            }
        ),
        suffixes=("ning", "ningar", "het", "lig"),
    ),
    "da": LanguageProfile(
        "Danish",
        unique_chars=frozenset({"ø", "æ"}),
        words=frozenset(
            {
                "og", "at", "for", "med", "af", "på", "er", "som", "ikke",
                "brugere", "bruger", "rapport", "indstillinger", "adgang",
            }
        ),
        suffixes=("ning", "ninger", "hed", "lig"),
    ),
    "no": LanguageProfile(
        "Norwegian",
        unique_chars=frozenset({"ø", "æ"}),
        words=frozenset(
            {
                "og", "at", "for", "med", "av", "på", "er", "som", "ikke",
                "brukere", "bruker", "rapport", "innstillinger", "tilgang",
            }
        ),
        suffixes=("ning", "ninger", "het", "lig"),
    ),
    "fi": LanguageProfile(
        "Finnish",
        words=frozenset(
            {
                "ja", "on", "ei", "että", "kanssa", "käyttäjät", "käyttäjä",
                "raportti", "asetukset", "pääsy",
            }
        ),
        suffixes=("minen", "misen", "uus", "yys"),
    ),
    "id": LanguageProfile(
        "Indonesian",
        words=frozenset(
            {
                "dan", "yang", "di", "ke", "dari", "untuk", "dengan", "adalah",
                "pengguna", "laporan", "pengaturan", "akses",
            }
        ),
        suffixes=("an", "nya", "kan"),
    ),
    "vi": LanguageProfile(
        "Vietnamese",
        unique_chars=frozenset(
            {"ơ", "ư", "đ", "ạ", "ả", "ấ", "ầ", "ẩ", "ẫ", "ậ", "ắ", "ằ", "ẳ",
             "ẵ", "ặ", "ế", "ề", "ể", "ễ", "ệ", "ố", "ồ", "ổ", "ỗ", "ộ", "ớ",
             "ờ", "ở", "ỡ", "ợ", "ụ", "ủ", "ứ", "ừ", "ử", "ữ", "ự", "ỳ", "ỵ"}
        ),
        words=frozenset({"và", "của", "là", "có", "cho", "với", "người", "dùng",
                         "báo", "cáo", "cài", "đặt", "truy", "cập"}),
    ),
    "ru": LanguageProfile("Russian", script=CYRILLIC),
    "uk": LanguageProfile("Ukrainian", script=CYRILLIC),
    "ar": LanguageProfile("Arabic", script=ARABIC),
    "fa": LanguageProfile("Persian", script=ARABIC),
    "he": LanguageProfile("Hebrew", script=HEBREW),
    "el": LanguageProfile("Greek", script=GREEK),
    "hi": LanguageProfile("Hindi", script=DEVANAGARI),
    "zh": LanguageProfile("Chinese", script=HAN),
    "ja": LanguageProfile("Japanese", script=HAN),
    "ko": LanguageProfile("Korean", script=HANGUL),
    "th": LanguageProfile("Thai", script=THAI),
}


def normalize_code(code: str | None) -> str:
    """Lowercase a language code and drop a region tag (``tr-TR`` -> ``tr``)."""
    return (code or "").strip().lower().replace("_", "-").split("-")[0]


def language_name(code: str | None) -> str:
    """English name of a language code (the code itself when unknown)."""
    base = normalize_code(code)
    return LANGUAGE_NAMES.get(base, base)


def language_label(code: str | None) -> str:
    """Prompt-friendly language identity: ``tr (Turkish)`` when known."""
    base = normalize_code(code)
    name = LANGUAGE_NAMES.get(base)
    return f"{base} ({name})" if name else base


def _dominant_script(text: str) -> str | None:
    counts = {script: len(pattern.findall(text)) for script, pattern in _SCRIPTS.items()}
    script, count = max(counts.items(), key=lambda item: item[1])
    if count == 0:
        return None
    total = sum(counts.values())
    return script if count / total >= 0.6 else None


def detect_language(text: str, minimum: float = 1.5) -> str | None:
    """Best-guess language code for clear text, ``None`` when ambiguous."""
    if not (text or "").strip():
        return None
    script = _dominant_script(text)
    if script is not None and script != LATIN:
        for code, expected in _NON_LATIN.items():
            if expected == script:
                return code
        return None
    scores = {
        code: profile.score(text)
        for code, profile in _PROFILES.items()
        if profile.script == LATIN
    }
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked or ranked[0][1] < minimum:
        return None
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None
    return ranked[0][0]


def language_verdict(text: str, code: str | None) -> bool | None:
    """Whether ``text`` is plausibly written in ``code``.

    Returns ``True``/``False`` when the evidence is clear, ``None`` when the
    text is too short/neutral or the language is not recognised.
    """
    base = normalize_code(code)
    profile = _PROFILES.get(base)
    if profile is None or not (text or "").strip():
        return None
    script = _dominant_script(text)
    if base in _NON_LATIN:
        if script is None:
            return None
        if base == "ja" and script == KANA:
            return True
        return script == _NON_LATIN[base]
    if script is not None and script != LATIN:
        return False
    scores = {
        code: candidate.score(text)
        for code, candidate in _PROFILES.items()
        if candidate.script == LATIN
    }
    target = scores.get(base, 0.0)
    others = [score for code, score in scores.items() if code != base]
    best_other = max(others, default=0.0)
    if target >= 1.5 and target >= best_other:
        return True
    # Require a real margin: many short English titles contain words that also
    # exist in another language ("as" is both English and Portuguese), and a
    # single foreign-looking suffix is not enough evidence.
    if best_other >= 1.5 and best_other >= target + 1.5:
        return False
    return None
