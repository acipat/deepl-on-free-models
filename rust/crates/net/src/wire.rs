//! Wire protocol: endpoints, request bodies, headers and frame decoding.
//!
//! Both providers are addressed exactly like the Python implementation:
//! Ollama through `POST {base}/api/chat` with a JSON body and an NDJSON
//! response, every OpenAI-compatible server through
//! `POST {base}[/v1]/chat/completions` with Server-Sent Events. The `/v1`
//! segment is only inserted when the base URL does not already end in `/v1`.

use reqwest::header::{HeaderMap, HeaderValue, AUTHORIZATION, CONTENT_TYPE};
use serde::Serialize;
use serde_json::Value;

use ofm_config::{BackendConfig, BackendKind};

use crate::error::{ErrorKind, TranslationError};

/// Stop sequences handed to the server; a chat-template leak ends generation.
pub(crate) const STOP_SEQUENCES: [&str; 3] = [
    "hy_end",
    "<\u{FF5C}hy_place\u{2581}holder\u{2581}no\u{2581}8\u{FF5C}>",
    "<\u{FF5C}hy_place\u{2581}holder\u{2581}no\u{2581}2\u{FF5C}>",
];

/// Which streaming protocol a response uses.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub(crate) enum Protocol {
    /// NDJSON objects, one per line, terminated by `"done": true`.
    Ollama,
    /// SSE `data:` frames terminated by `data: [DONE]`.
    OpenAi,
}

/// One chat message; every request carries a single user message.
#[derive(Serialize)]
struct Message<'a> {
    role: &'a str,
    content: &'a str,
}

/// Ollama sampling options; typed so `f32` fields serialise to their shortest
/// decimal form (`0.7`, not `0.699999988079071`).
#[derive(Serialize)]
struct OllamaOptions {
    temperature: f32,
    top_p: f32,
    top_k: u32,
    repeat_penalty: f32,
    num_ctx: u32,
    num_predict: u32,
    stop: &'static [&'static str],
}

/// `POST /api/chat` body for a streaming translation.
#[derive(Serialize)]
pub(crate) struct OllamaBody<'a> {
    model: &'a str,
    messages: [Message<'a>; 1],
    stream: bool,
    keep_alive: &'a str,
    options: OllamaOptions,
}

/// `POST /chat/completions` body for a streaming translation.
#[derive(Serialize)]
pub(crate) struct OpenAiBody<'a> {
    model: &'a str,
    messages: [Message<'a>; 1],
    stream: bool,
    temperature: f32,
    top_p: f32,
    max_tokens: u32,
    stop: &'static [&'static str],
}

/// `POST /api/chat` body used to warm a local model up.
#[derive(Serialize)]
pub(crate) struct OllamaWarmUpBody<'a> {
    model: &'a str,
    messages: [Message<'a>; 1],
    stream: bool,
    keep_alive: &'a str,
    options: OllamaWarmUpOptions,
}

#[derive(Serialize)]
struct OllamaWarmUpOptions {
    temperature: f32,
    num_predict: u32,
    num_ctx: u32,
}

/// `POST /chat/completions` body used to warm a remote model up.
#[derive(Serialize)]
pub(crate) struct OpenAiWarmUpBody<'a> {
    model: &'a str,
    messages: [Message<'a>; 1],
    stream: bool,
    temperature: f32,
    max_tokens: u32,
}

/// `{base}/api/chat`.
pub(crate) fn ollama_chat_endpoint(base: &str) -> String {
    format!("{}/api/chat", base.trim_end_matches('/'))
}

/// `{base}/api/tags`.
pub(crate) fn ollama_tags_endpoint(base: &str) -> String {
    format!("{}/api/tags", base.trim_end_matches('/'))
}

/// `{base}[/v1]/{path}` with `/v1` inserted only when it is absent.
pub(crate) fn openai_endpoint(base: &str, path: &str) -> String {
    let value = base.trim_end_matches('/');
    if value.ends_with("/v1") {
        format!("{value}/{path}")
    } else {
        format!("{value}/v1/{path}")
    }
}

/// Endpoint and protocol for one streaming chat request.
pub(crate) fn chat_endpoint(base: &str, kind: BackendKind) -> (String, Protocol) {
    match kind {
        BackendKind::Ollama => (ollama_chat_endpoint(base), Protocol::Ollama),
        BackendKind::OpenAI => (openai_endpoint(base, "chat/completions"), Protocol::OpenAi),
    }
}

