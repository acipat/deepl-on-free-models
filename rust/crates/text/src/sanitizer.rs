//! Output cleanup and translation validation for the translation pipeline.
//!
//! Port of `windows/deepl_ofm/core/sanitizer.py`, which follows
//! `Sources/HyMT/Support/OutputSanitizer.swift` (leaked chat-template tokens)
//! plus the block validation helpers from
//! `Sources/HyMT/Services/TranslationService.swift` (`validated` /
//! `translateBlock`: empty, repetition, script, role-token, instruction-echo,
//! meta-answer and length checks). Every check mirrors the Swift thresholds and
//! marker lists; [`OutputSanitizer::is_degenerate`] returns the compact set of
//! reasons documented in `CONTRACTS.md`.

use std::collections::HashSet;
use std::sync::OnceLock;

use regex::Regex;

use crate::chunker::TextChunker;

/// Leaked Hy-MT chat-template fragments removed before validation.
const KNOWN_LEAKS: [&str; 9] = [
    "<｜hy_place\u{2581}holder\u{2581}no\u{2581}2｜>",
    "<｜hy_place\u{2581}holder\u{2581}no\u{2581}8｜>",
    "<｜hy_end\u{2581}of\u{2581}sentence｜>",
    "｜hy_end\u{2581}of\u{2581}sentence｜",
    "｜hy_end",
    "hy-Assistant",
    "hy-User",
    "hy_Assistant",
    "hy_User",
];

const RE_HY_TOKEN: &str = r"[<｜|]hy_[A-Za-z0-9_▁]*[>|]?";
const RE_HY_TAIL: &str = r"[<｜|]\s*hy[-_/]?[A-Za-z]*[^>]*";
const RE_OPEN_ANGLE: &str = r"<｜[^>]*$";
const RE_OPEN_CLOSE: &str = r"</｜[^>]*$";
/// Python's `$` also matches just before a final newline; `(?:$|\n\z)` keeps
/// that behaviour so a dangling token is removed even at the end of a stream.
const RE_TRAILING_HY: &str = r"｜hy[^\s]*(?:$|\n\z)";
const RE_TRAILING_BRACKET: &str = r"[<｜|]\s*$";

/// `Here is the translation:` / `Ось переклад тексту:` wrappers.
const PREAMBLE_COLON: &str = concat!(
    r"(?i)^(?:",
    r"Ось\s+(?:ваш\s+|твій\s+)?(?:переклад|текст\s+у\s+перекладі)",
    r"(?:[^:\n]{0,50})?",
    r"|Звісно,?\s+ось(?:[^:\n]{0,50})?",
    r"|Here(?:'s|\s+is)\s+(?:the\s+|your\s+)?translation(?:[^:\n]{0,50})?",
    r"|The\s+translation\s+is",
    r"|Translation",
    r"|Вот\s+перевод",
    r"|Перевод\s+текста",
    r")\s*:\s*",
);
const PREAMBLE_FILLER: &str = r"(?i)^(?:Звісно|Звичайно|Ось)[!,.]\s*";

/// Characters that open a quoted translation.
const OPEN_QUOTES: [char; 3] = ['«', '\u{201C}', '"'];
/// Characters that close a quoted translation.
const CLOSE_QUOTES: [char; 3] = ['»', '\u{201D}', '"'];

/// Targets written with CJK ideographs (Japanese included).
const CJK_TARGET_CODES: [&str; 5] = ["zh", "zh-hant", "zh-hans", "yue", "ja"];
/// Targets written in Cyrillic.
const CYRILLIC_TARGET_CODES: [&str; 8] = ["uk", "ru", "be", "bg", "mk", "sr", "kk", "mn"];

const CJK_RANGES: [(u32, u32); 2] = [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)];
const CYRILLIC_RANGES: [(u32, u32); 1] = [(0x0400, 0x04FF)];
const LATIN_RANGES: [(u32, u32); 1] = [(0x0041, 0x024F)];

const UKRAINIAN_ALPHABET: &str = concat!(
    "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя",
    "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
);
const RUSSIAN_ALPHABET: &str = concat!(
    "абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
);

