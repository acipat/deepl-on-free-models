//! Restores protected tokens (URLs, e-mail addresses, model ids, inline code).
//!
//! Port of `windows/deepl_ofm/core/tokens.py`, which follows
//! `Sources/HyMT/Support/TokenRestorer.swift`. The model tends to change dots,
//! slashes or capitalisation inside technical tokens while the surrounding
//! prose is translated normally; this module puts the source spelling back and,
//! when the token count changed, either accepts the translation (every source
//! token survived somewhere) or returns `None` so the caller can retry.
//!
//! The original pattern uses lookbehind and lookahead assertions, which the
//! `regex` crate cannot express, so this module uses [`fancy_regex`]. The
//! sanitizer keeps plain `regex` for its simpler patterns.
//!
//! # Performance
//!
//! The token pattern is backtracking-based, exactly like Python's `re`. Both
//! implementations scale quadratically on adversarial *whitespace-free* runs
//! (hundreds of kilobytes of `a`, `a1`, `a.`, …); real input is processed per
//! chunk, so [`crate::TextChunker::LINE_LIMIT`] bounds the cost. No input can
//! panic: the scanner stops at a regex runtime error and works on character
//! offsets, so multi-byte languages are safe.

use std::sync::OnceLock;

use fancy_regex::Regex;

/// The token pattern, lifted verbatim from the Python implementation.
///
/// Alternation order matters: e-mail addresses and URLs are tried before the
/// bare-domain and `owner/model` alternatives so the longest technical token
/// wins. The trailing lookahead allows a sentence period: `Hy-MT2.` at the end
/// of a sentence is the same protected token as `Hy-MT2 ` in the middle; the
/// dot is not part of the token and stays in the translation.
const TOKEN_PATTERN: &str = concat!(
    r"(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
    r#"|(?:https?://[^\s)\]>"']+)"#,
    r"|(?:(?:[A-Za-z0-9][A-Za-z0-9-]*\.)+",
    r"(?:com|ai|org|io|dev|net|app|co|ua|me|info|biz|xyz|tech|cloud|pro)",
    r"\b(?:/[^\s)\]]*)?)",
    r"|(?:`[^`\n]+`)",
    r"|(?<![A-Za-z0-9._-])[A-Za-z0-9][A-Za-z0-9._-]*/",
    r"[A-Za-z0-9][A-Za-z0-9._:-]*(?![A-Za-z0-9_-])",
    r"|(?<![A-Za-z0-9._-])(?=[A-Za-z0-9.-]*\d)",
    r"[A-Za-z][A-Za-z0-9]*(?:[.-][A-Za-z0-9]+)+(?![A-Za-z0-9_-])",
);

/// Characters stripped from the end of a protected token.
const TRAILING_PUNCTUATION: [char; 7] = ['.', ',', ';', ':', '!', '?', '\u{2026}'];

/// Characters considered sentence punctuation by
/// [`TokenRestorer::preserve_trailing_punctuation`].
const TRAILING_PUNCTUATION_LOOSE: [char; 7] = [':', ';', ',', '.', '!', '?', '\u{2026}'];

static TOKEN_REGEX: OnceLock<Option<Regex>> = OnceLock::new();

/// The compiled token pattern; `None` only if the pattern itself is invalid.
fn token_regex() -> Option<&'static Regex> {
    TOKEN_REGEX
        .get_or_init(|| Regex::new(TOKEN_PATTERN).ok())
        .as_ref()
}

/// One protected token and its span in the original (non-normalised) text.
///
/// Spans are character offsets, mirroring Python string indexing: hyphen
/// normalisation maps one character to one character, so offsets stay valid.
#[derive(Clone, Debug, PartialEq, Eq)]
struct ProtectedToken {
    start: usize,
    end: usize,
    token: String,
}

