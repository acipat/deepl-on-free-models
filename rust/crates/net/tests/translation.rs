//! Acceptance tests for `ofm-net`, ported from `windows/tests/test_translation.py`
//! (plus the regression tests requested by the differential audit).
//!
//! There is no real network: every test starts a [`support::FakeServer`] on a
//! loopback `TcpListener` that speaks hand-written HTTP/1.1, NDJSON and SSE.

mod support;

use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::json;
use tokio::io::AsyncReadExt;
use tokio::net::TcpListener;

use ofm_config::{BackendConfig, BackendKind};
use ofm_i18n::{AppLanguage, Language, LanguageTable};
use ofm_net::{
    CancelFlag, ErrorKind, PartialFn, ProgressFn, TranslateRequest, TranslationError,
    TranslationOutput, Translator,
};
use ofm_text::{TranslationStyle, TranslationTone};

use support::{find_bytes, ollama_done, ollama_frame, sse_done, sse_frame, FakeServer, Reply};

// --------------------------------------------------------------------- setup

fn language(code: &str) -> &'static Language {
    LanguageTable::get(code).expect("language exists")
}

fn ollama_config(server: &FakeServer, model: &str) -> BackendConfig {
    BackendConfig {
        kind: BackendKind::Ollama,
        base_url: server.url(),
        model: model.to_string(),
        ..BackendConfig::default()
    }
}

fn openai_config(server: &FakeServer, model: &str) -> BackendConfig {
    BackendConfig {
        kind: BackendKind::OpenAI,
        base_url: server.url(),
        model: model.to_string(),
        api_key: "secret".to_string(),
        ..BackendConfig::default()
    }
}

async fn translate(
    translator: &Translator,
    text: &str,
    config: &BackendConfig,
    fallback: Option<&BackendConfig>,
    cancel: Option<CancelFlag>,
) -> Result<TranslationOutput, TranslationError> {
    translator
        .translate(TranslateRequest {
            text,
            source: language("uk"),
            source_explicit: true,
            target: language("en"),
            style: TranslationStyle::Auto,
            tone: TranslationTone::Standard,
            config,
            fallback,
            cancel,
            on_progress: None,
            on_partial: None,
        })
        .await
}

async fn translate_observed(
    translator: &Translator,
    text: &str,
    config: &BackendConfig,
    on_progress: Option<ProgressFn>,
    on_partial: Option<PartialFn>,
) -> Result<TranslationOutput, TranslationError> {
    translator
        .translate(TranslateRequest {
            text,
            source: language("uk"),
            source_explicit: true,
            target: language("en"),
            style: TranslationStyle::Auto,
            tone: TranslationTone::Standard,
            config,
            fallback: None,
            cancel: None,
            on_progress,
            on_partial,
        })
        .await
}

type ProgressSink = Arc<Mutex<Vec<(usize, usize)>>>;
type PartialSink = Arc<Mutex<Vec<String>>>;

fn progress_log() -> (ProgressFn, ProgressSink) {
    let log = Arc::new(Mutex::new(Vec::new()));
    let sink = Arc::clone(&log);
    let callback: ProgressFn =
        Arc::new(move |done, total| sink.lock().expect("progress log").push((done, total)));
    (callback, log)
}

fn partial_log() -> (PartialFn, PartialSink) {
    let log: PartialSink = Arc::new(Mutex::new(Vec::new()));
    let sink = Arc::clone(&log);
    let callback: PartialFn =
        Arc::new(move |text: &str| sink.lock().expect("partial log").push(text.to_string()));
    (callback, log)
}

/// The Ollama "done, nothing generated" frame.
fn empty_done() -> Vec<u8> {
    b"{\"done\": true}\n".to_vec()
}

/// A frame whose content is far larger than the byte cap of a short block.
fn over_cap_frame() -> Vec<u8> {
    ollama_frame(&"x".repeat(3_000))
}

/// A loopback address with nothing listening on it.
async fn dead_address() -> std::net::SocketAddr {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind");
    let address = listener.local_addr().expect("address");
    drop(listener);
    address
}

// ------------------------------------------------- 1. streaming protocols

#[tokio::test]
async fn ollama_and_openai_streams_produce_the_same_text() {
    let ollama_server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Hello "),
            ollama_frame("world."),
            ollama_done(2, 500_000_000),
        ])
    })
    .await;
    let openai_server = FakeServer::start(|_| {
        Reply::stream(vec![sse_frame("Hello "), sse_frame("world."), sse_done()])
    })
    .await;

    let translator = Translator::new();
    let ollama_backend = ollama_config(&ollama_server, "hy-mt2:7b");
    let openai_backend = openai_config(&openai_server, "gpt-test");

    let (progress, progress_sink) = progress_log();
    let (partial, partial_sink) = partial_log();
    let ollama = translate_observed(
        &translator,
        "Привіт, світе.",
        &ollama_backend,
        Some(progress),
        Some(partial),
    )
    .await
    .expect("ollama translation");
    let openai = translate(&translator, "Привіт, світе.", &openai_backend, None, None)
        .await
        .expect("openai translation");

    assert_eq!(ollama.text, "Hello world.");
    assert_eq!(openai.text, "Hello world.");
    assert_eq!(ollama.warnings, 0);
    assert_eq!(openai.warnings, 0);
    assert_eq!(
        *progress_sink.lock().expect("progress"),
        vec![(0, 1), (1, 1)]
    );
    assert_eq!(
        partial_sink
            .lock()
            .expect("partials")
            .last()
            .map(String::as_str),
        Some("Hello world.")
    );
    assert!(ollama.duration_ms.is_some());
    let rate = ollama.tokens_per_second.expect("server rate");
    assert!((rate - 4.0).abs() < 1e-6, "rate {rate}");
    assert!(!ollama.used_fallback);
    assert!(!openai.used_fallback);

    let ollama_requests = ollama_server.requests();
    assert_eq!(ollama_requests.len(), 1);
    assert_eq!(ollama_requests[0].method, "POST");
    assert_eq!(ollama_requests[0].path, "/api/chat");
    assert_eq!(ollama_requests[0].body["stream"], true);
    let options = &ollama_requests[0].body["options"];
    assert_eq!(options["num_ctx"], 8192);
    assert_eq!(options["repeat_penalty"], 1.05);
    assert_eq!(options["num_predict"], 4096);
    assert_eq!(options["temperature"], 0.7);
    assert_eq!(options["top_p"], 0.6);
    assert_eq!(options["top_k"], 20);
    assert_eq!(
        options["stop"].as_array().expect("stop sequences").len(),
        3,
        "all three chat-template stop sequences are sent"
    );
    assert!(ollama_requests[0].header("authorization").is_none());

    let openai_requests = openai_server.requests();
    assert_eq!(openai_requests.len(), 1);
    assert_eq!(openai_requests[0].path, "/v1/chat/completions");
    assert_eq!(openai_requests[0].body["temperature"], 0.7);
    assert_eq!(openai_requests[0].body["top_p"], 0.6);
    assert_eq!(openai_requests[0].body["max_tokens"], 4096);
    assert_eq!(openai_requests[0].body["stream"], true);
    assert_eq!(
        openai_requests[0].header("authorization"),
        Some("Bearer secret")
    );
    assert_eq!(
        openai_requests[0].header("content-type"),
        Some("application/json")
    );
}