const INSTRUCTION_MARKERS: [&str; 13] = [
    "preserve markdown syntax",
    "translate only the human-readable text",
    "translation style must strictly conform",
    "output only the translated heading",
    "output only the translated text",
    "here is the translation",
    "here's the translation",
    "the translation is",
    "ось переклад",
    "звісно, ось",
    "переклад тексту",
    "вот перевод",
    "перевод текста",
];

const FIRST_PERSON_SOURCE: [&str; 20] = [
    " i ",
    "i'",
    " me ",
    " my ",
    " we ",
    "we'",
    " us ",
    " our ",
    " я ",
    " мене ",
    " мені ",
    " мій ",
    " моя ",
    " ми ",
    " нас ",
    " наш ",
    " меня ",
    " мне ",
    " мой ",
    " мы ",
];

const META_MARKERS: [&str; 11] = [
    "я рекомендую",
    "я реком",
    "я можу допомогти",
    "я не можу",
    "якщо вам потрібно",
    "сподіваюся",
    "надіюся",
    "i recommend",
    "i can help",
    "i cannot",
    "let me know",
];

static HY_TOKEN_RE: OnceLock<Option<Regex>> = OnceLock::new();
static HY_TAIL_RE: OnceLock<Option<Regex>> = OnceLock::new();
static OPEN_ANGLE_RE: OnceLock<Option<Regex>> = OnceLock::new();
static OPEN_CLOSE_RE: OnceLock<Option<Regex>> = OnceLock::new();
static TRAILING_HY_RE: OnceLock<Option<Regex>> = OnceLock::new();
static TRAILING_BRACKET_RE: OnceLock<Option<Regex>> = OnceLock::new();
static PREAMBLE_COLON_RE: OnceLock<Option<Regex>> = OnceLock::new();
static PREAMBLE_FILLER_RE: OnceLock<Option<Regex>> = OnceLock::new();

/// Compile `pattern` once; a malformed pattern simply matches nothing.
fn compiled(slot: &'static OnceLock<Option<Regex>>, pattern: &str) -> Option<&'static Regex> {
    slot.get_or_init(|| Regex::new(pattern).ok()).as_ref()
}

/// Minimal interface the sanitizer needs from a target language.
///
/// It is implemented for `str`/`String` (handy in tests and in code that only
/// has a language code) and for [`ofm_i18n::Language`] (the production caller).
pub trait TargetLanguage {
    /// The target language code used to pick the expected script.
    fn language_code(&self) -> &str;
}

impl TargetLanguage for str {
    fn language_code(&self) -> &str {
        self
    }
}

impl TargetLanguage for String {
    fn language_code(&self) -> &str {
        self.as_str()
    }
}

impl TargetLanguage for ofm_i18n::Language {
    fn language_code(&self) -> &str {
        self.code
    }
}

/// Why the model output was rejected; `None` from
/// [`OutputSanitizer::is_degenerate`] means acceptable.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum DegenerateReason {
    /// The output was empty after wrapper cleanup.
    Empty,
    /// The output repeats itself or contains replacement characters.
    Repetition,
    /// The output is not written in the target script.
    Script,
    /// Chat-template role or special tokens leaked into the output.
    RoleTokens,
    /// The model echoed the instruction or answered instead of translating.
    Echo,
    /// The output is implausibly short or long for the source.
    Length,
}

impl DegenerateReason {
    /// Stable label used in logs and reason payloads.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Empty => "empty",
            Self::Repetition => "repetition",
            Self::Script => "script",
            Self::RoleTokens => "role_tokens",
            Self::Echo => "echo",
            Self::Length => "length",
        }
    }
}

/// Language code for `target`, matching the contract's `Language::code`.
fn target_code<T: TargetLanguage + ?Sized>(target: &T) -> &str {
    target.language_code()
}

fn is_cjk_code(code: &str) -> bool {
    let lowered = code.to_lowercase();
    CJK_TARGET_CODES.contains(&lowered.as_str())
}

/// True for targets written with CJK ideographs (Japanese included).
pub fn uses_cjk_script(code: &str) -> bool {
    is_cjk_code(code)
}

