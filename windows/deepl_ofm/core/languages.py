"""Language metadata, interface languages and script based detection.

Ported from ``Sources/HyMT/Models/Language.swift``; the ``AppLanguage`` enum and
its locale identifiers come from ``Sources/HyMT/Support/Localization.swift``.
The macOS ``NLLanguageRecognizer`` hypothesis is replaced by a compact stop-word
scorer for the Latin languages, falling back to English for Latin text.
"""
from __future__ import annotations

import locale
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from enum import Enum

try:  # the i18n catalogue is a sibling package; survive a circular start-up
    from deepl_ofm.i18n import t as _i18n_t
except ImportError:  # pragma: no cover - only while deepl_ofm.i18n is importing us
    _i18n_t = None  # type: ignore[assignment]


def translate(key: str, language: "AppLanguage | str | None" = None) -> str:
    """Translate *key* through :mod:`deepl_ofm.i18n`, tolerating its absence."""
    global _i18n_t
    translate = _i18n_t
    if translate is None:
        try:
            from deepl_ofm.i18n import t as translate  # noqa: F811 - late binding
        except ImportError:  # pragma: no cover - i18n is part of the app
            return key
        _i18n_t = translate
    try:
        return translate(key, language)
    except TypeError:  # older/stub signature without the language argument
        try:
            return translate(key)
        except Exception:  # pragma: no cover - defensive
            return key
    except Exception:  # pragma: no cover - defensive
        return key


class AppLanguage(str, Enum):
    """Interface language, mirroring the Swift ``AppLanguage`` enum."""

    SYSTEM = "system"
    EN = "en"
    UK = "uk"
    RU = "ru"
    DE = "de"
    FR = "fr"
    ES = "es"
    PL = "pl"
    PT = "pt"
    IT = "it"

    @property
    def resolved(self) -> "AppLanguage":
        """``system`` mapped to the detected OS language, everything else unchanged."""
        if self is AppLanguage.SYSTEM:
            return AppLanguage.system_resolved()
        return self

    @property
    def picker_title(self) -> str:
        """Native language name shown in the language picker."""
        if self is AppLanguage.SYSTEM:
            return translate("System")
        return _PICKER_TITLES[self]

    @property
    def locale_identifier(self) -> str:
        """``uk_UA`` style identifier used by the name lookup."""
        if self is AppLanguage.SYSTEM:
            return AppLanguage.system_resolved().locale_identifier
        return _LOCALE_IDENTIFIERS[self]

    @staticmethod
    def system_resolved() -> "AppLanguage":
        """Detect the OS interface language, defaulting to English."""
        code = _system_language_code()
        if code in ("ua",):
            code = "uk"
        return _SYSTEM_LANGUAGES.get(code, AppLanguage.EN)


_PICKER_TITLES: dict[AppLanguage, str] = {
    AppLanguage.EN: "English",
    AppLanguage.UK: "Українська",
    AppLanguage.RU: "Русский",
    AppLanguage.DE: "Deutsch",
    AppLanguage.FR: "Français",
    AppLanguage.ES: "Español",
    AppLanguage.PL: "Polski",
    AppLanguage.PT: "Português",
    AppLanguage.IT: "Italiano",
}

_LOCALE_IDENTIFIERS: dict[AppLanguage, str] = {
    AppLanguage.EN: "en_US",
    AppLanguage.UK: "uk_UA",
    AppLanguage.RU: "ru_RU",
    AppLanguage.DE: "de_DE",
    AppLanguage.FR: "fr_FR",
    AppLanguage.ES: "es_ES",
    AppLanguage.PL: "pl_PL",
    AppLanguage.PT: "pt_PT",
    AppLanguage.IT: "it_IT",
}

_SYSTEM_LANGUAGES: dict[str, AppLanguage] = {
    "en": AppLanguage.EN,
    "uk": AppLanguage.UK,
    "ru": AppLanguage.RU,
    "de": AppLanguage.DE,
    "fr": AppLanguage.FR,
    "es": AppLanguage.ES,
    "pl": AppLanguage.PL,
    "pt": AppLanguage.PT,
    "it": AppLanguage.IT,
}

