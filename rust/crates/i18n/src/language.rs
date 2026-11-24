//! The 38 Hy-MT2 languages and the script based language detector.
//!
//! Ported from `windows/deepl_ofm/core/languages.py`, which in turn mirrors
//! `Sources/HyMT/Models/Language.swift`. The macOS `NLLanguageRecognizer` of the
//! Swift app is replaced by the Python port's stop-word scorer: script ranges
//! first, then Ukrainian/Russian word scoring, then a Latin stop-word scorer
//! that falls back to English.

use std::collections::HashSet;
use std::sync::OnceLock;

use crate::app_language::AppLanguage;
use crate::language_data;
use crate::localize::t_in;

/// Number of characters `detect` looks at, as in the Python port.
const SAMPLE_LIMIT: usize = 600;

/// Weight of a word that matches only one Latin language's stop words.
const UNIQUE_WEIGHT: i32 = 3;

/// Minimum score before the Latin scorer trusts its guess.
const LATIN_MIN_SCORE: i32 = 3;

/// A language the translator can translate to or from.
///
/// `english_name` is what goes into the model instruction, `local_name` is the
/// curated Ukrainian name and [`Language::display_name`] localises it for the
/// remaining interface languages.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct Language {
    /// ISO-639-1 code (`"de"`), or `"auto"` for the pseudo language.
    pub code: &'static str,
    /// Name used in model instructions and as the English display name.
    pub english_name: &'static str,
    /// Ukrainian display name (`"німецька"`).
    pub local_name: &'static str,
    /// BCP-47 identifier with region (`"de-DE"`); `None` for `auto`.
    pub bcp47: Option<&'static str>,
}

impl Language {
    /// True for the "Auto-detect" pseudo language.
    pub fn is_auto(&self) -> bool {
        self.code == LanguageTable::AUTO.code
    }

    /// Name of this language in the interface language `ui`.
    ///
    /// Ukrainian and English come from the curated fields, the other interface
    /// languages consult the generated name table; unknown pairs fall back to
    /// the English name.
    pub fn display_name(&self, ui: AppLanguage) -> String {
        let resolved = ui.resolved();
        if self.is_auto() {
            return t_in("Auto-detect", resolved).to_owned();
        }
        match resolved {
            AppLanguage::Uk => {
                if self.local_name.is_empty() {
                    self.english_name.to_owned()
                } else {
                    self.local_name.to_owned()
                }
            }
            AppLanguage::En => self.english_name.to_owned(),
            other => language_data::localized_name(self.code, other)
                .unwrap_or(self.english_name)
                .to_owned(),
        }
    }
}

/// Registry of the 38 Hy-MT2 languages plus script based detection.
pub struct LanguageTable;

impl LanguageTable {
    /// The "Auto-detect" pseudo language.
    ///
    /// Its `english_name` is empty on purpose: the model is never asked to
    /// translate into it.
    pub const AUTO: Language = Language {
        code: "auto",
        english_name: "",
        local_name: "Автовизначення",
        bcp47: None,
    };