/// Characters of the expected script for `code`.
fn script_ranges(code: &str) -> &'static [(u32, u32)] {
    match code.to_lowercase().as_str() {
        "uk" | "ru" | "be" | "bg" | "mk" | "kk" | "mn" => &CYRILLIC_RANGES,
        "sr" => &[(0x0400, 0x04FF), (0x0041, 0x024F)],
        "zh" | "zh-hant" | "zh-hans" | "yue" => &CJK_RANGES,
        "ja" => &[(0x3040, 0x30FF), (0x4E00, 0x9FFF)],
        "ko" => &[(0xAC00, 0xD7AF), (0x1100, 0x11FF)],
        "ar" | "fa" | "ur" | "ug" => &[(0x0600, 0x06FF), (0x0750, 0x077F)],
        "he" => &[(0x0590, 0x05FF)],
        "th" => &[(0x0E00, 0x0E7F)],
        "hi" | "mr" => &[(0x0900, 0x097F)],
        "bn" => &[(0x0980, 0x09FF)],
        "ta" => &[(0x0B80, 0x0BFF)],
        "te" => &[(0x0C00, 0x0C7F)],
        "gu" => &[(0x0A80, 0x0AFF)],
        "km" => &[(0x1780, 0x17FF)],
        "my" => &[(0x1000, 0x109F)],
        "bo" => &[(0x0F00, 0x0FFF)],
        _ => &LATIN_RANGES,
    }
}

fn has_ranges(text: &str, ranges: &[(u32, u32)]) -> bool {
    text.chars().any(|character| {
        let value = character as u32;
        ranges
            .iter()
            .any(|(low, high)| *low <= value && value <= *high)
    })
}

/// Number of repeated 40-character shingles sampled every 20 characters.
fn count_repetitions(text: &str) -> usize {
    let characters: Vec<char> = text.chars().collect();
    if characters.len() < 40 {
        return 0;
    }
    let mut shingles: HashSet<String> = HashSet::new();
    let mut duplicates = 0usize;
    let mut index = 0usize;
    while index + 40 <= characters.len() {
        let shingle: String = characters[index..index + 40].iter().collect();
        if !shingles.insert(shingle) {
            duplicates += 1;
        }
        index += 20;
    }
    duplicates
}

/// Removes leaked template tokens and rejects degenerate model output.
pub struct OutputSanitizer;

impl OutputSanitizer {
    /// Remove chat-template / special-token wrappers and surrounding space.
    ///
    /// Byte-for-byte port of `OutputSanitizer.clean`. It removes known Hy-MT
    /// leaks (`<｜hy_place▁holder▁no▁2｜>`, `｜hy_end`, `hy-Assistant` …),
    /// generic `hy_*` fragments, a dangling partial token at the end of the
    /// stream, U+FFFD and NUL characters.
    ///
    /// "Here is the translation:" preambles are handled separately by
    /// [`OutputSanitizer::strip_preamble`], mirroring
    /// `TranslationService.stripPreamble`.
    pub fn strip_wrappers(text: &str) -> String {
        let mut value = text.to_string();
        for token in KNOWN_LEAKS {
            if value.contains(token) {
                value = value.replace(token, "");
            }
        }
        for regex in [
            compiled(&HY_TOKEN_RE, RE_HY_TOKEN),
            compiled(&HY_TAIL_RE, RE_HY_TAIL),
            compiled(&OPEN_ANGLE_RE, RE_OPEN_ANGLE),
            compiled(&OPEN_CLOSE_RE, RE_OPEN_CLOSE),
            compiled(&TRAILING_HY_RE, RE_TRAILING_HY),
            compiled(&TRAILING_BRACKET_RE, RE_TRAILING_BRACKET),
        ]
        .into_iter()
        .flatten()
        {
            value = regex.replace_all(&value, "").into_owned();
        }
        value = value.replace(['\u{FFFD}', '\0'], "");
        value.trim().to_string()
    }

    /// Swift-compatible alias of [`OutputSanitizer::strip_wrappers`].
    pub fn clean(text: &str) -> String {
        Self::strip_wrappers(text)
    }