/// Map the Unicode dash variants models like to emit back to ASCII `-`.
///
/// U+2010 hyphen, U+2011 non-breaking hyphen, U+2012 figure dash, U+2013 en
/// dash, U+2014 em dash and U+2212 minus sign.
fn normalize_hyphens(text: &str) -> String {
    text.chars()
        .map(|character| match character {
            '\u{2010}'..='\u{2014}' | '\u{2212}' => '-',
            other => other,
        })
        .collect()
}

/// Byte offset of every character boundary in `text`.
fn char_offsets(text: &str) -> Vec<usize> {
    text.char_indices().map(|(offset, _)| offset).collect()
}

/// Convert a regex byte offset into a character offset.
fn byte_to_char(offsets: &[usize], byte: usize) -> usize {
    match offsets.binary_search(&byte) {
        Ok(index) | Err(index) => index,
    }
}

/// Find protected tokens in `text`, mirroring Swift `matches(in:)`.
fn matches(text: &str) -> Vec<ProtectedToken> {
    let Some(regex) = token_regex() else {
        return Vec::new();
    };
    let normalized = normalize_hyphens(text);
    let offsets = char_offsets(&normalized);
    let mut result: Vec<ProtectedToken> = Vec::new();
    for found in regex.find_iter(&normalized) {
        // A runtime error (backtrack limit) stops the scan; treating the
        // already found tokens as final is safer than panicking.
        let Ok(found) = found else { break };
        let start = byte_to_char(&offsets, found.start());
        let mut end = byte_to_char(&offsets, found.end());
        let mut token = found.as_str().to_string();

        // A URL at the end of a sentence must not swallow the full stop.
        while let Some(last) = token.chars().last() {
            if !TRAILING_PUNCTUATION.contains(&last) {
                break;
            }
            token.truncate(token.len() - last.len_utf8());
            end -= 1;
        }
        if token.is_empty() {
            continue;
        }

        // Drop plain words (e.g. a bare `foo/bar` without digits) that only
        // matched through the path alternative.
        let interesting = token.starts_with('`')
            || token.contains('@')
            || token.contains('.')
            || token
                .chars()
                .any(|character| character.is_numeric() || character == ':' || character == '-');
        if !interesting {
            continue;
        }
        result.push(ProtectedToken { start, end, token });
    }
    result
}

/// Byte-for-byte restoration of technical tokens after translation.
pub struct TokenRestorer;

impl TokenRestorer {
    /// Restore source token spellings in `translated`.
    ///
    /// Returns `None` when the number of protected tokens changed and not every
    /// source token survived somewhere in the translation: keeping a corrupted
    /// URL or model id is worse than asking for a retry.
    pub fn restore(source: &str, translated: &str) -> Option<String> {
        let source_tokens = matches(source);
        if source_tokens.is_empty() {
            return Some(translated.to_string());
        }

        let translated_tokens = matches(translated);
        if source_tokens.len() == translated_tokens.len() {
            let source_chars: Vec<char> = source.chars().collect();
            let mut result: Vec<char> = translated.chars().collect();
            for (source_match, translated_match) in
                source_tokens.iter().zip(translated_tokens.iter()).rev()
            {
                if source_match.end > source_match.start
                    && translated_match.end <= result.len()
                    && translated_match.start <= translated_match.end
                {
                    let replacement: Vec<char> =
                        source_chars[source_match.start..source_match.end].to_vec();
                    result.splice(translated_match.start..translated_match.end, replacement);
                }
            }
            return Some(result.into_iter().collect());
        }

        // Counts differ when the model repeats an id or writes it twice with
        // different casing. Accept the line only when every token survived.
        let normalized = normalize_hyphens(translated).to_lowercase();
        let kept_every_token = source_tokens
            .iter()
            .all(|found| normalized.contains(&normalize_hyphens(&found.token).to_lowercase()));
        if kept_every_token {
            Some(translated.to_string())
        } else {
            None
        }
    }