    /// All languages in Swift order (the order of the app's language picker).
    pub fn all() -> &'static [Language] {
        &language_data::ALL
    }

    /// Look up a language by code, case-insensitively, by BCP-47 identifier or
    /// through the `"auto"` pseudo code.
    ///
    /// Unknown or blank codes return `None`; the lookup never panics.
    pub fn get(code: &str) -> Option<&'static Language> {
        let value = code.trim();
        if value.is_empty() {
            return None;
        }
        if value == LanguageTable::AUTO.code {
            return Some(auto_reference());
        }
        if let Some(language) = language_data::ALL.iter().find(|item| item.code == value) {
            return Some(language);
        }
        if let Some(language) = language_data::ALL
            .iter()
            .find(|item| item.code.eq_ignore_ascii_case(value))
        {
            return Some(language);
        }
        language_data::ALL.iter().find(|item| {
            item.bcp47
                .is_some_and(|bcp47| bcp47.eq_ignore_ascii_case(value))
        })
    }

    /// Guess the language of `text`, mirroring `Language.detect` in Swift.
    ///
    /// Only the first 600 characters are examined. Script ranges
    /// decide Japanese, Korean, Thai, Hebrew, Hindi, Bengali, Tamil, Telugu,
    /// Gujarati and Chinese. Arabic-script text needs language-specific clues;
    /// Cyrillic text is scored between Ukrainian
    /// and Russian (`preferred` breaks ties); Latin text goes through the
    /// stop-word scorer and falls back to English. Armenian and Georgian text
    /// returns `None`, exactly like the Swift original.
    ///
    /// Returns `None` for empty text and for scripts the app cannot translate.
    pub fn detect(text: &str, preferred: AppLanguage) -> Option<&'static Language> {
        let sample = sample_of(text);
        if sample.is_empty() {
            return None;
        }
        if contains_any(sample, &[(0x3040, 0x30FF)]) {
            // Hiragana and katakana.
            return LanguageTable::get("ja");
        }
        if contains_any(sample, &[(0xAC00, 0xD7AF), (0x1100, 0x11FF)]) {
            // Hangul syllables and Jamo.
            return LanguageTable::get("ko");
        }
        if contains_any(sample, &[(0x0E00, 0x0E7F)]) {
            // Thai.
            return LanguageTable::get("th");
        }
        if contains_any(sample, &[(0x0590, 0x05FF)]) {
            // Hebrew.
            return LanguageTable::get("he");
        }
        if contains_any(sample, &[(0x0600, 0x06FF), (0x0750, 0x077F)]) {
            return detect_arabic_script(sample);
        }
        if contains_any(sample, &[(0x0900, 0x097F)]) {
            // Devanagari.
            return LanguageTable::get("hi");
        }
        if contains_any(sample, &[(0x0980, 0x09FF)]) {
            // Bengali.
            return LanguageTable::get("bn");
        }
        if contains_any(sample, &[(0x0B80, 0x0BFF)]) {
            // Tamil.
            return LanguageTable::get("ta");
        }
        if contains_any(sample, &[(0x0C00, 0x0C7F)]) {
            // Telugu.
            return LanguageTable::get("te");
        }
        if contains_any(sample, &[(0x0A80, 0x0AFF)]) {
            // Gujarati.
            return LanguageTable::get("gu");
        }
        if contains_any(sample, &[(0x4E00, 0x9FFF), (0x3400, 0x4DBF)]) {
            // CJK unified ideographs (and extension A).
            return LanguageTable::get("zh");
        }
        if contains_any(sample, &[(0x0400, 0x04FF)]) {
            // Cyrillic.
            return detect_cyrillic(sample, preferred);
        }
        if contains_any(sample, &[(0x0530, 0x058F)]) {
            // Armenian: not supported by Hy-MT2, like Swift's `nil`.
            return None;
        }
        if contains_any(sample, &[(0x10A0, 0x10FF)]) {
            // Georgian: not supported either.
            return None;
        }
        if contains_any(sample, &[(0x0041, 0x024F)]) && sample.chars().any(char::is_alphabetic) {
            if let Some(guess) = guess_latin_language(sample) {
                if let Some(language) = LanguageTable::get(guess) {
                    return Some(language);
                }
            }
            return LanguageTable::get("en");
        }
        None
    }
}

/// Reference to [`LanguageTable::AUTO`] with a `'static` lifetime.
fn auto_reference() -> &'static Language {
    static AUTO_REFERENCE: Language = LanguageTable::AUTO;
    &AUTO_REFERENCE
}

/// First [`SAMPLE_LIMIT`] characters of `text`.
fn sample_of(text: &str) -> &str {
    match text.char_indices().nth(SAMPLE_LIMIT) {
        Some((index, _)) => &text[..index],
        None => text,
    }
}

/// True when any character of `sample` falls inside one of `ranges`.
fn contains_any(sample: &str, ranges: &[(u32, u32)]) -> bool {
    sample.chars().any(|character| {
        let value = character as u32;
        ranges
            .iter()
            .any(|&(low, high)| low <= value && value <= high)
    })
}