    /// Remove "Here is the translation:" / "Ось переклад тексту:" wrappers.
    ///
    /// Port of `TranslationService.stripPreamble`. A preamble that is also
    /// present in `source` is left alone, and the closing quote of a quoted
    /// translation is removed together with the opening one.
    pub fn strip_preamble(text: &str, source: &str) -> String {
        let mut value = text.trim().to_string();
        let source_lower = source.to_lowercase();
        let mut removed_preamble = false;
        for pattern in [
            compiled(&PREAMBLE_COLON_RE, PREAMBLE_COLON),
            compiled(&PREAMBLE_FILLER_RE, PREAMBLE_FILLER),
        ]
        .into_iter()
        .flatten()
        {
            let Some(found) = pattern.find(&value) else {
                continue;
            };
            if source_lower.contains(&found.as_str().to_lowercase()) {
                continue;
            }
            let start = found.start();
            let end = found.end();
            value = format!("{}{}", &value[..start], &value[end..])
                .trim()
                .to_string();
            removed_preamble = true;
        }

        if removed_preamble {
            if let Some(first) = value.chars().next() {
                if OPEN_QUOTES.contains(&first) {
                    let mut characters: Vec<char> = value.chars().collect();
                    characters.remove(0);
                    if let Some(position) = characters
                        .iter()
                        .position(|character| CLOSE_QUOTES.contains(character))
                    {
                        characters.remove(position);
                    }
                    value = characters
                        .into_iter()
                        .collect::<String>()
                        .trim()
                        .to_string();
                }
            }
        }
        value
    }

    /// True when chat-template role or special tokens are still present.
    pub fn has_role_tokens(text: &str) -> bool {
        let lower = text.to_lowercase();
        if lower.contains("hy-assistant") || lower.contains("hy-user") || lower.contains("hy_end") {
            return true;
        }
        text.contains("<｜") || text.contains("<|") || text.contains("</|") || text.contains("｜hy")
    }

    /// True when `text` contains at least one character of the target script.
    ///
    /// Port of `TranslationService.hasTargetScript`: a text without any letters
    /// passes (there is nothing to translate), otherwise it must contain a
    /// character from the script expected for the target code.
    pub fn script_ok<T: TargetLanguage + ?Sized>(text: &str, target: &T) -> bool {
        if !text.chars().any(|character| character.is_alphabetic()) {
            return true;
        }
        let code = target_code(target);
        has_ranges(text, script_ranges(code))
    }

    /// True when every Cyrillic character belongs to the target alphabet.
    ///
    /// Ukrainian and Russian have well-defined alphabets; Belarusian or Serbian
    /// letters inside a Ukrainian word indicate degeneration.
    pub fn uses_allowed_cyrillic<T: TargetLanguage + ?Sized>(text: &str, target: &T) -> bool {
        let code = target_code(target);
        let alphabet: &str = match code {
            "uk" => UKRAINIAN_ALPHABET,
            "ru" => RUSSIAN_ALPHABET,
            _ => return true,
        };
        !text.chars().any(|character| {
            ('\u{0400}'..='\u{04FF}').contains(&character) && !alphabet.contains(character)
        })
    }