# Windows LANGID primary language identifiers for the nine interface languages.
_WINDOWS_PRIMARY_LANGUAGES: dict[int, str] = {
    0x07: "de",
    0x09: "en",
    0x0A: "es",
    0x0C: "fr",
    0x10: "it",
    0x15: "pl",
    0x16: "pt",
    0x19: "ru",
    0x22: "uk",
}


def _windows_ui_language() -> str:  # pragma: no cover - Windows only
    """Best-effort UI language code through the Win32 API."""
    try:
        import ctypes

        language_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
    except Exception:
        return ""
    return _WINDOWS_PRIMARY_LANGUAGES.get(int(language_id) & 0x3FF, "")


def _system_language_code() -> str:
    """Return a two letter language code for the current session."""
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        raw = os.environ.get(variable, "").strip()
        if not raw:
            continue
        code = re.split(r"[.:@_\-]", raw, maxsplit=1)[0].strip().lower()
        if code:
            return code
    if sys.platform == "win32":
        code = _windows_ui_language()
        if code:
            return code
    try:
        code = (locale.getlocale()[0] or "").strip()
    except (TypeError, ValueError):  # pragma: no cover - exotic locale failures
        code = ""
    if code:
        return re.split(r"[.:@_\-]", code, maxsplit=1)[0].lower()
    return "en"


def coerce_app_language(value: AppLanguage | str | None) -> AppLanguage:
    """Best-effort conversion of stored/UI values to :class:`AppLanguage`."""
    if isinstance(value, AppLanguage):
        return value
    if value is None:
        return AppLanguage.SYSTEM
    code = str(value).strip().lower().replace("-", "_")
    if not code:
        return AppLanguage.SYSTEM
    code = code.split("_")[0]
    if code == "ua":
        return AppLanguage.UK
    return _SYSTEM_LANGUAGES.get(code, AppLanguage.SYSTEM)


@dataclass(frozen=True, slots=True)
class Language:
    """A translation language; ``english_name`` goes into the model instruction."""

    code: str
    english_name: str
    local_name: str
    bcp47: str | None = None

    @property
    def is_auto(self) -> bool:
        """True for the pseudo language used by the "Auto-detect" entry."""
        return self.code == "auto"

    def display_name(self, app_language: AppLanguage | str | None = None) -> str:
        """Name of the language in ``app_language`` (English when unavailable)."""
        language = coerce_app_language(app_language)
        if self.is_auto:
            return translate("Auto-detect", language.resolved)
        resolved = language.resolved
        if resolved is AppLanguage.UK:
            return self.local_name or self.english_name
        if resolved is AppLanguage.EN:
            return self.english_name
        names = _LOCALIZED_NAMES.get(self.code)
        if names:
            localized = names.get(resolved.value)
            if localized:
                return localized
        return self.english_name


