//! Pipeline-level behaviour: chunking, token restoration, validation and the
//! sentence-by-sentence retry the translator performs for a rejected block.

use ofm_i18n::LanguageTable;
use ofm_text::{DegenerateReason, OutputSanitizer, TextChunker, TokenRestorer};

/// A long, varied paragraph that exceeds [`TextChunker::LINE_LIMIT`].
fn long_paragraph() -> String {
    let mut text = String::new();
    for index in 1..=120 {
        text.push_str(&format!(
            "Sentence number {index} of the source text explains one detail. "
        ));
    }
    text.trim_end().to_string()
}

#[test]
fn long_paragraph_failing_repetition_is_retried_sentence_by_sentence() {
    let source = long_paragraph();
    let english = LanguageTable::get("en").expect("en");
    assert!(
        source.chars().count() > TextChunker::LINE_LIMIT,
        "the fixture must exceed the chunk limit"
    );

    // The first attempt returns a long, repetitive block and is rejected.
    let repeats = (source.chars().count() / 40).max(20);
    let broken = "Abcdefghij. ".repeat(repeats);
    assert_eq!(
        OutputSanitizer::is_degenerate(&source, &broken, english),
        Some(DegenerateReason::Repetition)
    );

    // Retry: the chunker splits the paragraph into limit-sized pieces, each of
    // which is retried sentence by sentence. Every single sentence passes the
    // validator and the composed result keeps the original layout.
    let chunks = TextChunker::split(&source);
    assert!(chunks.len() > 1, "long paragraph must be split");
    let mut retried: Vec<String> = Vec::new();
    for chunk in &chunks {
        let sentence_translations: Vec<String> = TextChunker::split_sentences(&chunk.text);
        for sentence in &sentence_translations {
            assert_eq!(
                OutputSanitizer::is_degenerate(sentence, sentence, english),
                None,
                "sentence rejected: {sentence:?}"
            );
        }
        let joined = sentence_translations.join(" ");
        assert_eq!(
            OutputSanitizer::is_degenerate(&chunk.text, &joined, english),
            None
        );
        retried.push(joined);
    }
    let composed = TextChunker::compose(&chunks, &retried).expect("compose");
    assert_eq!(composed, source);
}

#[test]
fn tokens_are_restored_per_chunk_before_composition() {
    let source = "# Install\n\nRun `ollama pull tencent/hy-mt2-7b` from https://ollama.com.";
    let chunks = TextChunker::split(source);
    let english = LanguageTable::get("en").expect("en");
    let mut translated: Vec<String> = Vec::new();
    for chunk in &chunks {
        // A noisy "translation" that corrupts the technical tokens.
        let noisy = chunk
            .text
            .replace("ollama.com", "olama.kom")
            .replace("tencent/hy-mt2-7b", "Tencent/HY-MT2-7B");
        let restored = TokenRestorer::restore(&chunk.text, &noisy).expect("restored");
        if chunk.is_heading {
            assert_eq!(
                OutputSanitizer::is_degenerate(&chunk.text, &restored, english),
                None
            );
        }
        translated.push(restored);
    }
    let composed = TextChunker::compose(&chunks, &translated).expect("compose");
    assert_eq!(composed, source);
}