    /// Keep the source line's final punctuation on the translation.
    pub fn preserve_trailing_punctuation(source: &str, translated: &str) -> String {
        let source_trimmed = source.trim();
        let Some(last_source) = source_trimmed.chars().last() else {
            return translated.to_string();
        };
        if !TRAILING_PUNCTUATION_LOOSE.contains(&last_source) {
            return translated.to_string();
        }
        let trimmed = translated.trim();
        match trimmed.chars().last() {
            Some(last) if TRAILING_PUNCTUATION_LOOSE.contains(&last) => {
                let cut = trimmed.len() - last.len_utf8();
                format!("{}{}", &trimmed[..cut], last_source)
            }
            _ => format!("{trimmed}{last_source}"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const UNICODE_HYPHENS: [char; 6] = [
        '\u{2010}', '\u{2011}', '\u{2012}', '\u{2013}', '\u{2014}', '\u{2212}',
    ];

    #[test]
    fn restores_url() {
        let source = "Groq (ключ: console.groq.com/keys):";
        let translated = "Groq (key: console.grole.com/keys)";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("Groq (key: console.groq.com/keys)".to_string())
        );
    }

    #[test]
    fn restores_model_ids() {
        let source = "tencent/hy-mt2-7b, qwen/qwen3.7-flash — model";
        let translated = "Tencent/HY-MT2-7B, QWEN/QWEN3.7-FLASH — model";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("tencent/hy-mt2-7b, qwen/qwen3.7-flash — model".to_string())
        );
    }

    #[test]
    fn mismatch_returns_none() {
        let source = "See console.groq.com/keys";
        let translated = "No link here";
        assert_eq!(TokenRestorer::restore(source, translated), None);
    }

    #[test]
    fn punctuation_is_kept() {
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation("Cloud providers:", "Cloud providers"),
            "Cloud providers:"
        );
    }