#[tokio::test]
async fn openai_base_with_v1_is_not_doubled() {
    let server = FakeServer::start(|_| Reply::stream(vec![sse_frame("Hi."), sse_done()])).await;
    let mut config = openai_config(&server, "gpt-test");
    config.base_url = format!("{}/v1/", server.url());

    let output = translate(&Translator::new(), "Привіт.", &config, None, None)
        .await
        .expect("translated");

    assert_eq!(output.text, "Hi.");
    assert_eq!(server.requests()[0].path, "/v1/chat/completions");
}

#[tokio::test]
async fn malformed_frames_and_keep_alives_are_skipped() {
    let ollama_server = FakeServer::start(|_| {
        Reply::stream(vec![
            b"not json at all\n".to_vec(),
            ollama_frame("Hello "),
            ollama_frame("world."),
            ollama_done(2, 500_000_000),
            b"{broken\n".to_vec(),
        ])
    })
    .await;
    let openai_server = FakeServer::start(|_| {
        Reply::stream(vec![
            b": keep-alive\n".to_vec(),
            b"event: message\n".to_vec(),
            b"data: {broken json\n".to_vec(),
            sse_frame("Hello "),
            sse_frame("world."),
            sse_done(),
        ])
    })
    .await;

    let translator = Translator::new();
    let ollama = translate(
        &translator,
        "Привіт, світе.",
        &ollama_config(&ollama_server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("ollama");
    let openai = translate(
        &translator,
        "Привіт, світе.",
        &openai_config(&openai_server, "gpt-test"),
        None,
        None,
    )
    .await
    .expect("openai");

    assert_eq!(ollama.text, "Hello world.");
    assert_eq!(openai.text, "Hello world.");
}

#[tokio::test]
async fn a_frame_split_inside_a_utf8_character_is_decoded() {
    let payload = "Hello, world \u{2014} caf\u{e9} \u{1F44B}";
    let frames = [ollama_frame(payload), ollama_done(2, 500_000_000)];
    let frame = frames[0].clone();
    let done = frames[1].clone();
    let split = find_bytes(&frame, "\u{1F44B}".as_bytes()).expect("emoji") + 2;
    let first = frame[..split].to_vec();
    let second = frame[split..].to_vec();

    let server = FakeServer::start(move |_| {
        Reply::slow_stream(
            vec![first.clone(), second.clone(), done.clone()],
            Duration::from_millis(25),
        )
    })
    .await;

    let output = translate(
        &Translator::new(),
        "Привіт, світе.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(output.text, format!("{payload}."));
}

#[tokio::test]
async fn cr_only_line_endings_are_split() {
    // F6: `requests.iter_lines()` uses universal newlines, so a bare CR must
    // terminate NDJSON and SSE frames too.
    let ndjson = concat!(
        "{\"message\":{\"content\":\"Hello\"},\"done\":false}\r",
        "{\"done\":true}\r"
    );
    let server = FakeServer::start(move |_| {
        Reply::body(ndjson.as_bytes().to_vec()).header("Content-Type", "application/x-ndjson")
    })
    .await;
    let output = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");
    assert_eq!(output.text, "Hello.");

    let sse = concat!(
        "data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}\r\r",
        "data: [DONE]\r"
    );
    let server = FakeServer::start(move |_| {
        Reply::body(sse.as_bytes().to_vec()).header("Content-Type", "text/event-stream")
    })
    .await;
    let output = translate(
        &Translator::new(),
        "Привіт.",
        &openai_config(&server, "gpt-test"),
        None,
        None,
    )
    .await
    .expect("translated");
    assert_eq!(output.text, "Hello.");
}

#[tokio::test]
async fn crlf_line_endings_are_split() {
    let ndjson = concat!(
        "{\"message\":{\"content\":\"Hello\"},\"done\":false}\r\n",
        "{\"done\":true}\r\n"
    );
    let server = FakeServer::start(move |_| Reply::body(ndjson.as_bytes().to_vec())).await;
    let output = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");
    assert_eq!(output.text, "Hello.");
}

#[tokio::test]
async fn a_gzip_encoded_stream_is_decoded() {
    // F7: gzip(NDJSON) with `Content-Encoding: gzip`, compressed by Python
    // (`gzip.compress(..., mtime=0)`) for the three frames below:
    //   {"message":{"content":"Hello "},"done":false}
    //   {"message":{"content":"world."},"done":false}
    //   {"done":true,"done_reason":"stop","eval_count":2,"eval_duration":500000000}
    const GZIP: &[u8] = &[
        0x1f, 0x8b, 0x08, 0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0xff, 0x6d, 0x8c, 0x41, 0x0a, 0x83,
        0x40, 0x10, 0x04, 0xef, 0xbe, 0x42, 0xfa, 0x2c, 0x22, 0x81, 0x5c, 0x7c, 0x41, 0x7e, 0x21,
        0x83, 0x3b, 0x09, 0xc2, 0xb8, 0x13, 0x76, 0x66, 0xcd, 0x61, 0xd9, 0xbf, 0x47, 0xd1, 0xa3,
        0x7d, 0x2b, 0xba, 0xba, 0x0b, 0x56, 0x36, 0xa3, 0x0f, 0x63, 0x2c, 0x98, 0x35, 0x3a, 0x47,
        0xc7, 0x88, 0x17, 0x8b, 0x68, 0x8b, 0xda, 0x21, 0x68, 0xdc, 0xbb, 0x37, 0x89, 0x71, 0x6d,
        0xca, 0xbd, 0xfd, 0xd3, 0x24, 0xa1, 0xbf, 0xb1, 0x4f, 0xf4, 0x94, 0xf9, 0xac, 0xa6, 0xc4,
        0x64, 0x1a, 0xf7, 0x89, 0xb9, 0x7e, 0xd1, 0x81, 0x37, 0x92, 0x69, 0xd6, 0x7c, 0xdc, 0x3c,
        0x2e, 0x0c, 0x39, 0x91, 0x2f, 0x87, 0xf5, 0x1c, 0xae, 0xd4, 0xe6, 0x0f, 0x08, 0xf2, 0x45,
        0x83, 0xa8, 0x00, 0x00, 0x00,
    ];
    let server = FakeServer::start(|_| {
        Reply::body(GZIP.to_vec())
            .header("Content-Encoding", "gzip")
            .header("Content-Type", "application/x-ndjson")
    })
    .await;

    let output = translate(
        &Translator::new(),
        "Привіт, світе.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");
    assert_eq!(output.text, "Hello world.");
    assert_eq!(server.request_count(), 1);
}

// ------------------------------------------------- 2. prompts & structure

#[tokio::test]
async fn headings_use_the_heading_instruction() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![ollama_frame("Title"), ollama_done(1, 500_000_000)])
    })
    .await;
    let output = translate(
        &Translator::new(),
        "# Заголовок",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(output.text, "# Title");
    let prompt = server.requests()[0].content().to_string();
    assert!(
        prompt.contains("Translate this heading into English."),
        "{prompt}"
    );
    assert!(prompt.starts_with("The source language is Ukrainian. "));
}