# Localised language names for the seven non-English/non-Ukrainian interface
# languages, standing in for the macOS Locale database.
_LOCALIZED_NAMES: dict[str, dict[str, str]] = {
    "zh": {"ru": "китайский", "de": "Chinesisch", "fr": "chinois", "es": "chino",
           "pl": "chiński", "pt": "chinês", "it": "cinese"},
    "en": {"ru": "английский", "de": "Englisch", "fr": "anglais", "es": "inglés",
           "pl": "angielski", "pt": "inglês", "it": "inglese"},
    "fr": {"ru": "французский", "de": "Französisch", "fr": "français", "es": "francés",
           "pl": "francuski", "pt": "francês", "it": "francese"},
    "pt": {"ru": "португальский", "de": "Portugiesisch", "fr": "portugais", "es": "portugués",
           "pl": "portugalski", "pt": "português", "it": "portoghese"},
    "es": {"ru": "испанский", "de": "Spanisch", "fr": "espagnol", "es": "español",
           "pl": "hiszpański", "pt": "espanhol", "it": "spagnolo"},
    "ja": {"ru": "японский", "de": "Japanisch", "fr": "japonais", "es": "japonés",
           "pl": "japoński", "pt": "japonês", "it": "giapponese"},
    "tr": {"ru": "турецкий", "de": "Türkisch", "fr": "turc", "es": "turco",
           "pl": "turecki", "pt": "turco", "it": "turco"},
    "ru": {"ru": "русский", "de": "Russisch", "fr": "russe", "es": "ruso",
           "pl": "rosyjski", "pt": "russo", "it": "russo"},
    "ar": {"ru": "арабский", "de": "Arabisch", "fr": "arabe", "es": "árabe",
           "pl": "arabski", "pt": "árabe", "it": "arabo"},
    "ko": {"ru": "корейский", "de": "Koreanisch", "fr": "coréen", "es": "coreano",
           "pl": "koreański", "pt": "coreano", "it": "coreano"},
    "th": {"ru": "тайский", "de": "Thailändisch", "fr": "thaï", "es": "tailandés",
           "pl": "tajski", "pt": "tailandês", "it": "thailandese"},
    "it": {"ru": "итальянский", "de": "Italienisch", "fr": "italien", "es": "italiano",
           "pl": "włoski", "pt": "italiano", "it": "italiano"},
    "de": {"ru": "немецкий", "de": "Deutsch", "fr": "allemand", "es": "alemán",
           "pl": "niemiecki", "pt": "alemão", "it": "tedesco"},
    "vi": {"ru": "вьетнамский", "de": "Vietnamesisch", "fr": "vietnamien", "es": "vietnamita",
           "pl": "wietnamski", "pt": "vietnamita", "it": "vietnamita"},
    "ms": {"ru": "малайский", "de": "Malaiisch", "fr": "malais", "es": "malayo",
           "pl": "malajski", "pt": "malaio", "it": "malese"},
    "id": {"ru": "индонезийский", "de": "Indonesisch", "fr": "indonésien", "es": "indonesio",
           "pl": "indonezyjski", "pt": "indonésio", "it": "indonesiano"},
    "tl": {"ru": "филиппинский", "de": "Filipino", "fr": "philippin", "es": "filipino",
           "pl": "filipiński", "pt": "filipino", "it": "filippino"},
    "hi": {"ru": "хинди", "de": "Hindi", "fr": "hindi", "es": "hindi",
           "pl": "hindi", "pt": "híndi", "it": "hindi"},
    "zh-Hant": {"ru": "китайский (традиционный)", "de": "Chinesisch (traditionell)",
                "fr": "chinois traditionnel", "es": "chino tradicional",
                "pl": "chiński tradycyjny", "pt": "chinês tradicional",
                "it": "cinese tradizionale"},
    "pl": {"ru": "польский", "de": "Polnisch", "fr": "polonais", "es": "polaco",
           "pl": "polski", "pt": "polaco", "it": "polacco"},
    "cs": {"ru": "чешский", "de": "Tschechisch", "fr": "tchèque", "es": "checo",
           "pl": "czeski", "pt": "checo", "it": "ceco"},
    "nl": {"ru": "нидерландский", "de": "Niederländisch", "fr": "néerlandais",
           "es": "neerlandés", "pl": "niderlandzki", "pt": "neerlandês",
           "it": "olandese"},
    "km": {"ru": "кхмерский", "de": "Khmer", "fr": "khmer", "es": "jemer",
           "pl": "khmerski", "pt": "khmer", "it": "khmer"},
    "my": {"ru": "бирманский", "de": "Birmanisch", "fr": "birman", "es": "birmano",
           "pl": "birmański", "pt": "birmanês", "it": "birmano"},
    "fa": {"ru": "персидский", "de": "Persisch", "fr": "persan", "es": "persa",
           "pl": "perski", "pt": "persa", "it": "persiano"},
    "gu": {"ru": "гуджарати", "de": "Gujarati", "fr": "gujarati", "es": "guyaratí",
           "pl": "gudżarati", "pt": "guzerate", "it": "gujarati"},
    "ur": {"ru": "урду", "de": "Urdu", "fr": "ourdou", "es": "urdu",
           "pl": "urdu", "pt": "urdu", "it": "urdu"},
    "te": {"ru": "телугу", "de": "Telugu", "fr": "télougou", "es": "telugu",
           "pl": "telugu", "pt": "telugu", "it": "telugu"},
    "mr": {"ru": "маратхи", "de": "Marathi", "fr": "marathi", "es": "maratí",
           "pl": "marathi", "pt": "marata", "it": "marathi"},
    "he": {"ru": "иврит", "de": "Hebräisch", "fr": "hébreu", "es": "hebreo",
           "pl": "hebrajski", "pt": "hebraico", "it": "ebraico"},
    "bn": {"ru": "бенгальский", "de": "Bengalisch", "fr": "bengali", "es": "bengalí",
           "pl": "bengalski", "pt": "bengali", "it": "bengalese"},
    "ta": {"ru": "тамильский", "de": "Tamil", "fr": "tamoul", "es": "tamil",
           "pl": "tamilski", "pt": "tâmil", "it": "tamil"},
    "uk": {"ru": "украинский", "de": "Ukrainisch", "fr": "ukrainien", "es": "ucraniano",
           "pl": "ukraiński", "pt": "ucraniano", "it": "ucraino"},
    "bo": {"ru": "тибетский", "de": "Tibetisch", "fr": "tibétain", "es": "tibetano",
           "pl": "tybetański", "pt": "tibetano", "it": "tibetano"},
    "kk": {"ru": "казахский", "de": "Kasachisch", "fr": "kazakh", "es": "kazajo",
           "pl": "kazachski", "pt": "cazaque", "it": "kazako"},
    "mn": {"ru": "монгольский", "de": "Mongolisch", "fr": "mongol", "es": "mongol",
           "pl": "mongolski", "pt": "mongol", "it": "mongolo"},
    "ug": {"ru": "уйгурский", "de": "Uigurisch", "fr": "ouïghour", "es": "uigur",
           "pl": "ujgurski", "pt": "uigure", "it": "uiguro"},
    "yue": {"ru": "кантонский", "de": "Kantonesisch", "fr": "cantonais", "es": "cantonés",
            "pl": "kantoński", "pt": "cantonês", "it": "cantonese"},
}