/// Arabic script is shared across languages. Leave ambiguous text in Auto.
fn detect_arabic_script(sample: &str) -> Option<&'static Language> {
    if sample.contains(|character| "ٹڈڑںھہے".contains(character)) {
        return LanguageTable::get("ur");
    }
    let tokens = words(sample);
    let persian = tokens.iter().any(|word| {
        matches!(
            word.as_str(),
            "است" | "هست" | "بود" | "برای" | "این" | "بفرستید"
        )
    });
    let arabic = tokens.iter().any(|word| {
        matches!(
            word.as_str(),
            "هذا" | "هذه" | "ذلك" | "الذي" | "التي" | "إلى"
        )
    });
    match (persian, arabic) {
        (true, false) => LanguageTable::get("fa"),
        (false, true) => LanguageTable::get("ar"),
        _ => None,
    }
}

/// Stop-word sets of the detector, built once on first use.
struct WordIndex {
    /// Words that add to the Ukrainian score.
    ukrainian: HashSet<&'static str>,
    /// Words that add to the Russian score.
    russian: HashSet<&'static str>,
    /// Folded stop words, indexed like [`language_data::LATIN_ORDER`].
    latin: Vec<HashSet<&'static str>>,
}

/// Lazily built [`WordIndex`] shared by all detection calls.
static WORD_INDEX: OnceLock<WordIndex> = OnceLock::new();

/// Return the shared [`WordIndex`], building it on first use.
fn word_index() -> &'static WordIndex {
    WORD_INDEX.get_or_init(|| WordIndex {
        ukrainian: language_data::UKRAINIAN_WORDS.iter().copied().collect(),
        russian: language_data::RUSSIAN_WORDS.iter().copied().collect(),
        latin: language_data::LATIN_STOP_WORDS
            .iter()
            .map(|words| words.iter().copied().collect())
            .collect(),
    })
}

/// Ukrainian/Russian scoring copied from the Swift source.
fn detect_cyrillic(sample: &str, preferred: AppLanguage) -> Option<&'static Language> {
    let index = word_index();
    let mut ukrainian = 0;
    let mut russian = 0;
    for character in sample.chars().flat_map(char::to_lowercase) {
        match character {
            'і' | 'ї' | 'є' | 'ґ' => ukrainian += 2,
            'ы' | 'э' | 'ё' | 'ъ' => russian += 2,
            '’' => ukrainian += 1,
            _ => {}
        }
    }
    for word in words(sample) {
        if index.ukrainian.contains(word.as_str()) {
            ukrainian += 1;
        }
        if index.russian.contains(word.as_str()) {
            russian += 1;
        }
    }
    if ukrainian > russian {
        return LanguageTable::get("uk");
    }
    if russian > ukrainian {
        return LanguageTable::get("ru");
    }
    if preferred.resolved() == AppLanguage::Ru {
        LanguageTable::get("ru")
    } else {
        LanguageTable::get("uk")
    }
}

/// Split `text` into lower-cased runs of Unicode letters.
///
/// This is `re.findall(r"[^\W\d_]+", text.lower())` from the Python port:
/// digits, punctuation, whitespace and combining marks all separate words.
fn words(text: &str) -> Vec<String> {
    let mut words: Vec<String> = Vec::new();
    let mut current = String::new();
    for character in text.chars() {
        if character.is_alphabetic() {
            current.extend(character.to_lowercase());
        } else if !current.is_empty() {
            words.push(std::mem::take(&mut current));
        }
    }
    if !current.is_empty() {
        words.push(current);
    }
    words
}