    #[test]
    fn wrong_punctuation_is_replaced() {
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation("Cloud providers:", "Cloud providers."),
            "Cloud providers:"
        );
    }

    #[test]
    fn multi_label_domain_is_restored() {
        let source = "Сайт example.com.ua працює";
        let translated = "The site example.com works";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("The site example.com.ua works".to_string())
        );
    }

    #[test]
    fn email_is_restored() {
        let source = "Напишіть на admin@example.com";
        let translated = "Write to admin@example.org";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("Write to admin@example.com".to_string())
        );
    }

    #[test]
    fn sentence_period_is_not_part_of_url() {
        let source = "Відкрийте https://example.com.";
        let translated = "Open https://example.com";
        let restored = TokenRestorer::restore(source, translated);
        assert_eq!(restored, Some("Open https://example.com".to_string()));
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation(source, &restored.unwrap_or_default()),
            "Open https://example.com."
        );
    }

    #[test]
    fn markdown_link_target_is_restored() {
        let source = "[key](https://example.com/keys)";
        let translated = "[key](https://example.com/keys)";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some(translated.to_string())
        );
    }

    #[test]
    fn inline_code_is_protected() {
        let source = "Use `console.groq.com/keys` here";
        let translated = "Use `console.groq.com/keys` here";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some(translated.to_string())
        );
    }

    #[test]
    fn hyphenated_model_id_is_protected() {
        let source = "gpt-oss-120b — ~3000 tokens per second";
        let translated = "GPT-OSS-120B — ~3000 tokens per second";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("gpt-oss-120b — ~3000 tokens per second".to_string())
        );
    }

    #[test]
    fn unicode_hyphen_in_model_id_is_restored() {
        let source = "Hy-MT2 7B model";
        let translated = "Hy\u{2011}MT2 7B model";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("Hy-MT2 7B model".to_string())
        );
    }

    #[test]
    fn source_unicode_hyphen_survives() {
        let source = "Hy\u{2011}MT2 7B model";
        let translated = "Hy-MT2 7B model";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("Hy\u{2011}MT2 7B model".to_string())
        );
    }

    #[test]
    fn model_id_at_end_of_sentence_is_restored() {
        let source = "Styles Auto / Literal / Natural and tones Default / Formal / Casual, \
                      matching the Hy-MT2 model card.";
        let translated = "Стилі Авто / Дослівний / Натуральний та тони За замовчуванням / \
                          Формальний / Неформальний, відповідно до картки моделі Hy-MT2.";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some(translated.to_string())
        );
    }

    #[test]
    fn hyphenated_id_before_period_is_restored_exactly() {
        let source = "The engine is Hy-MT2.";
        let translated = "Рушій — hy\u{2011}mt2.";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("Рушій — Hy-MT2.".to_string())
        );
    }

    #[test]
    fn model_id_before_comma_is_restored() {
        let source = "Hy-MT2, our translator";
        let translated = "hy-mt2, наш перекладач";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("Hy-MT2, наш перекладач".to_string())
        );
    }

    #[test]
    fn repeated_token_keeps_translation() {
        let source = "Model Hy-MT2 here";
        let translated = "Модель Hy-MT2 (Hy-MT2) тут";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some(translated.to_string())
        );
    }

    #[test]
    fn dropped_token_still_falls_back() {
        let source = "Download from example.com/keys now";
        let translated = "Завантажте звідси зараз";
        assert_eq!(TokenRestorer::restore(source, translated), None);
    }

    #[test]
    fn empty_source_returns_translation() {
        assert_eq!(TokenRestorer::restore("", ""), Some(String::new()));
        assert_eq!(
            TokenRestorer::restore("", "Привіт"),
            Some("Привіт".to_string())
        );
    }

    #[test]
    fn whitespace_only_source_returns_translation() {
        assert_eq!(
            TokenRestorer::restore("   \n\t", "  hello  "),
            Some("  hello  ".to_string())
        );
    }

    #[test]
    fn text_without_tokens_is_untouched() {
        let source = "Просто речення без посилань";
        let translated = "Just a sentence without links";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some(translated.to_string())
        );
    }

    #[test]
    fn url_at_end_of_sentence_keeps_the_period() {
        let source = "Документація: https://example.com/docs.";
        let translated = "Documentation: https://example.com/docs";
        let restored = TokenRestorer::restore(source, translated);
        assert_eq!(
            restored,
            Some("Documentation: https://example.com/docs".to_string())
        );
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation(source, &restored.unwrap_or_default()),
            "Documentation: https://example.com/docs."
        );
    }

    #[test]
    fn trailing_punctuation_edge_cases() {
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation("", "Hello"),
            "Hello"
        );
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation("   ", "Hello"),
            "Hello"
        );
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation("Hi", "Hello"),
            "Hello"
        );
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation("Hi?", "Hello!"),
            "Hello?"
        );
        assert_eq!(
            TokenRestorer::preserve_trailing_punctuation("Hi?", "Hello"),
            "Hello?"
        );
    }

    #[test]
    fn every_unicode_hyphen_variant_is_normalised() {
        for hyphen in UNICODE_HYPHENS {
            let source = "Hy-MT2 model";
            let translated = format!("Hy{hyphen}MT2 model");
            assert_eq!(
                TokenRestorer::restore(source, &translated),
                Some("Hy-MT2 model".to_string()),
                "hyphen {hyphen:?}"
            );
        }
    }

    #[test]
    fn source_hyphen_variant_is_restored() {
        for hyphen in UNICODE_HYPHENS {
            let source = format!("Hy{hyphen}MT2 model");
            let translated = "Hy-MT2 model";
            assert_eq!(
                TokenRestorer::restore(&source, translated),
                Some(format!("Hy{hyphen}MT2 model")),
                "hyphen {hyphen:?}"
            );
        }
    }

    #[test]
    fn equal_token_counts_are_replaced_by_position() {
        let source = "alpha.com and beta.io";
        let translated = "gamma.com und delta.io";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some("alpha.com und beta.io".to_string())
        );
    }

    #[test]
    fn token_count_lost_with_empty_translation_returns_none() {
        assert_eq!(TokenRestorer::restore("Visit example.com", ""), None);
    }

    #[test]
    fn inline_code_with_period_inside_is_untouched() {
        let source = "Call `config.yaml.` first";
        let translated = "Call `config.yaml.` first";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some(translated.to_string())
        );
    }

    #[test]
    fn inline_code_model_id_with_colon_is_protected() {
        let source = "Use `qwen3:8b` locally";
        let translated = "Використовуйте `qwen3:8b` локально";
        assert_eq!(
            TokenRestorer::restore(source, translated),
            Some(translated.to_string())
        );
    }

    #[test]
    fn url_inside_parentheses_does_not_take_the_bracket() {
        let source = "See (https://example.com/docs) for details";
        let token = matches(source);
        assert_eq!(token.len(), 1);
        assert_eq!(token[0].token, "https://example.com/docs");
        assert_eq!(
            TokenRestorer::restore(source, "Дивіться (https://example.com/docs) тут"),
            Some("Дивіться (https://example.com/docs) тут".to_string())
        );
    }

    #[test]
    fn bare_words_are_not_tokens() {
        assert!(matches("and/or maybe").is_empty());
        assert!(matches("plain prose without technical terms").is_empty());
        assert_eq!(
            TokenRestorer::restore("and/or maybe", "і/або можливо"),
            Some("і/або можливо".to_string())
        );
    }

    #[test]
    fn token_pattern_compiles() {
        assert!(token_regex().is_some(), "token pattern must compile");
    }

    #[test]
    fn pathological_inputs_do_not_panic() {
        let long = "x".repeat(4096);
        let adversarial = "a".repeat(3200);
        let cases = [
            "",
            " ",
            ".",
            "...",
            "``",
            "`",
            "http://",
            "https://.",
            "a@b",
            "@",
            "/",
            "a/",
            "/b",
            "a/b",
            "a.b",
            "a.b.c",
            "\u{2010}",
            "\u{2212}\u{2010}",
            "<｜hy_end｜>",
            "a-1.2.3-",
            long.as_str(),
            adversarial.as_str(),
        ];
        for case in cases {
            let restored = TokenRestorer::restore(case, case);
            assert!(
                restored.is_some(),
                "self translation must round-trip: {case:?}"
            );
            let _ = TokenRestorer::preserve_trailing_punctuation(case, case);
            let _ = matches(case);
        }
    }

    #[test]
    fn very_long_text_does_not_panic() {
        let prose = "The quick brown fox jumps over the lazy dog. ".repeat(2000);
        let text = format!("{prose}Visit console.groq.com/keys for details. {prose}");
        let restored = TokenRestorer::restore(&text, &text);
        assert_eq!(restored, Some(text.clone()));
        assert!(TokenRestorer::restore(&text, "").is_none());
        let _ = TokenRestorer::preserve_trailing_punctuation(&text, &text);
    }

    #[test]
    fn random_inputs_never_panic() {
        // Deterministic LCG so the fuzz-ish test is reproducible.
        let alphabet: Vec<char> =
            "abcXYZ0129.-_/@:`~ \n\t\u{2010}\u{2011}\u{2012}\u{2013}\u{2014}\u{2212}｜<>"
                .chars()
                .collect();
        let mut state: u64 = 0x5DEE_CE66_D1CE_1234;
        let mut next = || {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            (state >> 33) as usize
        };
        for _ in 0..200 {
            let length = next() % 120;
            let candidate: String = (0..length)
                .map(|_| alphabet[next() % alphabet.len()])
                .collect();
            let other_length = next() % 120;
            let other: String = (0..other_length)
                .map(|_| alphabet[next() % alphabet.len()])
                .collect();
            if let Some(restored) = TokenRestorer::restore(&candidate, &other) {
                // The result must stay valid UTF-8; reaching this line proves it.
                assert!(
                    restored.chars().count() <= candidate.chars().count() + other.chars().count()
                );
            }
            let _ = TokenRestorer::preserve_trailing_punctuation(&candidate, &other);
        }
    }
}