class LanguageTable:
    """Registry of the 38 Hy-MT2 languages plus script based detection."""

    AUTO: Language = Language(
        code="auto",
        english_name="",
        local_name="Автовизначення",
        bcp47=None,
    )

    ALL: list[Language] = [
        Language("zh", "Chinese", "китайська", "zh-CN"),
        Language("en", "English", "англійська", "en-US"),
        Language("fr", "French", "французька", "fr-FR"),
        Language("pt", "Portuguese", "португальська", "pt-PT"),
        Language("es", "Spanish", "іспанська", "es-ES"),
        Language("ja", "Japanese", "японська", "ja-JP"),
        Language("tr", "Turkish", "турецька", "tr-TR"),
        Language("ru", "Russian", "російська", "ru-RU"),
        Language("ar", "Arabic", "арабська", "ar-SA"),
        Language("ko", "Korean", "корейська", "ko-KR"),
        Language("th", "Thai", "тайська", "th-TH"),
        Language("it", "Italian", "італійська", "it-IT"),
        Language("de", "German", "німецька", "de-DE"),
        Language("vi", "Vietnamese", "в'єтнамська", "vi-VN"),
        Language("ms", "Malay", "малайська", "ms-MY"),
        Language("id", "Indonesian", "індонезійська", "id-ID"),
        Language("tl", "Filipino", "філіппінська", "fil-PH"),
        Language("hi", "Hindi", "гінді", "hi-IN"),
        Language("zh-Hant", "Traditional Chinese", "китайська (традиційна)", "zh-TW"),
        Language("pl", "Polish", "польська", "pl-PL"),
        Language("cs", "Czech", "чеська", "cs-CZ"),
        Language("nl", "Dutch", "нідерландська", "nl-NL"),
        Language("km", "Khmer", "кхмерська", "km-KH"),
        Language("my", "Burmese", "бірманська", "my-MM"),
        Language("fa", "Persian", "перська", "fa-IR"),
        Language("gu", "Gujarati", "гуджараті", "gu-IN"),
        Language("ur", "Urdu", "урду", "ur-PK"),
        Language("te", "Telugu", "телугу", "te-IN"),
        Language("mr", "Marathi", "маратхі", "mr-IN"),
        Language("he", "Hebrew", "іврит", "he-IL"),
        Language("bn", "Bengali", "бенгальська", "bn-BD"),
        Language("ta", "Tamil", "тамільська", "ta-IN"),
        Language("uk", "Ukrainian", "українська", "uk-UA"),
        Language("bo", "Tibetan", "тибетська", "bo-CN"),
        Language("kk", "Kazakh", "казахська", "kk-KZ"),
        Language("mn", "Mongolian", "монгольська", "mn-MN"),
        Language("ug", "Uyghur", "уйгурська", "ug-CN"),
        Language("yue", "Cantonese", "кантонська", "yue-HK"),
    ]

    _BY_CODE: dict[str, Language] = {language.code: language for language in ALL}
    _BY_LOWER_CODE: dict[str, Language] = {
        language.code.lower(): language for language in ALL
    }
    _BY_BCP47: dict[str, Language] = {
        language.bcp47.lower(): language for language in ALL if language.bcp47
    }

    @staticmethod
    def get(code: str) -> Language | None:
        """Look up a language by code, accepting ``auto`` and BCP-47 identifiers."""
        if not isinstance(code, str):
            return None
        value = code.strip()
        if not value:
            return None
        if value == LanguageTable.AUTO.code:
            return LanguageTable.AUTO
        found = LanguageTable._BY_CODE.get(value)
        if found is not None:
            return found
        lowered = value.lower()
        found = LanguageTable._BY_LOWER_CODE.get(lowered)
        if found is not None:
            return found
        return LanguageTable._BY_BCP47.get(lowered)

    @staticmethod
    def detect(
        text: str,
        preferred: AppLanguage | str = AppLanguage.SYSTEM,
        *,
        for_prompt: bool = False,
    ) -> Language | None:
        """Guess the language of *text*, mirroring ``Language.detect`` in Swift."""
        if not isinstance(text, str) or not text:
            return None
        sample = text[:600]
        if not sample:
            return None

        def has(ranges: tuple[tuple[int, int], ...]) -> bool:
            for character in sample:
                value = ord(character)
                for low, high in ranges:
                    if low <= value <= high:
                        return True
            return False

        if has(((0x3040, 0x30FF),)):
            return LanguageTable.get("ja")
        if has(((0xAC00, 0xD7AF), (0x1100, 0x11FF))):
            return LanguageTable.get("ko")
        if has(((0x0E00, 0x0E7F),)):
            return LanguageTable.get("th")
        if has(((0x0590, 0x05FF),)):
            return LanguageTable.get("he")
        if has(((0x0600, 0x06FF), (0x0750, 0x077F))):
            return _detect_arabic_script(sample)
        if has(((0x0900, 0x097F),)):
            # Hindi is a UI guess for Devanagari, which Marathi also uses.
            return None if for_prompt else LanguageTable.get("hi")
        if has(((0x0980, 0x09FF),)):
            return LanguageTable.get("bn")
        if has(((0x0B80, 0x0BFF),)):
            return LanguageTable.get("ta")
        if has(((0x0C00, 0x0C7F),)):
            return LanguageTable.get("te")
        if has(((0x0A80, 0x0AFF),)):
            return LanguageTable.get("gu")
        if has(((0x4E00, 0x9FFF), (0x3400, 0x4DBF))):
            return LanguageTable.get("zh")
        if has(((0x0400, 0x04FF),)):
            return _detect_cyrillic(sample, preferred)
        if has(((0x0530, 0x058F),)):
            return None
        if has(((0x10A0, 0x10FF),)):
            return None
        if has(((0x0041, 0x024F),)) and any(character.isalpha() for character in sample):
            guess = _guess_latin_language(sample)
            if guess is not None:
                language = LanguageTable.get(guess)
                if language is not None:
                    return language
            return LanguageTable.get("en")
        return None