#[tokio::test]
async fn an_auto_source_language_is_not_prefixed() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![ollama_frame("Hello."), ollama_done(1, 500_000_000)])
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");
    let output = Translator::new()
        .translate(TranslateRequest {
            text: "Привіт.",
            source: language("auto"),
            source_explicit: false,
            target: language("en"),
            style: TranslationStyle::Auto,
            tone: TranslationTone::Standard,
            config: &config,
            fallback: None,
            cancel: None,
            on_progress: None,
            on_partial: None,
        })
        .await
        .expect("translated");

    assert_eq!(output.text, "Hello.");
    assert!(!server.requests()[0]
        .content()
        .starts_with("The source language"));
}

#[tokio::test]
async fn a_short_question_keeps_the_selected_style_and_tone() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Könnten Sie mir den Bericht schicken?"),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");
    let output = Translator::new()
        .translate(TranslateRequest {
            text: "Could you send me the report?",
            source: language("en"),
            source_explicit: true,
            target: language("de"),
            style: TranslationStyle::Literal,
            tone: TranslationTone::Formal,
            config: &config,
            fallback: None,
            cancel: None,
            on_progress: None,
            on_partial: None,
        })
        .await
        .expect("translated");

    assert_eq!(output.text, "Könnten Sie mir den Bericht schicken?");
    let prompt = server.requests()[0].content().to_string();
    assert!(
        prompt.contains("Please translate the following text into German."),
        "{prompt}"
    );
    assert!(
        prompt.contains("[literal, word for word; formal and professional]"),
        "the selected style and tone must survive: {prompt}"
    );
    assert!(!prompt.contains("heading"), "{prompt}");
    assert_eq!(
        prompt,
        "The source language is English. Please translate the following text into German. \
         Note that the translation style must strictly conform to [literal, word for word; \
         formal and professional]:\n\nCould you send me the report?"
    );
}

#[tokio::test]
async fn a_markdown_heading_keeps_the_heading_instruction_and_the_style() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![ollama_frame("Titel"), ollama_done(1, 500_000_000)])
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");
    let output = Translator::new()
        .translate(TranslateRequest {
            text: "## Title",
            source: language("en"),
            source_explicit: true,
            target: language("de"),
            style: TranslationStyle::Literal,
            tone: TranslationTone::Formal,
            config: &config,
            fallback: None,
            cancel: None,
            on_progress: None,
            on_partial: None,
        })
        .await
        .expect("translated");

    assert_eq!(output.text, "## Titel");
    let prompt = server.requests()[0].content().to_string();
    assert!(
        prompt.contains("Please translate this heading into German."),
        "{prompt}"
    );
    assert!(
        prompt.contains("[literal, word for word; formal and professional]"),
        "{prompt}"
    );
}

#[tokio::test]
async fn an_explicit_source_language_is_prefixed() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Good morning."),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");
    Translator::new()
        .translate(TranslateRequest {
            text: "Guten Morgen.",
            source: language("de"),
            source_explicit: true,
            target: language("en"),
            style: TranslationStyle::Auto,
            tone: TranslationTone::Standard,
            config: &config,
            fallback: None,
            cancel: None,
            on_progress: None,
            on_partial: None,
        })
        .await
        .expect("translated");

    let prompt = server.requests()[0].content().to_string();
    assert!(
        prompt.starts_with("The source language is German. "),
        "{prompt}"
    );
}

#[tokio::test]
async fn a_detected_source_language_is_not_prefixed() {
    // The script detector maps Arabic script to Arabic; a Persian sentence then
    // looks like Arabic. That guess must not be asserted to the model.
    let detected = LanguageTable::detect("مرحبا بالعالم، هذا اختبار.", AppLanguage::System)
        .expect("Arabic script is detected");
    assert_eq!(detected.code, "ar");

    let server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Hello, world."),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");
    Translator::new()
        .translate(TranslateRequest {
            text: "مرحبا بالعالم، هذا اختبار.",
            source: detected,
            source_explicit: false,
            target: language("en"),
            style: TranslationStyle::Auto,
            tone: TranslationTone::Standard,
            config: &config,
            fallback: None,
            cancel: None,
            on_progress: None,
            on_partial: None,
        })
        .await
        .expect("translated");

    let prompt = server.requests()[0].content().to_string();
    assert!(!prompt.starts_with("The source language"), "{prompt}");
    assert!(
        !prompt.contains("The source language is Arabic"),
        "{prompt}"
    );
}

#[tokio::test]
async fn translate_gemma_uses_the_instruction_published_by_its_model_card() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Hallo, Welt!"),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;
    let config = ollama_config(&server, "translategemma:4b");
    let output = Translator::new()
        .translate(TranslateRequest {
            text: "Hello, world!",
            source: language("en"),
            source_explicit: true,
            target: language("de"),
            style: TranslationStyle::Auto,
            tone: TranslationTone::Standard,
            config: &config,
            fallback: None,
            cancel: None,
            on_progress: None,
            on_partial: None,
        })
        .await
        .expect("translated");

    assert_eq!(output.text, "Hallo, Welt!");
    let prompt = server.requests()[0].content().to_string();
    assert!(
        prompt.starts_with(
            "The source language is English. You are a professional English (en) to German \
             (de) translator."
        ),
        "{prompt}"
    );
    assert!(
        prompt.contains("Please translate the following English text into German:"),
        "{prompt}"
    );
    assert!(
        prompt.ends_with(":\n\n\nHello, world!"),
        "two blank lines before the text: {prompt}"
    );
}