/// Stop-word based replacement for `NLLanguageRecognizer`.
fn guess_latin_language(text: &str) -> Option<&'static str> {
    let index = word_index();
    let mut scores = vec![0_i32; index.latin.len()];
    let mut scored = false;
    for word in words(text) {
        let folded = fold_word(&word);
        let hits: Vec<usize> = index
            .latin
            .iter()
            .enumerate()
            .filter(|(_, words)| words.contains(folded.as_str()))
            .map(|(position, _)| position)
            .collect();
        if hits.is_empty() {
            continue;
        }
        // A word unique to one language is stronger evidence than a shared one.
        let weight = if hits.len() == 1 { UNIQUE_WEIGHT } else { 1 };
        for position in hits {
            if let Some(score) = scores.get_mut(position) {
                *score += weight;
            }
        }
        scored = true;
    }
    if !scored {
        return None;
    }
    let mut best: Option<&'static str> = None;
    let mut best_score = 0;
    for (position, code) in language_data::LATIN_ORDER.iter().enumerate() {
        let score = scores.get(position).copied().unwrap_or(0);
        // Strict comparison keeps the first language of the order on a tie.
        if score > best_score {
            best_score = score;
            best = Some(*code);
        }
    }
    if best_score < LATIN_MIN_SCORE {
        return None;
    }
    best
}

/// Lower-case and strip diacritics so `cómo` matches the stop word `como`.
fn fold_word(word: &str) -> String {
    let mut folded = String::with_capacity(word.len());
    for character in word.chars().flat_map(char::to_lowercase) {
        folded.push(fold_character(character));
    }
    folded
}

