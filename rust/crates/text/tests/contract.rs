//! Contract-level checks: the public API is usable exactly as `CONTRACTS.md`
//! describes, including `ofm_i18n::Language` arguments and typed errors.

use ofm_i18n::{Language, LanguageTable};
use ofm_text::{
    DegenerateReason, OutputSanitizer, PromptBuilder, TextChunk, TextChunker, TokenRestorer,
    TranslationStyle, TranslationTone,
};

fn language(code: &str) -> &'static Language {
    LanguageTable::get(code).expect("language must exist")
}

#[test]
fn sanitizer_accepts_a_language_reference() {
    let ukrainian: &Language = language("uk");
    assert!(OutputSanitizer::script_ok("Привіт", ukrainian));
    assert!(OutputSanitizer::uses_allowed_cyrillic("Привіт", ukrainian));
    assert_eq!(
        OutputSanitizer::is_degenerate("Hello", "Привіт", ukrainian),
        None
    );
    assert_eq!(
        OutputSanitizer::is_degenerate("Hello", "Hello", ukrainian),
        Some(DegenerateReason::Script)
    );
}

#[test]
fn compose_returns_a_typed_error() {
    let chunks = TextChunker::split("One\nTwo");
    let translated = vec!["One".to_string(), "Two".to_string()];
    assert_eq!(
        TextChunker::compose(&chunks, &translated),
        Ok("One\nTwo".to_string())
    );
    let error = TextChunker::compose(&chunks, &translated[..1]);
    assert!(error.is_err());
    let message = error.map_err(|e| e.to_string()).unwrap_err();
    assert!(message.contains('2'), "unexpected message: {message}");
}

#[test]
fn chunk_fields_are_public_and_buildable() {
    let chunk = TextChunk {
        prefix: "## ".to_string(),
        text: "Title".to_string(),
        is_heading: true,
        is_code: false,
        separator_before: "\n".to_string(),
        index: 0,
    };
    assert_eq!(
        TextChunker::compose(&[chunk], &["Заголовок".to_string()]),
        Ok("## Заголовок".to_string())
    );
}

#[test]
fn prompts_and_tokens_are_reachable() {
    let instruction = PromptBuilder::instruction(
        TranslationStyle::Auto,
        TranslationTone::Standard,
        "Ukrainian",
        false,
    );
    assert!(instruction.ends_with(':'));
    assert_eq!(
        TokenRestorer::restore("See example.com", "Дивіться example.com"),
        Some("Дивіться example.com".to_string())
    );
    assert_eq!(
        TokenRestorer::preserve_trailing_punctuation("Hi?", "Привіт"),
        "Привіт?"
    );
}