# Unicode letters only: the Swift code splits on every non-letter character.
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_UNIQUE_WEIGHT = 3
_LATIN_MIN_SCORE = 3


def _detect_arabic_script(sample: str) -> Language | None:
    """Identify languages with distinct evidence in the shared script."""
    if any(letter in sample for letter in "ٹڈڑںھہے"):
        return LanguageTable.get("ur")

    words = set(_WORD_RE.findall(sample))
    persian = bool(words & {"است", "هست", "بود", "برای", "این", "بفرستید"})
    arabic = bool(words & {"هذا", "هذه", "ذلك", "الذي", "التي", "إلى"})
    if persian == arabic:
        return None
    return LanguageTable.get("fa" if persian else "ar")


def _detect_cyrillic(sample: str, preferred: AppLanguage | str) -> Language | None:
    """Ukrainian/Russian scoring copied from the Swift source."""
    lowered = sample.lower()
    uk_score = 0
    ru_score = 0
    for character in lowered:
        if character in ("і", "ї", "є", "ґ"):
            uk_score += 2
        elif character in ("ы", "э", "ё", "ъ"):
            ru_score += 2
        elif character == "’":
            uk_score += 1

    tokens = _WORD_RE.findall(lowered)
    uk_score += sum(1 for token in tokens if token in _UKRAINIAN_WORDS)
    ru_score += sum(1 for token in tokens if token in _RUSSIAN_WORDS)

    if uk_score > ru_score:
        return LanguageTable.get("uk")
    if ru_score > uk_score:
        return LanguageTable.get("ru")
    if coerce_app_language(preferred).resolved is AppLanguage.RU:
        return LanguageTable.get("ru")
    return LanguageTable.get("uk")