/// Base character of a precomposed Latin letter, or the character itself.
fn fold_character(character: char) -> char {
    match language_data::FOLD_PAIRS.binary_search_by(|(source, _)| source.cmp(&character)) {
        Ok(position) => language_data::FOLD_PAIRS[position].1,
        Err(_) => character,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Order of the language table in `Sources/HyMT/Models/Language.swift`.
    const EXPECTED_CODES: [&str; 38] = [
        "zh", "en", "fr", "pt", "es", "ja", "tr", "ru", "ar", "ko", "th", "it", "de", "vi", "ms",
        "id", "tl", "hi", "zh-Hant", "pl", "cs", "nl", "km", "my", "fa", "gu", "ur", "te", "mr",
        "he", "bn", "ta", "uk", "bo", "kk", "mn", "ug", "yue",
    ];

    #[test]
    fn thirty_eight_languages_in_swift_order() {
        let all = LanguageTable::all();
        assert_eq!(all.len(), 38);
        let codes: Vec<&str> = all.iter().map(|language| language.code).collect();
        assert_eq!(codes, EXPECTED_CODES);
    }

    #[test]
    fn every_language_has_names_and_a_bcp47_identifier() {
        for language in LanguageTable::all() {
            assert!(!language.code.is_empty(), "{language:?}");
            assert!(!language.english_name.is_empty(), "{language:?}");
            assert!(!language.local_name.is_empty(), "{language:?}");
            assert!(language.bcp47.is_some(), "{language:?}");
            assert!(!language.is_auto(), "{language:?}");
        }
    }

    #[test]
    fn auto_language_is_a_pseudo_language() {
        assert_eq!(LanguageTable::AUTO.code, "auto");
        assert!(LanguageTable::AUTO.is_auto());
        assert!(LanguageTable::AUTO.bcp47.is_none());
        assert!(LanguageTable::AUTO.english_name.is_empty());
        assert_eq!(LanguageTable::get("auto"), Some(&LanguageTable::AUTO));
        assert!(!LanguageTable::all()[0].is_auto());
    }

    #[test]
    fn lookup_accepts_codes_case_and_bcp47() {
        assert_eq!(
            LanguageTable::get("de"),
            Some(&Language {
                code: "de",
                english_name: "German",
                local_name: "німецька",
                bcp47: Some("de-DE"),
            })
        );
        assert_eq!(
            LanguageTable::get("zh-hant").map(|l| l.code),
            Some("zh-Hant")
        );
        assert_eq!(LanguageTable::get("ZH-TW").map(|l| l.code), Some("zh-Hant"));
        assert_eq!(LanguageTable::get("en-US").map(|l| l.code), Some("en"));
        assert_eq!(LanguageTable::get("fil-PH").map(|l| l.code), Some("tl"));
        assert_eq!(LanguageTable::get("DE").map(|l| l.code), Some("de"));
        assert_eq!(LanguageTable::get("nope"), None);
        assert_eq!(LanguageTable::get(""), None);
        assert_eq!(LanguageTable::get("   "), None);
    }

    #[test]
    fn detects_scripts() {
        let cases: [(&str, &str); 11] = [
            ("こんにちは世界、今日はいい天気ですね。", "ja"),
            ("안녕하세요. 오늘 날씨가 좋네요.", "ko"),
            ("สวัสดีครับ วันนี้อากาศดี", "th"),
            ("مرحبا بالعالم، هذا اختبار.", "ar"),
            ("नमस्ते दुनिया, यह एक परीक्षण है।", "hi"),
            ("你好世界，这是一个测试。", "zh"),
            ("שלום עולם", "he"),
            ("வணக்கம் உலகம்", "ta"),
            ("Це український текст про переклад", "uk"),
            ("Это русский текст про перевод", "ru"),
            ("Hello, this is a test", "en"),
        ];
        for (text, expected) in cases {
            let detected = LanguageTable::detect(text, AppLanguage::System)
                .unwrap_or_else(|| panic!("no language detected for {text:?}"));
            assert_eq!(detected.code, expected, "{text:?}");
        }
    }

    #[test]
    fn swift_language_cases() {
        // Ported verbatim from the Swift `LanguageTests`.
        assert_eq!(
            LanguageTable::detect("Це український текст про переклад", AppLanguage::Uk)
                .map(|l| l.code),
            Some("uk")
        );
        assert_eq!(
            LanguageTable::detect("Это русский текст про перевод", AppLanguage::Ru).map(|l| l.code),
            Some("ru")
        );
        assert_eq!(
            LanguageTable::detect("Hello, this is a test", AppLanguage::En).map(|l| l.code),
            Some("en")
        );
        assert_eq!(
            LanguageTable::detect("ключ", AppLanguage::Uk).map(|l| l.code),
            Some("uk")
        );
        assert_eq!(
            LanguageTable::detect("ключ", AppLanguage::Ru).map(|l| l.code),
            Some("ru")
        );
    }

    #[test]
    fn ambiguous_cyrillic_uses_the_preferred_language() {
        assert_eq!(
            LanguageTable::detect("ключ", AppLanguage::Ru).map(|l| l.code),
            Some("ru")
        );
        assert_eq!(
            LanguageTable::detect("ключ", AppLanguage::Uk).map(|l| l.code),
            Some("uk")
        );
    }

    #[test]
    fn distinctive_letters_outweigh_the_word_lists() {
        assert_eq!(
            LanguageTable::detect("їжа та ґанок", AppLanguage::Ru).map(|l| l.code),
            Some("uk")
        );
        assert_eq!(
            LanguageTable::detect("объём и этаж", AppLanguage::Uk).map(|l| l.code),
            Some("ru")
        );
    }

    #[test]
    fn detects_latin_languages() {
        let cases: [(&str, &str); 11] = [
            (
                "Bonjour, je voudrais savoir à quelle heure commence la réunion.",
                "fr",
            ),
            (
                "Este documento explica cómo funciona el servicio de traducción.",
                "es",
            ),
            (
                "Este documento explica como funciona o serviço de tradução.",
                "pt",
            ),
            ("Das ist ein guter Test für die Übersetzung.", "de"),
            ("Dit is een goede test voor de vertaling.", "nl"),
            ("La casa è bella e il giardino è grande.", "it"),
            ("To jest dobry test tłumaczenia.", "pl"),
            ("Bu bir çeviri testidir ve çok iyidir.", "tr"),
            ("Đây là một bài kiểm tra bản dịch.", "vi"),
            ("Ini adalah sebuah tes terjemahan yang baik.", "id"),
            ("Ini ialah satu ujian terjemahan yang baik.", "ms"),
        ];
        for (text, expected) in cases {
            let detected = LanguageTable::detect(text, AppLanguage::En)
                .unwrap_or_else(|| panic!("no language detected for {text:?}"));
            assert_eq!(detected.code, expected, "{text:?}");
        }
    }

    #[test]
    fn latin_text_without_known_words_falls_back_to_english() {
        assert_eq!(
            LanguageTable::detect("Xyzzy plugh foobar", AppLanguage::System).map(|l| l.code),
            Some("en")
        );
    }

    #[test]
    fn unsupported_or_empty_text_returns_none() {
        assert_eq!(LanguageTable::detect("", AppLanguage::System), None);
        assert_eq!(
            LanguageTable::detect("12345 67890 !!!", AppLanguage::System),
            None
        );
        assert_eq!(LanguageTable::detect("ქართული", AppLanguage::System), None);
        assert_eq!(LanguageTable::detect("Հայերեն", AppLanguage::System), None);
    }

    #[test]
    fn detection_only_samples_the_first_600_characters() {
        let mut text = "a".repeat(SAMPLE_LIMIT);
        text.push_str(" こんにちは");
        assert_eq!(
            LanguageTable::detect(&text, AppLanguage::System).map(|l| l.code),
            Some("en")
        );
        let mut shifted = String::from("こんにちは ");
        shifted.push_str(&"a".repeat(SAMPLE_LIMIT));
        assert_eq!(
            LanguageTable::detect(&shifted, AppLanguage::System).map(|l| l.code),
            Some("ja")
        );
    }

    #[test]
    fn display_names_use_english_and_ukrainian_names() {
        let german = LanguageTable::get("de").expect("de");
        assert_eq!(german.display_name(AppLanguage::En), "German");
        assert_eq!(german.display_name(AppLanguage::Uk), "німецька");
    }

    #[test]
    fn display_names_are_localised() {
        assert_eq!(
            LanguageTable::get("de").map(|l| l.display_name(AppLanguage::De)),
            Some("Deutsch".to_owned())
        );
        assert_eq!(
            LanguageTable::get("uk").map(|l| l.display_name(AppLanguage::Ru)),
            Some("украинский".to_owned())
        );
        assert_eq!(
            LanguageTable::get("zh-Hant").map(|l| l.display_name(AppLanguage::Fr)),
            Some("chinois traditionnel".to_owned())
        );
        assert_eq!(
            LanguageTable::get("yue").map(|l| l.display_name(AppLanguage::It)),
            Some("cantonese".to_owned())
        );
    }

    #[test]
    fn display_names_fall_back_to_english_when_not_curated() {
        let klingon = Language {
            code: "xx",
            english_name: "Klingon",
            local_name: "клінгонська",
            bcp47: None,
        };
        assert_eq!(klingon.display_name(AppLanguage::De), "Klingon");
        let empty_local = Language {
            code: "en",
            english_name: "English",
            local_name: "",
            bcp47: Some("en-US"),
        };
        assert_eq!(empty_local.display_name(AppLanguage::Uk), "English");
    }

    #[test]
    fn auto_display_name_is_translated() {
        assert_eq!(
            LanguageTable::AUTO.display_name(AppLanguage::En),
            "Auto-detect"
        );
        assert_eq!(
            LanguageTable::AUTO.display_name(AppLanguage::Uk),
            "Автовизначення"
        );
    }

    #[test]
    fn word_splitting_drops_digits_and_punctuation() {
        assert_eq!(
            words("Hello, world! 42 naïve_thing"),
            vec![
                "hello".to_owned(),
                "world".to_owned(),
                "naïve".to_owned(),
                "thing".to_owned(),
            ]
        );
    }

    #[test]
    fn folding_strips_latin_diacritics() {
        assert_eq!(fold_word("cómo"), "como");
        assert_eq!(fold_word("für"), "fur");
        assert_eq!(fold_word("Übersetzung"), "ubersetzung");
        assert_eq!(fold_word("được"), "đuoc");
        assert_eq!(fold_word("plain"), "plain");
    }

    #[test]
    fn word_lists_are_sorted_for_the_fold_table() {
        assert!(language_data::FOLD_PAIRS
            .windows(2)
            .all(|pair| pair[0].0 < pair[1].0));
        assert_eq!(
            language_data::LATIN_ORDER.len(),
            language_data::LATIN_STOP_WORDS.len()
        );
        assert_eq!(language_data::LATIN_ORDER.len(), 12);
    }
}