/// Streaming translation body for `config`.
pub(crate) fn ollama_body<'a>(prompt: &'a str, config: &'a BackendConfig) -> OllamaBody<'a> {
    OllamaBody {
        model: &config.model,
        messages: [Message {
            role: "user",
            content: prompt,
        }],
        stream: true,
        keep_alive: "5m",
        options: OllamaOptions {
            temperature: config.temperature,
            top_p: config.top_p,
            top_k: config.top_k,
            repeat_penalty: config.repetition_penalty,
            num_ctx: config.context_window,
            num_predict: 4096,
            stop: &STOP_SEQUENCES,
        },
    }
}

/// Streaming translation body for an OpenAI-compatible server.
pub(crate) fn openai_body<'a>(prompt: &'a str, config: &'a BackendConfig) -> OpenAiBody<'a> {
    OpenAiBody {
        model: &config.model,
        messages: [Message {
            role: "user",
            content: prompt,
        }],
        stream: true,
        temperature: config.temperature,
        top_p: config.top_p,
        max_tokens: 4096,
        stop: &STOP_SEQUENCES,
    }
}

/// Warm-up body for `config`; the caller picks the matching endpoint.
pub(crate) fn ollama_warm_up_body<'a>(
    prompt: &'a str,
    config: &'a BackendConfig,
) -> OllamaWarmUpBody<'a> {
    OllamaWarmUpBody {
        model: &config.model,
        messages: [Message {
            role: "user",
            content: prompt,
        }],
        stream: false,
        keep_alive: "5m",
        options: OllamaWarmUpOptions {
            temperature: 0.0,
            num_predict: 1,
            num_ctx: config.context_window,
        },
    }
}

/// Warm-up body for an OpenAI-compatible server.
pub(crate) fn openai_warm_up_body<'a>(
    prompt: &'a str,
    config: &'a BackendConfig,
) -> OpenAiWarmUpBody<'a> {
    OpenAiWarmUpBody {
        model: &config.model,
        messages: [Message {
            role: "user",
            content: prompt,
        }],
        stream: false,
        temperature: 0.0,
        max_tokens: 1,
    }
}

/// `Content-Type: application/json` plus `Authorization` for a non-empty key.
///
/// An API key that cannot be put into a header value is reported as a
/// connection failure, mirroring `requests.InvalidHeader`.
pub(crate) fn auth_headers(
    config: &BackendConfig,
    base: &str,
) -> Result<HeaderMap, TranslationError> {
    let mut headers = HeaderMap::new();
    if !config.api_key.is_empty() {
        headers.insert(AUTHORIZATION, bearer(&config.api_key, base)?);
    }
    Ok(headers)
}

/// JSON content type plus `Authorization` for a non-empty key.
pub(crate) fn json_headers(
    config: &BackendConfig,
    base: &str,
) -> Result<HeaderMap, TranslationError> {
    let mut headers = auth_headers(config, base)?;
    headers.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
    Ok(headers)
}

/// `Bearer <key>` as a header value.
pub(crate) fn bearer(key: &str, base: &str) -> Result<HeaderValue, TranslationError> {
    HeaderValue::from_str(&format!("Bearer {key}"))
        .map_err(|_| TranslationError::new(ErrorKind::Connection).with_detail(base))
}

/// Result of feeding one protocol frame to the accumulator.
pub(crate) type FrameOutcome = (bool, Option<(u64, f64)>);

/// An error carried inside a protocol frame (`{"error": …}`).
pub(crate) fn frame_error(detail: &str) -> TranslationError {
    TranslationError::new(ErrorKind::Http).with_detail(detail)
}

/// Decode one Ollama NDJSON line.
///
/// Returns `(terminal, stats)` where `stats` is `(tokens, seconds)` reported by
/// the server. Invalid JSON is ignored, exactly like the Python reader.
pub(crate) fn consume_ollama(
    line: &str,
    emit: &mut dyn FnMut(&str) -> bool,
) -> Result<FrameOutcome, TranslationError> {
    let Ok(value) = serde_json::from_str::<Value>(line) else {
        return Ok((false, None));
    };
    let Some(object) = value.as_object() else {
        return Ok((false, None));
    };

    if let Some(error) = object
        .get("error")
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
    {
        return Err(frame_error(error));
    }

    if let Some(content) = object
        .get("message")
        .and_then(Value::as_object)
        .and_then(|message| message.get("content"))
        .and_then(Value::as_str)
        .filter(|text| !text.is_empty())
    {
        if !emit(content) {
            return Ok((true, None));
        }
    }

    let mut stats = None;
    if object.get("done").and_then(Value::as_bool) == Some(true) {
        if let (Some(count), Some(duration)) = (
            object.get("eval_count").and_then(Value::as_u64),
            object.get("eval_duration").and_then(Value::as_f64),
        ) {
            if count > 0 && duration > 0.0 {
                stats = Some((count, duration / 1_000_000_000.0));
            }
        }
        if object.get("done_reason").and_then(Value::as_str) == Some("length") {
            return Err(TranslationError::new(ErrorKind::Empty).with_detail("length"));
        }
        return Ok((true, stats));
    }
    Ok((false, stats))
}