#[tokio::test]
async fn the_prompt_preview_equals_the_first_engine_prompt() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Könnten Sie mir den Bericht schicken?"),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");
    let text = "Could you send me the report?";
    let expected = ofm_net::first_prompt_for_text(
        text,
        language("en"),
        true,
        language("de"),
        TranslationStyle::Literal,
        TranslationTone::Formal,
        &config.model,
    )
    .expect("a first prompt");

    Translator::new()
        .translate(TranslateRequest {
            text,
            source: language("en"),
            source_explicit: true,
            target: language("de"),
            style: TranslationStyle::Literal,
            tone: TranslationTone::Formal,
            config: &config,
            fallback: None,
            cancel: None,
            on_progress: None,
            on_partial: None,
        })
        .await
        .expect("translated");

    assert_eq!(server.requests()[0].content(), expected);
}

#[tokio::test]
async fn multiline_input_keeps_the_line_count_and_prefixes() {
    let server = FakeServer::start(|request| {
        let content = request.content();
        for (source, translated) in [
            ("Заголовок", "Title"),
            ("Пункт перший", "First item"),
            ("Другий пункт", "Second item"),
        ] {
            if content.contains(source) {
                return Reply::stream(vec![ollama_frame(translated), ollama_done(1, 500_000_000)]);
            }
        }
        Reply::stream(vec![ollama_frame("?"), ollama_done(1, 500_000_000)])
    })
    .await;

    let output = translate(
        &Translator::new(),
        "# Заголовок\n\n- Пункт перший\n1. Другий пункт",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    let lines: Vec<&str> = output.text.split('\n').collect();
    assert_eq!(lines, vec!["# Title", "", "- First item", "1. Second item"]);
    assert_eq!(lines.len(), 4);
}

#[tokio::test]
async fn code_blocks_and_punctuation_only_lines_pass_through() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![ollama_frame("Hello."), ollama_done(1, 500_000_000)])
    })
    .await;
    let output = translate(
        &Translator::new(),
        "```\nlet x = 1;\n```\n---\nПривіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(output.text, "```\nlet x = 1;\n```\n---\nHello.");
    assert_eq!(server.request_count(), 1, "only the text line is sent");
}

#[tokio::test]
async fn a_roman_numeral_only_line_is_not_sent() {
    // F10: Python's `str.isalpha()` is false for `Ⅻ` (category Nl), so the
    // line is passed through instead of being sent to the model.
    let server = FakeServer::start(|_| {
        Reply::stream(vec![ollama_frame("Twelve."), ollama_done(1, 500_000_000)])
    })
    .await;
    let output = translate(
        &Translator::new(),
        "\u{216B}",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(output.text, "\u{216B}");
    assert_eq!(output.warnings, 0);
    assert_eq!(server.request_count(), 0);
}

// ------------------------------------------------- 3. marker truncation

#[tokio::test]
async fn a_marker_stops_the_block_early() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Hello"),
            ollama_frame("hy_end"),
            ollama_frame(" ignored"),
            // Never read: reading it would raise an HTTP error.
            br#"{"error": "this frame must never be read"}"#.to_vec(),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;

    let output = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    // The source ends with a period; TokenRestorer preserves it.
    assert_eq!(output.text, "Hello.");
    assert_eq!(output.warnings, 0);
    assert_eq!(server.request_count(), 1);
}

#[tokio::test]
async fn a_marker_split_across_frames_is_still_found() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Hello"),
            ollama_frame("hy_"),
            ollama_frame("end"),
            ollama_frame(" ignored"),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;

    let output = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(output.text, "Hello.");
}

// ------------------------------------------------- 4. retry ladder