def _fold(value: str) -> str:
    """Lower-case and strip diacritics so ``cómo`` matches ``como``."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.casefold()


def _guess_latin_language(text: str) -> str | None:
    """Stop-word based replacement for ``NLLanguageRecognizer``."""
    words = [_fold(word) for word in _WORD_RE.findall(text.lower())]
    if not words:
        return None
    scores: dict[str, int] = {}
    for word in words:
        hits = [code for code in _LATIN_ORDER if word in _LATIN_STOP_WORDS[code]]
        if not hits:
            continue
        weight = _UNIQUE_WEIGHT if len(hits) == 1 else 1
        for code in hits:
            scores[code] = scores.get(code, 0) + weight
    if not scores:
        return None
    best_code = ""
    best_score = 0
    for code in _LATIN_ORDER:
        score = scores.get(code, 0)
        if score > best_score:
            best_code = code
            best_score = score
    if best_score < _LATIN_MIN_SCORE:
        return None
    return best_code


_UKRAINIAN_WORDS: frozenset[str] = frozenset(
    """
    що цей ця ці після або також вже ще рядок рядки мова переклад можна потрібно
    який яка які було цього мене тебе його її вони ми ви безкоштовно локальні
    хмарні провайдери
    """.split()
)

_RUSSIAN_WORDS: frozenset[str] = frozenset(
    """
    что это этот эта эти после или также ещё еще строка строки язык перевод можно
    нужно который которая которые было этого меня тебя его её они мы вы бесплатно
    локальные облачные провайдеры
    """.split()
)

_LATIN_ORDER: tuple[str, ...] = (
    "en", "fr", "de", "es", "pt", "it", "pl", "nl", "tr", "vi", "id", "ms",
)

_LATIN_STOPS: dict[str, str] = {
    "en": """
        the and is are was were this that these those with you your for of to it
        in on at by or but not have has had be been being from they them their we
        our will would can could should there what when which who whom how why
        about into than then just also very more most some any all no if so do
        does did my me he she his her its as up out one two because while between
        through during before after above below here where both each few other
        such only own same too again once please thanks hello
    """,
    "fr": """
        le la les des du de et est une un que qui dans pour avec sur pas ce cette
        ces au aux en il elle nous vous ils elles sont être avoir plus mais ou où
        comme tout tous toute toutes votre notre je tu mon ma mes ton ta tes son
        sa ses leur leurs par sans sous entre aussi très déjà encore toujours
        jamais bien faire fait dit bonjour merci salut oui non comment pourquoi
        quand quel quelle quels quelles ceci cela celui celle dont donc alors
        ainsi chez vers depuis pendant avant après à était étaient sera seront
        peut peuvent dois doit veut veux
    """,
    "de": """
        der die das den dem des ein eine einer eines einem einen und ist sind
        nicht mit für auf aus bei nach von zu zum zur im in ich du er sie es wir
        ihr sich auch aber oder wenn wie dass werden wird wurde worden haben hat
        hatte sein war waren mehr sehr noch nur kann können müssen muss über unter
        zwischen durch gegen ohne um als so dann dort hier was wer wo warum weil
        diese dieser dieses diesem diesen mein meine dein deine seine ihre unsere
        euer guten tag hallo danke bitte ja nein
    """,
    "es": """
        el la los las un una unos unas de del y o que en es son está están este
        esta estos estas ese esa esos esas por para con sin sobre entre no sí se
        su sus mi mis tu tus nuestro nuestra al lo le les me te nos os como cuando
        donde porque pero más muy también ya hay ha han he fue ser estar tiene
        tienen puede pueden todo todos toda todas otro otra otros otras hacer hace
        dice dijo bien mal gracias hola buenos días servicio
    """,
    "pt": """
        o os as um uma uns umas de do da dos das e ou que em no na nos nas é são
        está estão este esta estes estas esse essa por para com sem sobre entre
        não sim se seu sua seus suas meu minha nosso nossa ao lhe me te vos como
        quando onde porque mas mais muito também já há foi ser estar tem têm pode
        podem todo todos toda todas fazer faz diz disse obrigado olá bom dia não
        não você vocês isso isto aquilo pelo pela pelos pelas dos das nas aos às num
        numa serviço tradução funciona
    """,
    "it": """
        il lo la i gli le un uno una di del della dei delle che nel nella è sono
        questo questa questi queste quello quella per con senza su tra fra non sì
        si suo sua suoi sue mio mia nostro nostra al alla allo ai alle come quando
        dove perché ma più molto anche già ha hanno ho fu essere stare stato può
        possono tutto tutti tutta tutte fare fa dice detto bene male grazie ciao
        buongiorno è
    """,
    "pl": """
        i w z na do nie że się jest są to ten ta te tego tej tych za od po przez
        przy o jak ale albo lub czy tak bardzo jeszcze już tylko może można mieć
        ma mają był była było były oraz dla bez pod nad między który która które
        których tym tego nie ma dziękuję cześć dzień dobry
    """,
    "nl": """
        de het een en van in op te dat die dit deze is zijn was waren niet met voor
        aan bij uit naar door over onder tussen tegen zonder om als maar of ook
        nog al heel zeer kan kunnen moet moeten hebben heeft had ik jij je hij zij
        ze wij we jullie u mijn jouw haar ons hun dit dank je hallo goedemorgen
    """,
    "tr": """
        ve bir bu şu o da de ile için olan olarak var yok çok daha en gibi ama
        fakat veya ya ki ne nasıl neden çünkü her bazı tüm ben sen biz siz onlar
        benim senin onun bizim sizin onların değil mi mı mu mü teşekkür merhaba
    """,
    "vi": """
        và là của có không được trong cho một những các với để này đó khi như
        nhưng hoặc thì mà tôi bạn anh chị em chúng họ người việc rất cũng đã sẽ
        đang về từ đến theo trên dưới xin chào cảm ơn
    """,
    "id": """
        dan yang di ke dari untuk dengan ini itu tidak ada adalah akan sudah telah
        pada dalam oleh juga bisa dapat karena tetapi atau jika ketika setelah
        sebelum saya kamu dia kami kita mereka sangat lebih semua banyak terima
        kasih selamat pagi sebuah terjemahan tes baik satu buku orang dunia
        bahasa
    """,
    "ms": """
        dan yang di ke dari untuk dengan ini itu tidak tiada akan telah pada
        dalam oleh juga boleh dapat kerana tetapi atau jika apabila selepas
        sebelum saya kamu dia kami kita mereka sangat lebih semua banyak terima
        kasih selamat pagi ialah anda awak terjemahan baik satu ujian bahasa
    """,
}

_LATIN_STOP_WORDS: dict[str, frozenset[str]] = {
    code: frozenset(_fold(word) for word in words.split())
    for code, words in _LATIN_STOPS.items()
}


AUTO: Language = LanguageTable.AUTO
ALL: list[Language] = LanguageTable.ALL


def get_language(code: str) -> Language | None:
    """Module level shortcut for :meth:`LanguageTable.get`."""
    return LanguageTable.get(code)


def detect_language(
    text: str,
    preferred: AppLanguage | str = AppLanguage.SYSTEM,
) -> Language | None:
    """Module level shortcut for :meth:`LanguageTable.detect`."""
    return LanguageTable.detect(text, preferred)