/// Decode one OpenAI-compatible SSE line.
///
/// Only `data:` frames carry content; comments (`: keep-alive`) and `event:`
/// lines are skipped. `stream=false` servers that answer with a buffered body
/// are not supported here, matching the Python implementation.
pub(crate) fn consume_openai(
    line: &str,
    emit: &mut dyn FnMut(&str) -> bool,
) -> Result<FrameOutcome, TranslationError> {
    let stripped = line.trim();
    let Some(payload) = stripped.strip_prefix("data:") else {
        return Ok((false, None));
    };
    let payload = payload.trim();
    if payload == "[DONE]" {
        return Ok((true, None));
    }
    if payload.is_empty() {
        return Ok((false, None));
    }
    let Ok(value) = serde_json::from_str::<Value>(payload) else {
        return Ok((false, None));
    };
    let Some(object) = value.as_object() else {
        return Ok((false, None));
    };

    match object.get("error") {
        Some(Value::Object(error)) => {
            let message = error
                .get("message")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| Value::Object(error.clone()).to_string());
            return Err(frame_error(&message));
        }
        Some(Value::String(text)) if !text.is_empty() => return Err(frame_error(text)),
        _ => {}
    }

    if let Some(first) = object
        .get("choices")
        .and_then(Value::as_array)
        .and_then(|choices| choices.first())
        .and_then(Value::as_object)
    {
        let delta = first
            .get("delta")
            .and_then(Value::as_object)
            .or_else(|| first.get("message").and_then(Value::as_object));
        if let Some(content) = delta
            .and_then(|delta| delta.get("content"))
            .and_then(Value::as_str)
            .filter(|text| !text.is_empty())
        {
            if !emit(content) {
                return Ok((true, None));
            }
        }
        if let Some(reason) = first
            .get("finish_reason")
            .and_then(Value::as_str)
            .filter(|text| !text.is_empty())
        {
            return match reason {
                "length" => Err(TranslationError::new(ErrorKind::Empty).with_detail("length")),
                "stop" | "end_turn" => Ok((true, None)),
                other => Err(TranslationError::new(ErrorKind::Interrupted).with_detail(other)),
            };
        }
    }
    Ok((false, None))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> BackendConfig {
        BackendConfig {
            model: "hy-mt2:7b".to_string(),
            ..BackendConfig::default()
        }
    }

    #[test]
    fn endpoints_follow_the_python_rules() {
        assert_eq!(
            ollama_chat_endpoint("http://127.0.0.1:11434"),
            "http://127.0.0.1:11434/api/chat"
        );
        assert_eq!(
            ollama_tags_endpoint("http://127.0.0.1:11434/"),
            "http://127.0.0.1:11434/api/tags"
        );
        assert_eq!(
            openai_endpoint("https://api.example.test", "chat/completions"),
            "https://api.example.test/v1/chat/completions"
        );
        assert_eq!(
            openai_endpoint("https://api.example.test/v1/", "chat/completions"),
            "https://api.example.test/v1/chat/completions"
        );
        assert_eq!(
            openai_endpoint("https://openrouter.ai/api/v1", "models"),
            "https://openrouter.ai/api/v1/models"
        );
    }

    #[test]
    fn bodies_carry_the_python_generation_parameters() {
        let config = config();
        // Compare what actually goes on the wire: `to_value` would widen the
        // `f32` sampling values to their full binary expansion (1.0499999…),
        // while the serializer emits the shortest round-trip form (1.05) — the
        // form the Python implementation sends.
        let body: serde_json::Value = serde_json::from_str(
            &serde_json::to_string(&ollama_body("prompt", &config)).expect("serialise"),
        )
        .expect("parse back");
        assert_eq!(body["model"], "hy-mt2:7b");
        assert_eq!(body["stream"], true);
        assert_eq!(body["keep_alive"], "5m");
        assert_eq!(body["options"]["num_ctx"], 8192);
        assert_eq!(body["options"]["repeat_penalty"], 1.05);
        assert_eq!(body["options"]["num_predict"], 4096);
        assert_eq!(body["options"]["temperature"], 0.7);
        assert_eq!(body["options"]["stop"], serde_json::json!(STOP_SEQUENCES));
        assert_eq!(body["messages"][0]["role"], "user");
        assert_eq!(body["messages"][0]["content"], "prompt");

        let body: serde_json::Value = serde_json::from_str(
            &serde_json::to_string(&openai_body("prompt", &config)).expect("serialise"),
        )
        .expect("parse back");
        assert_eq!(body["temperature"], 0.7);
        assert_eq!(body["top_p"], 0.6);
        assert_eq!(body["max_tokens"], 4096);
        assert_eq!(body["stream"], true);
    }

    #[test]
    fn ollama_consumer_reads_content_and_stats() {
        let mut text = String::new();
        let mut emit = |piece: &str| {
            text.push_str(piece);
            true
        };
        let (terminal, stats) = consume_ollama(
            r#"{"message": {"content": "Hello"}, "done": false}"#,
            &mut emit,
        )
        .expect("frame");
        assert!(!terminal);
        assert!(stats.is_none());

        let (terminal, stats) = consume_ollama(
            r#"{"done": true, "done_reason": "stop", "eval_count": 2, "eval_duration": 500000000}"#,
            &mut emit,
        )
        .expect("frame");
        assert!(terminal);
        assert_eq!(stats, Some((2, 0.5)));
        assert_eq!(text, "Hello");
    }

    #[test]
    fn ollama_length_cut_is_an_empty_error() {
        let mut emit = |_piece: &str| true;
        let error = consume_ollama(r#"{"done": true, "done_reason": "length"}"#, &mut emit)
            .expect_err("length");
        assert_eq!(error.kind, ErrorKind::Empty);
    }

    #[test]
    fn malformed_frames_are_ignored() {
        let mut emit = |_piece: &str| true;
        assert_eq!(
            consume_ollama("not json", &mut emit).expect("ignored"),
            (false, None)
        );
        assert_eq!(
            consume_openai("data: {broken", &mut emit).expect("ignored"),
            (false, None)
        );
        assert_eq!(
            consume_openai(": keep-alive", &mut emit).expect("ignored"),
            (false, None)
        );
    }

    #[test]
    fn openai_consumer_reads_deltas_and_finish_reasons() {
        let mut text = String::new();
        let mut emit = |piece: &str| {
            text.push_str(piece);
            true
        };
        let frame = r#"data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":null}]}"#;
        assert_eq!(
            consume_openai(frame, &mut emit).expect("frame"),
            (false, None)
        );

        let stop = r#"data: {"choices":[{"delta":{},"finish_reason":"stop"}]}"#;
        assert_eq!(
            consume_openai(stop, &mut emit).expect("frame"),
            (true, None)
        );
        assert_eq!(
            consume_openai("data: [DONE]", &mut emit).expect("done"),
            (true, None)
        );
        assert_eq!(text, "Hi");
    }

    #[test]
    fn openai_unknown_finish_reason_is_interrupted() {
        let mut emit = |_piece: &str| true;
        let frame = r#"data: {"choices":[{"delta":{},"finish_reason":"content_filter"}]}"#;
        let error = consume_openai(frame, &mut emit).expect_err("filtered");
        assert_eq!(error.kind, ErrorKind::Interrupted);
    }

    #[test]
    fn openai_error_frames_become_http_errors() {
        let mut emit = |_piece: &str| true;
        let frame = r#"data: {"error": {"message": "no credits"}}"#;
        let error = consume_openai(frame, &mut emit).expect_err("error");
        assert_eq!(error.kind, ErrorKind::Http);
        assert!(error.detail.contains("no credits"));
    }

    #[test]
    fn marker_frame_terminates_generation() {
        let mut budget = crate::budget::OutputBudget::new(1_000);
        let mut emit = |piece: &str| budget.append(piece);
        let frame = r#"{"message": {"content": "hy_end"}, "done": false}"#;
        assert_eq!(
            consume_ollama(frame, &mut emit).expect("frame"),
            (true, None)
        );
    }
}