    /// Validate one translated block.
    ///
    /// Returns `None` for acceptable output, otherwise the first
    /// [`DegenerateReason`] that applies.
    ///
    /// The checks and their order follow `TranslationService.validated`:
    /// replacement characters, empty output, short output, target script, role
    /// tokens, instruction echo, first-person meta answers, foreign script
    /// contamination, excessive length and internal repetition. Wrapper tokens
    /// are stripped before the textual checks, exactly like Swift's
    /// `OutputSanitizer.clean` call inside `validated`.
    ///
    /// Call [`OutputSanitizer::strip_preamble`] on the raw model output first
    /// (as Swift's `bufferedTranslation` does): this method deliberately
    /// reports a remaining "Here is the translation:" preamble as an
    /// [`DegenerateReason::Echo`] failure.
    pub fn is_degenerate<T: TargetLanguage + ?Sized>(
        source: &str,
        translated: &str,
        target: &T,
    ) -> Option<DegenerateReason> {
        if translated.contains('\u{FFFD}') {
            return Some(DegenerateReason::Repetition);
        }

        let cleaned = Self::strip_wrappers(translated);
        if cleaned.is_empty() {
            return Some(DegenerateReason::Empty);
        }

        let code = target_code(target);
        let source_count = source.chars().count();
        let cleaned_count = cleaned.chars().count();

        if source_count >= 60 && cleaned_count < source_count / 4 {
            return Some(DegenerateReason::Length);
        }
        if source_count >= 60
            && cleaned_count < source_count / 2
            && !is_cjk_code(code)
            && TextChunker::split_sentences(source).len() > 1
            && TextChunker::split_sentences(&cleaned).len() == 1
        {
            return Some(DegenerateReason::Length);
        }

        if !Self::script_ok(&cleaned, target) {
            return Some(DegenerateReason::Script);
        }
        if Self::has_role_tokens(&cleaned) {
            return Some(DegenerateReason::RoleTokens);
        }

        let lower = cleaned.to_lowercase();
        let source_lower = source.to_lowercase();
        for marker in INSTRUCTION_MARKERS {
            if lower.contains(marker) && !source_lower.contains(marker) {
                return Some(DegenerateReason::Echo);
            }
        }

        let padded_source = format!(" {source_lower} ");
        if !FIRST_PERSON_SOURCE
            .iter()
            .any(|marker| padded_source.contains(marker))
            && META_MARKERS.iter().any(|marker| lower.contains(marker))
        {
            return Some(DegenerateReason::Echo);
        }

        if !is_cjk_code(code) && has_ranges(&cleaned, &CJK_RANGES) {
            return Some(DegenerateReason::Script);
        }
        if !CYRILLIC_TARGET_CODES.contains(&code) {
            if has_ranges(&cleaned, &CYRILLIC_RANGES) {
                return Some(DegenerateReason::Script);
            }
        } else if (code == "uk" || code == "ru") && !Self::uses_allowed_cyrillic(&cleaned, target) {
            return Some(DegenerateReason::Script);
        }

        if source_count >= 40 && cleaned_count > source_count.saturating_mul(4) {
            return Some(DegenerateReason::Length);
        }
        if source_count < 40 && cleaned_count > 120.max(source_count.saturating_mul(8)) {
            return Some(DegenerateReason::Length);
        }

        if cleaned_count > 120 && count_repetitions(&cleaned) > 1 {
            return Some(DegenerateReason::Repetition);
        }

        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn target_script_presence() {
        assert!(OutputSanitizer::script_ok("Привіт", "uk"));
        assert!(!OutputSanitizer::script_ok("Hello", "uk"));
        assert!(OutputSanitizer::script_ok("Hello", "en"));
        assert!(!OutputSanitizer::script_ok("Привіт", "en"));
        assert!(OutputSanitizer::script_ok("こんにちは", "ja"));
        assert!(!OutputSanitizer::script_ok("Hello", "ja"));
    }

    #[test]
    fn cjk_script_includes_japanese() {
        assert!(uses_cjk_script("ja"));
        assert!(uses_cjk_script("zh-Hant"));
        assert!(!uses_cjk_script("en"));
    }

    #[test]
    fn ukrainian_alphabet() {
        assert!(OutputSanitizer::uses_allowed_cyrillic(
            "Привіт, це український текст.",
            "uk"
        ));
        assert!(!OutputSanitizer::uses_allowed_cyrillic("маў", "uk"));
        assert!(!OutputSanitizer::uses_allowed_cyrillic("цѯнструмент", "uk"));
        assert!(!OutputSanitizer::uses_allowed_cyrillic("коштуђуце", "uk"));
    }

    #[test]
    fn russian_alphabet() {
        assert!(OutputSanitizer::uses_allowed_cyrillic(
            "Привет, это русский текст.",
            "ru"
        ));
        assert!(!OutputSanitizer::uses_allowed_cyrillic("Привіт", "ru"));
    }

    #[test]
    fn script_ok_accepts_letterless_text() {
        assert!(OutputSanitizer::script_ok("123 — 456", "uk"));
        assert!(OutputSanitizer::script_ok("", "uk"));
    }

    #[test]
    fn preamble_is_stripped() {
        assert_eq!(
            OutputSanitizer::strip_preamble(
                "Ось переклад тексту: «Привіт». Далі текст.",
                "Hello. More text.",
            ),
            "Привіт. Далі текст."
        );
        assert_eq!(
            OutputSanitizer::strip_preamble("Here is the translation: Hello.", "Привіт."),
            "Hello."
        );
        assert_eq!(
            OutputSanitizer::strip_preamble(
                "Звісно! Цей пакет коштує 57 доларів.",
                "The bundle costs $57.",
            ),
            "Цей пакет коштує 57 доларів."
        );
    }

    #[test]
    fn preamble_is_not_stripped_when_it_is_source_text() {
        let source = "Here is the translation: a phrase to translate";
        assert_eq!(
            OutputSanitizer::strip_preamble(source, source),
            source.to_string()
        );
    }

    #[test]
    fn strip_preamble_english_and_russian_variants() {
        assert_eq!(
            OutputSanitizer::strip_preamble("Here's the translation: Good morning.", ""),
            "Good morning."
        );
        assert_eq!(
            OutputSanitizer::strip_preamble("The translation is: Good morning.", ""),
            "Good morning."
        );
        assert_eq!(
            OutputSanitizer::strip_preamble("Вот перевод: Доброе утро.", ""),
            "Доброе утро."
        );
    }

    #[test]
    fn strip_wrappers_removes_known_leaks() {
        let known = [
            "<｜hy_place\u{2581}holder\u{2581}no\u{2581}2｜>",
            "<｜hy_place\u{2581}holder\u{2581}no\u{2581}8｜>",
            "<｜hy_end\u{2581}of\u{2581}sentence｜>",
            "｜hy_end\u{2581}of\u{2581}sentence｜",
            "｜hy_end",
            "hy-Assistant",
            "hy-User",
            "hy_Assistant",
            "hy_User",
        ];
        for token in known {
            assert_eq!(
                OutputSanitizer::strip_wrappers(&format!("Привіт{token}")),
                "Привіт",
                "suffix {token:?}"
            );
            assert_eq!(
                OutputSanitizer::strip_wrappers(&format!("{token}Привіт")),
                "Привіт",
                "prefix {token:?}"
            );
        }
    }

    #[test]
    fn strip_wrappers_removes_generic_hy_fragments() {
        assert_eq!(OutputSanitizer::strip_wrappers("Hello<hy_token>"), "Hello");
        assert_eq!(
            OutputSanitizer::strip_wrappers("Hello<｜hy_end\u{2581}of\u{2581}sentence｜>"),
            "Hello"
        );
        assert_eq!(OutputSanitizer::strip_wrappers("Hello｜hy_end"), "Hello");
        assert_eq!(OutputSanitizer::strip_wrappers("Hello<"), "Hello");
    }

    #[test]
    fn strip_wrappers_removes_replacement_and_nul() {
        assert_eq!(
            OutputSanitizer::strip_wrappers("При\u{FFFD}віт\0"),
            "Привіт"
        );
    }

    #[test]
    fn strip_wrappers_trims_whitespace() {
        assert_eq!(OutputSanitizer::strip_wrappers("  \n Hello \n "), "Hello");
        assert_eq!(OutputSanitizer::strip_wrappers(""), "");
        assert_eq!(OutputSanitizer::clean("Hi｜hy_end"), "Hi");
    }

    #[test]
    fn strip_wrappers_removes_dangling_token_before_trailing_newline() {
        // Python's `$` matches before a final newline; the port keeps that.
        assert_eq!(OutputSanitizer::strip_wrappers("Привіт｜hy\n"), "Привіт");
        assert_eq!(
            OutputSanitizer::strip_wrappers("Привіт｜hy_end\n"),
            "Привіт"
        );
    }

    #[test]
    fn has_role_tokens() {
        for value in [
            "hy-Assistant",
            "hy-User",
            "hy_end",
            "<|im_end|>",
            "<|start_header_id|>",
            "｜hy",
            "</|",
        ] {
            assert!(
                OutputSanitizer::has_role_tokens(&format!("Text {value}")),
                "value {value:?}"
            );
        }
        assert!(!OutputSanitizer::has_role_tokens(
            "Just a normal translation."
        ));
    }

    #[test]
    fn valid_translation_is_not_degenerate() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello, world!", "Привіт, світе!", "uk"),
            None
        );
    }

    #[test]
    fn empty_output() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "", "en"),
            Some(DegenerateReason::Empty)
        );
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "   \n\t ", "en"),
            Some(DegenerateReason::Empty)
        );
    }

    #[test]
    fn replacement_character_is_rejected() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello", "При\u{FFFD}віт", "uk"),
            Some(DegenerateReason::Repetition)
        );
    }

    #[test]
    fn script_mismatch() {
        // The model echoed English into a Ukrainian target.
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "Hello.", "uk"),
            Some(DegenerateReason::Script)
        );
        // Cyrillic text targeting English.
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "Привіт.", "en"),
            Some(DegenerateReason::Script)
        );
        // CJK text targeting a non-CJK language.
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "你好。", "en"),
            Some(DegenerateReason::Script)
        );
    }

    #[test]
    fn cjk_targets_accept_cjk() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "你好。", "zh"),
            None
        );
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "こんにちは。", "ja"),
            None
        );
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "안녕하세요.", "ko"),
            None
        );
    }

    #[test]
    fn disallowed_cyrillic_letters_are_rejected() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Привіт.", "маў", "uk"),
            Some(DegenerateReason::Script)
        );
        assert_eq!(
            OutputSanitizer::is_degenerate("Привет.", "Привіт", "ru"),
            Some(DegenerateReason::Script)
        );
    }

    #[test]
    fn role_tokens_are_rejected() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "Hello <|im_end|>", "en"),
            Some(DegenerateReason::RoleTokens)
        );
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "Hello <|start_header_id|>assistant", "en"),
            Some(DegenerateReason::RoleTokens)
        );
    }

    #[test]
    fn known_leaks_are_cleaned_before_validation() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "Привіт｜hy_end", "uk"),
            None
        );
    }

    #[test]
    fn instruction_echo_is_rejected() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Привіт.", "Here is the translation: Hello.", "en"),
            Some(DegenerateReason::Echo)
        );
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "Preserve Markdown syntax exactly", "en"),
            Some(DegenerateReason::Echo)
        );
        assert_eq!(
            OutputSanitizer::is_degenerate(
                "Hello.",
                "The translation style must strictly conform to [literal]",
                "en"
            ),
            Some(DegenerateReason::Echo)
        );
    }

    #[test]
    fn instruction_marker_in_source_is_allowed() {
        let source = "The translation is a complex subject.";
        assert_eq!(
            OutputSanitizer::is_degenerate(source, "Переклад — це складна тема.", "uk"),
            None
        );
    }

    #[test]
    fn first_person_meta_answer_is_rejected() {
        assert_eq!(
            OutputSanitizer::is_degenerate(
                "Купити цей продукт.",
                "I recommend this product.",
                "en"
            ),
            Some(DegenerateReason::Echo)
        );
        assert_eq!(
            OutputSanitizer::is_degenerate("Купи цей продукт.", "Я можу допомогти з цим.", "uk"),
            Some(DegenerateReason::Echo)
        );
    }

    #[test]
    fn first_person_source_allows_first_person_translation() {
        let source = "I recommend this product because it works.";
        assert_eq!(OutputSanitizer::is_degenerate(source, source, "en"), None);
    }

    #[test]
    fn short_output_is_rejected() {
        let source = "This is a long source sentence that has plenty of words in it. ".repeat(2);
        assert_eq!(
            OutputSanitizer::is_degenerate(&source, "Short.", "en"),
            Some(DegenerateReason::Length)
        );
    }

    #[test]
    fn collapsed_sentences_are_rejected() {
        let source = "This is sentence number one of the text. \
                      This is sentence number two of the text.";
        assert_eq!(
            OutputSanitizer::is_degenerate(source, "This is a short one.", "en"),
            Some(DegenerateReason::Length)
        );
    }

    #[test]
    fn excessive_length_is_rejected() {
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", &"x".repeat(121), "en"),
            Some(DegenerateReason::Length)
        );
        let long_source = "A sentence with enough characters to cross forty. ".repeat(2);
        assert_eq!(
            OutputSanitizer::is_degenerate(
                &long_source,
                &"y".repeat(long_source.chars().count() * 4 + 1),
                "en"
            ),
            Some(DegenerateReason::Length)
        );
    }

    #[test]
    fn repetition_is_rejected() {
        let repeated = "abcdefghij".repeat(20);
        assert_eq!(
            OutputSanitizer::is_degenerate(&repeated, &repeated, "en"),
            Some(DegenerateReason::Repetition)
        );
    }

    #[test]
    fn short_source_and_short_translation_pass() {
        assert_eq!(OutputSanitizer::is_degenerate("Hi.", "Привіт.", "uk"), None);
    }

    #[test]
    fn language_lookup_used_by_the_sanitizer() {
        for code in ["uk", "ru", "en", "ja", "zh", "de"] {
            let expected = !matches!(code, "uk" | "ru" | "ja" | "zh");
            assert_eq!(
                OutputSanitizer::script_ok("Hello", code),
                expected,
                "code {code}"
            );
        }
    }

    #[test]
    fn reasons_have_stable_labels() {
        assert_eq!(DegenerateReason::Empty.as_str(), "empty");
        assert_eq!(DegenerateReason::Repetition.as_str(), "repetition");
        assert_eq!(DegenerateReason::Script.as_str(), "script");
        assert_eq!(DegenerateReason::RoleTokens.as_str(), "role_tokens");
        assert_eq!(DegenerateReason::Echo.as_str(), "echo");
        assert_eq!(DegenerateReason::Length.as_str(), "length");
    }

    #[test]
    fn i18n_language_targets_are_accepted() {
        let ukrainian = ofm_i18n::LanguageTable::get("uk").expect("uk language");
        let english = ofm_i18n::LanguageTable::get("en").expect("en language");
        assert!(OutputSanitizer::script_ok("Привіт", ukrainian));
        assert!(!OutputSanitizer::script_ok("Hello", ukrainian));
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello, world!", "Привіт, світе!", ukrainian),
            None
        );
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello.", "Hello.", ukrainian),
            Some(DegenerateReason::Script)
        );
        assert!(OutputSanitizer::uses_allowed_cyrillic("Привіт", ukrainian));
        assert_eq!(
            OutputSanitizer::is_degenerate("Hi.", "Привіт.", english),
            Some(DegenerateReason::Script)
        );
        let japanese = ofm_i18n::LanguageTable::get("ja").expect("ja language");
        assert!(uses_cjk_script(japanese.code));
        assert!(OutputSanitizer::script_ok("こんにちは", japanese));
    }

    #[test]
    fn string_targets_are_accepted() {
        let owned = String::from("uk");
        assert!(OutputSanitizer::script_ok("Привіт", &owned));
        assert_eq!(
            OutputSanitizer::is_degenerate("Hello", "Привіт", &owned),
            None
        );
    }

    #[test]
    fn pathological_inputs_do_not_panic() {
        let cases = [
            "",
            " ",
            "\0\0",
            "\u{FFFD}",
            "<｜",
            "</｜",
            "｜hy",
            "<hy_",
            "```",
            "\u{0400}",
            "\u{04FF}",
            "\u{4E00}",
            "Привіт",
            "о",
            "Ось",
            "Звісно",
            "Here",
            "The translation is",
            "Translation:",
            "«»",
            "\"\"",
            "“”",
        ];
        for case in cases {
            let cleaned = OutputSanitizer::strip_wrappers(case);
            let _ = OutputSanitizer::strip_preamble(case, case);
            let _ = OutputSanitizer::strip_preamble(case, "");
            let _ = OutputSanitizer::has_role_tokens(case);
            let _ = OutputSanitizer::script_ok(case, "uk");
            let _ = OutputSanitizer::script_ok(case, "en");
            let _ = OutputSanitizer::uses_allowed_cyrillic(case, "uk");
            let _ = OutputSanitizer::is_degenerate(case, case, "uk");
            let _ = OutputSanitizer::is_degenerate(case, &cleaned, "en");
            let _ = OutputSanitizer::is_degenerate(&cleaned, case, "ja");
        }
    }

    #[test]
    fn long_varied_translation_is_not_rejected() {
        let words = [
            "слово",
            "текст",
            "переклад",
            "мова",
            "рядок",
            "документ",
            "речення",
            "абзац",
        ];
        let mut varied = String::new();
        for index in 0..400 {
            varied.push_str(words[index % words.len()]);
            varied.push_str(&index.to_string());
            varied.push(' ');
        }
        varied.push('.');
        assert!(varied.chars().count() > 1000);
        // A faithful, varied translation in the target script passes every check.
        assert_eq!(OutputSanitizer::is_degenerate(&varied, &varied, "uk"), None);
    }

    #[test]
    fn repetition_inside_a_long_translation_is_rejected() {
        let repeated = "abcdefghij".repeat(20);
        let source = "A source sentence that is long enough to avoid the short-output rule here.";
        assert_eq!(
            OutputSanitizer::is_degenerate(source, &repeated, "en"),
            Some(DegenerateReason::Repetition)
        );
    }
}