#[tokio::test]
async fn empty_output_runs_the_retry_ladder_and_counts_a_warning() {
    let server = FakeServer::start(|request| {
        if request.content().contains("Другий") {
            Reply::stream(vec![
                ollama_frame("Second line."),
                ollama_done(1, 500_000_000),
            ])
        } else {
            Reply::stream(vec![empty_done()])
        }
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");
    assert!((config.temperature - 0.7).abs() < 1e-6);

    let output = translate(
        &Translator::new(),
        "Привіт.\nДругий рядочок.",
        &config,
        None,
        None,
    )
    .await
    .expect("translated");

    let requests = server.requests();
    let first_block: Vec<_> = requests
        .iter()
        .filter(|request| request.content().contains("Привіт."))
        .collect();
    let second_block: Vec<_> = requests
        .iter()
        .filter(|request| request.content().contains("Другий рядочок."))
        .collect();
    // The block is a sentence, not a heading, so it uses the full ladder for
    // Auto/Standard: [generic x3, natural x2, plain x2]. The sentence fallback
    // cannot help a one-sentence block.
    assert_eq!(first_block.len(), 7);
    assert_eq!(second_block.len(), 1);
    assert_eq!(first_block[1].body["options"]["temperature"], 0.3);
    // The caller's configuration is never mutated by the retries.
    assert!((config.temperature - 0.7).abs() < 1e-6);

    assert_eq!(output.text, "Привіт.\nSecond line.");
    assert_eq!(output.warnings, 1);
    assert!(!output.used_fallback);
}

#[tokio::test]
async fn all_empty_blocks_return_the_source_with_a_warning() {
    let server = FakeServer::start(|_| Reply::stream(vec![empty_done()])).await;
    let output = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(output.text, "Привіт.");
    assert_eq!(output.warnings, 1);
    assert!(!output.used_fallback);
}

#[tokio::test]
async fn all_empty_blocks_switch_to_the_fallback() {
    let server = FakeServer::start(|request| {
        if request.model() == "primary" {
            Reply::stream(vec![empty_done()])
        } else {
            Reply::stream(vec![
                ollama_frame("Fallback text."),
                ollama_done(1, 500_000_000),
            ])
        }
    })
    .await;
    let primary = ollama_config(&server, "primary");
    let backup = ollama_config(&server, "backup");

    let output = translate(&Translator::new(), "Привіт.", &primary, Some(&backup), None)
        .await
        .expect("translated");

    assert!(output.used_fallback);
    assert_eq!(output.text, "Fallback text.");
    assert_eq!(output.warnings, 0);
}

#[tokio::test]
async fn a_replacement_character_is_rejected_before_token_cleanup() {
    let calls = Arc::new(AtomicUsize::new(0));
    let counter = Arc::clone(&calls);
    let server = FakeServer::start(move |_| {
        let call = counter.fetch_add(1, Ordering::SeqCst);
        if call == 0 {
            Reply::stream(vec![
                ollama_frame("Hello\u{FFFD}"),
                ollama_done(1, 500_000_000),
            ])
        } else {
            Reply::stream(vec![ollama_frame("Hello"), ollama_done(1, 500_000_000)])
        }
    })
    .await;

    let output = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(calls.load(Ordering::SeqCst), 2);
    assert_eq!(output.text, "Hello.");
}

#[tokio::test]
async fn the_sentence_fallback_translates_a_long_failing_block() {
    let server = FakeServer::start(|request| {
        let content = request.content();
        if content.contains("Перше речення.") && content.contains("Друге речення.")
        {
            Reply::stream(vec![empty_done()])
        } else if content.contains("Перше речення.") {
            Reply::stream(vec![
                ollama_frame("First sentence."),
                ollama_done(1, 500_000_000),
            ])
        } else if content.contains("Друге речення.") {
            Reply::stream(vec![
                ollama_frame("Second sentence."),
                ollama_done(1, 500_000_000),
            ])
        } else {
            Reply::stream(vec![empty_done()])
        }
    })
    .await;

    let output = translate(
        &Translator::new(),
        "Перше речення. Друге речення.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(output.text, "First sentence. Second sentence.");
    assert_eq!(output.warnings, 0);
}

#[tokio::test]
async fn an_over_budget_response_is_retried_at_a_lower_temperature() {
    // F1: a byte-cap overrun is an *empty candidate*, not a failed block.
    let calls = Arc::new(AtomicUsize::new(0));
    let counter = Arc::clone(&calls);
    let server = FakeServer::start(move |_| {
        let call = counter.fetch_add(1, Ordering::SeqCst);
        if call == 0 {
            Reply::stream(vec![over_cap_frame(), ollama_done(1, 500_000_000)])
        } else {
            Reply::stream(vec![ollama_frame("Hello."), ollama_done(1, 500_000_000)])
        }
    })
    .await;

    let output = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(calls.load(Ordering::SeqCst), 2);
    assert_eq!(output.text, "Hello.");
    assert_eq!(output.warnings, 0);
    let requests = server.requests();
    assert_eq!(requests[1].body["options"]["temperature"], 0.3);
}

#[tokio::test]
async fn an_over_budget_block_does_not_lose_the_rest_of_the_document() {
    let calls = Arc::new(AtomicUsize::new(0));
    let counter = Arc::clone(&calls);
    let server = FakeServer::start(move |request| {
        let call = counter.fetch_add(1, Ordering::SeqCst);
        if call == 0 {
            // The first attempt for the first block overruns the budget.
            return Reply::stream(vec![over_cap_frame(), ollama_done(1, 500_000_000)]);
        }
        if request.content().contains("Перший") {
            Reply::stream(vec![
                ollama_frame("First line."),
                ollama_done(1, 500_000_000),
            ])
        } else {
            Reply::stream(vec![
                ollama_frame("Second line."),
                ollama_done(1, 500_000_000),
            ])
        }
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");

    let output = translate(
        &Translator::new(),
        "Перший рядок.\nДругий рядок.",
        &config,
        None,
        None,
    )
    .await
    .expect("translated");

    assert_eq!(output.text, "First line.\nSecond line.");
    assert_eq!(output.warnings, 0);
    assert_eq!(server.request_count(), 3);
    assert_eq!(server.requests()[1].body["options"]["temperature"], 0.3);
}

#[tokio::test]
async fn an_over_budget_response_does_not_switch_to_the_fallback() {
    let calls = Arc::new(AtomicUsize::new(0));
    let counter = Arc::clone(&calls);
    let primary_server = FakeServer::start(move |_| {
        let call = counter.fetch_add(1, Ordering::SeqCst);
        if call == 0 {
            Reply::stream(vec![over_cap_frame(), ollama_done(1, 500_000_000)])
        } else {
            Reply::stream(vec![ollama_frame("Hello."), ollama_done(1, 500_000_000)])
        }
    })
    .await;
    let fallback_server = FakeServer::start(|_| {
        Reply::stream(vec![
            ollama_frame("Fallback text."),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;
    let primary = ollama_config(&primary_server, "primary");
    let backup = ollama_config(&fallback_server, "backup");

    let output = translate(&Translator::new(), "Привіт.", &primary, Some(&backup), None)
        .await
        .expect("translated");

    assert_eq!(output.text, "Hello.");
    assert!(!output.used_fallback);
    assert_eq!(output.warnings, 0);
    assert_eq!(primary_server.request_count(), 2);
    assert_eq!(fallback_server.request_count(), 0);
}

// ------------------------------------------------- 5. fallback & errors

#[tokio::test]
async fn the_fallback_config_is_used_on_a_connection_error() {
    let server =
        FakeServer::start(|_| Reply::stream(vec![sse_frame("Fallback works."), sse_done()])).await;
    let mut primary = openai_config(&server, "primary");
    primary.base_url = format!("http://{}", dead_address().await);
    let backup = openai_config(&server, "backup");

    let output = translate(
        &Translator::new(),
        "Привіт, світе.",
        &primary,
        Some(&backup),
        None,
    )
    .await
    .expect("translated");

    assert!(output.used_fallback);
    assert_eq!(output.text, "Fallback works.");
    let requests = server.requests();
    assert_eq!(requests.len(), 1);
    assert_eq!(requests[0].model(), "backup");
}

#[tokio::test]
async fn a_primary_http_error_retries_on_the_fallback() {
    let primary_server = FakeServer::start(|_| Reply::status(500)).await;
    let fallback_server =
        FakeServer::start(|_| Reply::stream(vec![sse_frame("Fallback works."), sse_done()])).await;
    let primary = openai_config(&primary_server, "primary");
    let backup = openai_config(&fallback_server, "backup");

    let output = translate(
        &Translator::new(),
        "Привіт, світе.",
        &primary,
        Some(&backup),
        None,
    )
    .await
    .expect("translated");

    assert!(output.used_fallback);
    assert_eq!(output.text, "Fallback works.");
    assert_eq!(primary_server.requests()[0].model(), "primary");
    assert_eq!(fallback_server.requests()[0].model(), "backup");
}

#[tokio::test]
async fn a_primary_failure_without_fallback_is_raised() {
    let server = FakeServer::start(|_| Reply::status(500)).await;
    let error = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect_err("server error");

    assert_eq!(error.kind, ErrorKind::Server);
    assert_eq!(error.status, Some(500));
}

#[tokio::test]
async fn http_statuses_map_to_the_documented_kinds() {
    let cases = [
        (401u16, ErrorKind::Unauthorized),
        (403, ErrorKind::Unauthorized),
        (429, ErrorKind::RateLimit),
        (500, ErrorKind::Server),
        (503, ErrorKind::Server),
        (400, ErrorKind::Http),
        (404, ErrorKind::Http),
    ];
    for (status, kind) in cases {
        let server = FakeServer::start(move |_| Reply::status(status)).await;
        let error = translate(
            &Translator::new(),
            "Привіт.",
            &ollama_config(&server, "hy-mt2:7b"),
            None,
            None,
        )
        .await
        .expect_err("status error");
        assert_eq!(error.kind, kind, "status {status}");
        assert_eq!(error.status, Some(status), "status {status}");
    }
}

#[tokio::test]
async fn the_rate_limit_message_is_localised() {
    ofm_i18n::set_language(AppLanguage::En);
    let server = FakeServer::start(|_| Reply::status(429).header("Retry-After", "12")).await;
    let error = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect_err("rate limited");

    assert_eq!(error.kind, ErrorKind::RateLimit);
    assert_eq!(error.detail, "12");
    assert!(
        error.message().contains("Too many requests"),
        "{}",
        error.message()
    );
}

#[tokio::test]
async fn the_model_and_api_key_are_checked_before_any_request() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![ollama_frame("Hi."), ollama_done(1, 500_000_000)])
    })
    .await;
    let translator = Translator::new();
    let mut config = ollama_config(&server, "");

    let error = translate(&translator, "Привіт.", &config, None, None)
        .await
        .expect_err("missing model");
    assert_eq!(error.kind, ErrorKind::Model);
    assert_eq!(error.message(), "Choose a model in Settings.");

    config.model = "hy-mt2:7b".to_string();
    config.requires_api_key = true;
    let error = translate(&translator, "Привіт.", &config, None, None)
        .await
        .expect_err("missing key");
    assert_eq!(error.kind, ErrorKind::Unauthorized);
    assert_eq!(error.detail, "api_key");
    assert_eq!(error.message(), "Add your API key in Settings.");
    assert_eq!(server.request_count(), 0);
}

#[tokio::test]
async fn an_invalid_base_url_maps_to_invalid_url() {
    let config = BackendConfig {
        kind: BackendKind::Ollama,
        base_url: "not a url".to_string(),
        model: "hy-mt2:7b".to_string(),
        ..BackendConfig::default()
    };
    let error = translate(&Translator::new(), "Привіт.", &config, None, None)
        .await
        .expect_err("invalid url");
    assert_eq!(error.kind, ErrorKind::InvalidUrl);
    assert!(error.message().contains("Invalid server URL"));
}

#[tokio::test]
async fn a_server_closing_early_is_interrupted() {
    let ollama_server = FakeServer::start(|_| Reply::stream(vec![ollama_frame("partial")])).await;
    let error = translate(
        &Translator::new(),
        "Привіт, світе.",
        &ollama_config(&ollama_server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect_err("interrupted");
    assert_eq!(error.kind, ErrorKind::Interrupted);

    let openai_server = FakeServer::start(|_| Reply::stream(vec![sse_frame("Hi")])).await;
    let error = translate(
        &Translator::new(),
        "Привіт, світе.",
        &openai_config(&openai_server, "gpt-test"),
        None,
        None,
    )
    .await
    .expect_err("interrupted");
    assert_eq!(error.kind, ErrorKind::Interrupted);
}

// ------------------------------------------------- 6. cancellation

#[tokio::test]
async fn cancellation_before_the_request_returns_quickly() {
    let server = FakeServer::start(|_| {
        Reply::stream(vec![ollama_frame("Hello"), ollama_done(1, 500_000_000)])
    })
    .await;
    let cancel: CancelFlag = Arc::new(AtomicBool::new(true));
    let started = Instant::now();

    let error = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        Some(cancel),
    )
    .await
    .expect_err("cancelled");

    assert_eq!(error.kind, ErrorKind::Cancelled);
    assert!(started.elapsed() < Duration::from_millis(500));
    assert_eq!(server.request_count(), 0);
}

#[tokio::test]
async fn cancellation_during_streaming_returns_quickly() {
    let server = FakeServer::start(|_| {
        Reply::slow_stream(
            vec![
                ollama_frame("Hello"),
                ollama_frame(" world"),
                ollama_done(2, 500_000_000),
            ],
            Duration::from_millis(300),
        )
    })
    .await;

    let translator = Translator::new();
    let config = ollama_config(&server, "hy-mt2:7b");
    let text = "Привіт, світе.".to_string();
    let source = language("uk");
    let target = language("en");
    let flag: CancelFlag = Arc::new(AtomicBool::new(false));
    let task_flag = Arc::clone(&flag);
    let task = tokio::spawn(async move {
        translator
            .translate(TranslateRequest {
                text: &text,
                source,
                source_explicit: true,
                target,
                style: TranslationStyle::Auto,
                tone: TranslationTone::Standard,
                config: &config,
                fallback: None,
                cancel: Some(task_flag),
                on_progress: None,
                on_partial: None,
            })
            .await
    });

    tokio::time::sleep(Duration::from_millis(80)).await;
    flag.store(true, Ordering::SeqCst);
    let started = Instant::now();
    let joined = tokio::time::timeout(Duration::from_secs(2), task)
        .await
        .expect("finished")
        .expect("joined");
    let error = joined.expect_err("cancelled");

    assert_eq!(error.kind, ErrorKind::Cancelled);
    assert!(started.elapsed() < Duration::from_secs(1));
}

// ------------------------------------------------- 7. rewrite

#[tokio::test]
async fn rewrite_uses_the_editor_instruction() {
    let server =
        FakeServer::start(|_| Reply::stream(vec![sse_frame("Improved text."), sse_done()])).await;
    let config = openai_config(&server, "gpt-test");

    let output = Translator::new()
        .rewrite("some text", language("en"), &config, None, None)
        .await
        .expect("rewritten");

    assert_eq!(output.text, "Improved text.");
    let prompt = server.requests()[0].content().to_string();
    assert!(prompt.starts_with("You are an editor."));
    assert!(prompt.contains("Rewrite the following text in English."));
    assert!(prompt.contains("clarity, grammar, tone and style."));
    assert!(prompt.contains("without explanations or quotes."));
    assert!(prompt.ends_with("some text"));
}

#[tokio::test]
async fn rewrite_retries_on_the_fallback_after_an_http_error() {
    let primary_server = FakeServer::start(|_| Reply::status(503)).await;
    let fallback_server =
        FakeServer::start(|_| Reply::stream(vec![sse_frame("Improved by fallback."), sse_done()]))
            .await;
    let primary = openai_config(&primary_server, "primary");
    let backup = openai_config(&fallback_server, "backup");

    let output = Translator::new()
        .rewrite("some text", language("en"), &primary, Some(&backup), None)
        .await
        .expect("rewritten");

    assert!(output.used_fallback);
    assert_eq!(output.text, "Improved by fallback.");
}

#[tokio::test]
async fn rewrite_reports_progress_and_partials() {
    // F2: Python's rewrite reports (0,1) then (1,1) and emits the final text.
    let server =
        FakeServer::start(|_| Reply::stream(vec![sse_frame("Improved text."), sse_done()])).await;
    let config = openai_config(&server, "gpt-test");
    let (progress, progress_sink) = progress_log();
    let (partial, partial_sink) = partial_log();

    let output = Translator::new()
        .rewrite_with(
            "some text",
            language("en"),
            &config,
            None,
            None,
            Some(progress),
            Some(partial),
        )
        .await
        .expect("rewritten");

    assert_eq!(output.text, "Improved text.");
    assert_eq!(
        *progress_sink.lock().expect("progress"),
        vec![(0, 1), (1, 1)]
    );
    assert_eq!(
        *partial_sink.lock().expect("partials"),
        vec!["Improved text.".to_string()]
    );
}

#[tokio::test]
async fn rewrite_fallback_reports_progress_and_partials() {
    let primary_server = FakeServer::start(|_| Reply::status(503)).await;
    let fallback_server =
        FakeServer::start(|_| Reply::stream(vec![sse_frame("Improved by fallback."), sse_done()]))
            .await;
    let primary = openai_config(&primary_server, "primary");
    let backup = openai_config(&fallback_server, "backup");
    let (progress, progress_sink) = progress_log();
    let (partial, partial_sink) = partial_log();

    let output = Translator::new()
        .rewrite_with(
            "some text",
            language("en"),
            &primary,
            Some(&backup),
            None,
            Some(progress),
            Some(partial),
        )
        .await
        .expect("rewritten");

    assert_eq!(output.text, "Improved by fallback.");
    assert_eq!(
        *progress_sink.lock().expect("progress"),
        vec![(0, 1), (0, 1), (1, 1)]
    );
    assert_eq!(
        *partial_sink.lock().expect("partials"),
        vec!["".to_string(), "Improved by fallback.".to_string()]
    );
}

// ------------------------------------------------- 8. warm-up & models

#[tokio::test]
async fn warm_up_returns_true_only_for_200() {
    let ok_server = FakeServer::start(|_| Reply::status(200)).await;
    let translator = Translator::new();
    let config = ollama_config(&ok_server, "hy-mt2:7b");

    assert!(translator.warm_up(&config).await);
    let request = &ok_server.requests()[0];
    assert_eq!(request.body["stream"], false);
    assert_eq!(request.body["options"]["num_predict"], 1);
    assert_eq!(request.body["options"]["num_ctx"], 8192);
    assert_eq!(request.body["keep_alive"], "5m");

    let failing_server = FakeServer::start(|_| Reply::status(503)).await;
    assert!(
        !translator
            .warm_up(&ollama_config(&failing_server, "hy-mt2:7b"))
            .await
    );
}

#[tokio::test]
async fn list_models_delegates_to_the_probe() {
    let server = FakeServer::start(|_| {
        Reply::json(
            200,
            &json!({"models": [{"name": "hy-mt2:7b"}, {"model": "x"}]}),
        )
    })
    .await;

    let models = Translator::new()
        .list_models(&ollama_config(&server, "hy-mt2:7b"))
        .await
        .expect("models");

    assert_eq!(models, vec!["hy-mt2:7b".to_string(), "x".to_string()]);
    assert_eq!(server.requests()[0].method, "GET");
    assert_eq!(server.requests()[0].path, "/api/tags");
}

// ------------------------------------------------- 9. concurrency & misc

#[test]
fn the_translator_is_send_and_sync() {
    fn assert_send_sync<T: Send + Sync>() {}
    assert_send_sync::<Translator>();
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn one_translator_serves_concurrent_jobs() {
    let server = FakeServer::start(|request| {
        if request.content().contains("Alpha") {
            Reply::stream(vec![ollama_frame("First."), ollama_done(1, 500_000_000)])
        } else {
            Reply::stream(vec![ollama_frame("Second."), ollama_done(1, 500_000_000)])
        }
    })
    .await;

    let translator = Arc::new(Translator::new());
    let config = Arc::new(ollama_config(&server, "hy-mt2:7b"));

    let first = {
        let translator = Arc::clone(&translator);
        let config = Arc::clone(&config);
        tokio::spawn(async move { translate(&translator, "Alpha.", &config, None, None).await })
    };
    let second = {
        let translator = Arc::clone(&translator);
        let config = Arc::clone(&config);
        tokio::spawn(async move { translate(&translator, "Beta.", &config, None, None).await })
    };
    let (first, second) = tokio::join!(first, second);

    assert_eq!(first.expect("joined").expect("translated").text, "First.");
    assert_eq!(second.expect("joined").expect("translated").text, "Second.");
    assert_eq!(server.request_count(), 2);
}

#[tokio::test]
async fn blank_text_is_returned_unchanged_without_a_request() {
    let server =
        FakeServer::start(|_| Reply::stream(vec![ollama_frame("x"), ollama_done(1, 500_000_000)]))
            .await;

    let output = translate(
        &Translator::new(),
        "   \n",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect("blank");

    assert_eq!(output.text, "   \n");
    assert_eq!(output.duration_ms, Some(0));
    assert_eq!(server.request_count(), 0);
}

#[tokio::test]
async fn a_whitespace_padded_model_id_is_still_rejected() {
    // Documented deviation: Python would send `"  "`; rejecting it locally is
    // the safer behaviour and keeps the "choose a model" error.
    let server = FakeServer::start(|_| {
        Reply::stream(vec![ollama_frame("Hi."), ollama_done(1, 500_000_000)])
    })
    .await;
    let error = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "   "),
        None,
        None,
    )
    .await
    .expect_err("missing model");

    assert_eq!(error.kind, ErrorKind::Model);
    assert_eq!(server.request_count(), 0);
}

// ------------------------------------------------- 10. audit round 2 fixes

#[tokio::test]
async fn an_over_cap_rewrite_with_a_marker_is_not_accepted() {
    // A rambling rewrite that hits the 512 KB cap and then leaks a marker is a
    // truncation, not a finished answer: it must be rejected as too long.
    let padding = "y".repeat(512_000);
    let server = FakeServer::start(move |_| {
        Reply::stream(vec![
            ollama_frame(&padding),
            ollama_frame("xhy_end"),
            ollama_done(1, 500_000_000),
        ])
    })
    .await;
    let config = ollama_config(&server, "hy-mt2:7b");

    let error = Translator::new()
        .rewrite("some text", language("en"), &config, None, None)
        .await
        .expect_err("rewrite output too long");

    assert_eq!(error.kind, ErrorKind::Empty);
    assert!(error.detail.contains("too long"), "{}", error.detail);
}

#[tokio::test]
async fn cancellation_interrupts_a_stalled_request() {
    // A server that accepts the connection and never answers must not keep the
    // Cancel button inert until the read timeout expires.
    let listener = TcpListener::bind("127.0.0.1:0").await.expect("bind");
    let address = listener.local_addr().expect("address");
    let server = tokio::spawn(async move {
        loop {
            let Ok((mut socket, _)) = listener.accept().await else {
                break;
            };
            tokio::spawn(async move {
                let mut buffer = [0u8; 4096];
                let _ = socket.read(&mut buffer).await;
                tokio::time::sleep(Duration::from_secs(30)).await;
            });
        }
    });

    let config = BackendConfig {
        kind: BackendKind::Ollama,
        base_url: format!("http://{address}"),
        model: "hy-mt2:7b".to_string(),
        ..BackendConfig::default()
    };
    let translator = Translator::new();
    let text = "Привіт.".to_string();
    let source = language("uk");
    let target = language("en");
    let flag: CancelFlag = Arc::new(AtomicBool::new(false));
    let task_flag = Arc::clone(&flag);
    let task = tokio::spawn(async move {
        translator
            .translate(TranslateRequest {
                text: &text,
                source,
                source_explicit: true,
                target,
                style: TranslationStyle::Auto,
                tone: TranslationTone::Standard,
                config: &config,
                fallback: None,
                cancel: Some(task_flag),
                on_progress: None,
                on_partial: None,
            })
            .await
    });

    tokio::time::sleep(Duration::from_millis(300)).await;
    flag.store(true, Ordering::SeqCst);
    let started = Instant::now();
    let joined = tokio::time::timeout(Duration::from_secs(2), task)
        .await
        .expect("cancel observed")
        .expect("joined");
    let error = joined.expect_err("cancelled");

    assert_eq!(error.kind, ErrorKind::Cancelled);
    assert!(started.elapsed() < Duration::from_secs(1));
    server.abort();
}

#[tokio::test]
async fn a_failed_fallback_keeps_the_primary_partial_result() {
    // Primary translates the first block, then fails. The fallback fails too:
    // the caller keeps the primary's work (translated block + source tail).
    let primary_server = FakeServer::start(|request| {
        if request.content().contains("Перший") {
            Reply::stream(vec![
                ollama_frame("First line."),
                ollama_done(1, 500_000_000),
            ])
        } else {
            Reply::status(500)
        }
    })
    .await;
    let fallback_server = FakeServer::start(|_| Reply::status(500)).await;
    let primary = ollama_config(&primary_server, "primary");
    let backup = ollama_config(&fallback_server, "backup");

    let output = translate(
        &Translator::new(),
        "Перший рядок.\nДругий рядок.",
        &primary,
        Some(&backup),
        None,
    )
    .await
    .expect("primary partial result");

    assert_eq!(output.text, "First line.\nДругий рядок.");
    assert_eq!(output.warnings, 1);
    assert!(!output.used_fallback);
}

#[tokio::test]
async fn a_failed_fallback_keeps_a_degenerate_primary_result() {
    let primary_server = FakeServer::start(|_| Reply::stream(vec![empty_done()])).await;
    let fallback_server = FakeServer::start(|_| Reply::status(500)).await;
    let primary = ollama_config(&primary_server, "primary");
    let backup = ollama_config(&fallback_server, "backup");

    let output = translate(&Translator::new(), "Привіт.", &primary, Some(&backup), None)
        .await
        .expect("primary result");

    assert_eq!(output.text, "Привіт.");
    assert_eq!(output.warnings, 1);
    assert!(!output.used_fallback);
}

#[tokio::test]
async fn an_identical_fallback_endpoint_is_not_retried() {
    let server = FakeServer::start(|_| Reply::status(500)).await;
    let primary = ollama_config(&server, "hy-mt2:7b");
    let mut fallback = ollama_config(&server, "hy-mt2:7b");
    fallback.temperature = 0.5;

    let error = translate(
        &Translator::new(),
        "Привіт.",
        &primary,
        Some(&fallback),
        None,
    )
    .await
    .expect_err("server error");

    assert_eq!(error.kind, ErrorKind::Server);
    assert_eq!(
        server.request_count(),
        1,
        "the same endpoint is not retried"
    );
}

#[tokio::test]
async fn duplicate_prompts_are_sent_once() {
    // Auto + a non-standard tone describes the same style as Natural, so the
    // styled and natural prompts are byte-identical.
    let server = FakeServer::start(|_| Reply::stream(vec![empty_done()])).await;
    let config = ollama_config(&server, "hy-mt2:7b");
    let source = "Це досить довгий рядок, який перевищує вісімдесят символів, \
                  щоб увімкнути стильову драбину.";
    assert!(source.chars().count() > 80);

    let output = Translator::new()
        .translate(TranslateRequest {
            text: source,
            source: language("uk"),
            source_explicit: true,
            target: language("en"),
            style: TranslationStyle::Auto,
            tone: TranslationTone::Formal,
            config: &config,
            fallback: None,
            cancel: None,
            on_progress: None,
            on_partial: None,
        })
        .await
        .expect("translated");

    assert_eq!(output.warnings, 1);
    // [styled x3, plain x2] instead of [styled x3, natural x2, plain x2].
    assert_eq!(server.request_count(), 5);

    let mut prompts: Vec<String> = server
        .requests()
        .iter()
        .map(|request| request.content().to_string())
        .collect();
    prompts.sort();
    prompts.dedup();
    assert_eq!(prompts.len(), 2, "no byte-identical prompt is sent twice");
}

#[tokio::test]
async fn an_endless_line_is_rejected_instead_of_buffered() {
    let blob = "x".repeat(5 * 1024 * 1024 + 64);
    let server = FakeServer::start(move |_| Reply::body(blob.clone().into_bytes())).await;

    let error = translate(
        &Translator::new(),
        "Привіт.",
        &ollama_config(&server, "hy-mt2:7b"),
        None,
        None,
    )
    .await
    .expect_err("oversized line");

    assert_eq!(error.kind, ErrorKind::Unexpected);
    assert!(error.detail.contains("4 MiB"), "{}", error.detail);
}
