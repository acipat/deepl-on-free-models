//! The streaming translator: provider protocols, retry ladder and fallback.
//!
//! Port of `Translator` in `windows/deepl_ofm/services/translation.py`.
//!
//! The pipeline for one job is:
//!
//! 1. [`TextChunker::split`] turns the document into one chunk per line.
//! 2. Each chunk is translated with the prompt ladder from [`PromptPlan`]:
//!    structurally recognised headings get the heading instruction, other
//!    blocks the styled instruction plus its fallbacks, and TranslateGemma the
//!    instruction published by its model card.
//! 3. Every candidate is validated with [`OutputSanitizer`], the protected
//!    tokens are restored and the source line's trailing punctuation is kept.
//! 4. A block that never validates is left in the source language and counted
//!    as a warning; when every block failed the whole job is retried on the
//!    fallback configuration.
//!
//! The [`Translator`] holds only the HTTP client, so several tasks may share
//! one instance (the app runs translate, file and write jobs concurrently).

use std::sync::atomic::Ordering;
use std::time::{Duration, Instant};

use reqwest::Client;

use ofm_config::{BackendConfig, BackendKind, PromptFamily};
use ofm_i18n::Language;
use ofm_text::{
    OutputSanitizer, PromptBuilder, TextChunk, TextChunker, TokenRestorer, TranslationStyle,
    TranslationTone,
};

use crate::budget::OutputBudget;
use crate::error::{http_error, ErrorKind, TranslationError};
use crate::pipeline::{
    contains_markdown, is_letter, markdown_structure, split_mixed_line, validated,
    with_source_language,
};
use crate::probe::probe_models;
use crate::prompt::{unique_prompts, PromptPlan};
use crate::request::{CancelFlag, TranslateRequest, TranslationOutput};
use crate::wire::{
    chat_endpoint, consume_ollama, consume_openai, json_headers, ollama_body, ollama_warm_up_body,
    openai_body, openai_warm_up_body, Protocol,
};

/// Connect timeout, like `_CONNECT_TIMEOUT` in the Python module.
const CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
/// Read timeout: the Python translator timeout (180 s).
const DEFAULT_TIMEOUT: Duration = Duration::from_secs(180);
/// How often the cancel flag is polled while waiting for network data.
const CANCEL_POLL: Duration = Duration::from_millis(40);
/// Pause before a lowered-temperature retry (Python: 0.120 s).
const RETRY_DELAY: Duration = Duration::from_millis(120);
/// Largest streamed line accepted before the response is declared broken.
const MAX_LINE_BYTES: usize = 4 * 1024 * 1024;
/// Byte cap for one `rewrite` response.
const REWRITE_MAX_BYTES: usize = 128_000 * 4;
/// The prompt used to load a model into memory.
const WARM_UP_PROMPT: &str = "Hello";

/// Streaming translation engine for Ollama and OpenAI-compatible backends.
///
/// The type is `Send + Sync` and keeps no per-request state: every job owns its
/// own accumulators, so one translator can serve several tasks at once.
pub struct Translator {
    client: Client,
}

impl Default for Translator {
    fn default() -> Self {
        Self::new()
    }
}

impl Translator {
    /// Build a translator (connect timeout 10 s, read timeout 180 s).
    pub fn new() -> Self {
        let client = Client::builder()
            .connect_timeout(CONNECT_TIMEOUT)
            .read_timeout(DEFAULT_TIMEOUT)
            .build()
            .unwrap_or_else(|error| {
                log::warn!("could not build the HTTP client ({error}); using defaults");
                Client::new()
            });
        Self { client }
    }

    // ------------------------------------------------------------------ public

    /// Translate `request.text` line by line, retrying the whole job on the
    /// fallback configuration when the primary backend fails.
    ///
    /// Cancellation is reported as [`ErrorKind::Cancelled`] and never retried.
    pub async fn translate(
        &self,
        request: TranslateRequest<'_>,
    ) -> Result<TranslationOutput, TranslationError> {
        let started = Instant::now();
        check_cancelled(request.cancel.as_ref())?;
        if request.text.trim().is_empty() {
            return Ok(TranslationOutput {
                text: request.text.to_string(),
                duration_ms: Some(0),
                ..TranslationOutput::default()
            });
        }

        let primary = self.run_job(&request, request.config).await;
        let (job, used_fallback) = match primary {
            Ok(job) => {
                // Swift retries the whole job when no block was translated.
                match distinct_fallback(&request) {
                    Some(fallback) if job.degenerate => {
                        log::info!("no block translated; retrying on the fallback backend");
                        emit_partial(&request.on_partial, "");
                        match self.run_job(&request, fallback).await {
                            Ok(fallback_job) => (fallback_job, true),
                            Err(failure) => {
                                if failure.error.kind == ErrorKind::Cancelled
                                    || is_cancelled(request.cancel.as_ref())
                                {
                                    return Err(TranslationError::new(ErrorKind::Cancelled));
                                }
                                log::warn!(
                                    "fallback failed ({}); keeping the primary result",
                                    failure.error
                                );
                                (job, false)
                            }
                        }
                    }
                    _ => (job, false),
                }
            }
            Err(failure) => {
                if failure.error.kind == ErrorKind::Cancelled
                    || is_cancelled(request.cancel.as_ref())
                {
                    return Err(TranslationError::new(ErrorKind::Cancelled));
                }
                let Some(fallback) = distinct_fallback(&request) else {
                    return Err(failure.error);
                };
                log::info!(
                    "primary translation failed ({}); retrying on the fallback backend",
                    failure.error
                );
                emit_partial(&request.on_partial, "");
                match self.run_job(&request, fallback).await {
                    Ok(fallback_job) => (fallback_job, true),
                    Err(fallback_failure) => {
                        if fallback_failure.error.kind == ErrorKind::Cancelled
                            || is_cancelled(request.cancel.as_ref())
                        {
                            return Err(TranslationError::new(ErrorKind::Cancelled));
                        }
                        // Both backends failed: keep the primary's partial work
                        // instead of losing it to the fallback's error.
                        log::warn!(
                            "fallback failed ({}); keeping the primary result",
                            fallback_failure.error
                        );
                        (failure.partial, false)
                    }
                }
            }
        };

        Ok(TranslationOutput {
            text: job.text,
            warnings: job.warnings,
            tokens_per_second: rate(job.tokens, job.seconds),
            duration_ms: Some(elapsed_ms(started)),
            used_fallback,
        })
    }

    /// Improve `text` (DeepL Write) with the editor instruction.
    ///
    /// The text is sent as one block; no line splitting and no token
    /// protection is applied, exactly like the Python `rewrite`. A caller that
    /// needs progress and partial output uses [`Self::rewrite_with`].
    pub async fn rewrite(
        &self,
        text: &str,
        target: &Language,
        config: &BackendConfig,
        fallback: Option<&BackendConfig>,
        cancel: Option<CancelFlag>,
    ) -> Result<TranslationOutput, TranslationError> {
        self.rewrite_with(text, target, config, fallback, cancel, None, None)
            .await
    }

    /// [`Self::rewrite`] with the progress and partial-result callbacks of the
    /// Python `rewrite`.
    ///
    /// Progress reports `(0, 1)` before the stream and `(1, 1)` once the
    /// cleaned text is available; a fallback retry reports `(0, 1)` again and
    /// emits an empty partial first, like the reference implementation.
    #[allow(clippy::too_many_arguments)]
    pub async fn rewrite_with(
        &self,
        text: &str,
        target: &Language,
        config: &BackendConfig,
        fallback: Option<&BackendConfig>,
        cancel: Option<CancelFlag>,
        on_progress: Option<crate::request::ProgressFn>,
        on_partial: Option<crate::request::PartialFn>,
    ) -> Result<TranslationOutput, TranslationError> {
        let started = Instant::now();
        check_cancelled(cancel.as_ref())?;
        let prompt = rewrite_prompt(text, target.english_name);

        let primary = self
            .rewrite_once(&prompt, config, cancel.as_ref(), &on_progress)
            .await;
        let (result, used_fallback) = match primary {
            Ok(result) => (result, false),
            Err(error) => {
                if error.kind == ErrorKind::Cancelled || is_cancelled(cancel.as_ref()) {
                    return Err(TranslationError::new(ErrorKind::Cancelled));
                }
                let fallback = fallback.filter(|candidate| !same_endpoint(candidate, config));
                let Some(fallback) = fallback else {
                    return Err(error);
                };
                log::info!("primary rewrite failed ({error}); retrying on the fallback backend");
                emit_partial(&on_partial, "");
                (
                    self.rewrite_once(&prompt, fallback, cancel.as_ref(), &on_progress)
                        .await?,
                    true,
                )
            }
        };
        emit_partial(&on_partial, &result.text);

        Ok(TranslationOutput {
            text: result.text,
            warnings: 0,
            tokens_per_second: rate(result.tokens, result.seconds),
            duration_ms: Some(elapsed_ms(started)),
            used_fallback,
        })
    }

    /// Return the model ids advertised by `config`'s backend.
    pub async fn list_models(
        &self,
        config: &BackendConfig,
    ) -> Result<Vec<String>, TranslationError> {
        probe_models(&self.client, config).await
    }

    /// Load `config`'s model into memory; a 200 response means it is warm.
    pub async fn warm_up(&self, config: &BackendConfig) -> bool {
        if config.model.trim().is_empty() {
            return false;
        }
        let base = config.compatible_base();
        let (url, kind) = match config.kind {
            BackendKind::Ollama => (
                crate::wire::ollama_chat_endpoint(&base),
                BackendKind::Ollama,
            ),
            BackendKind::OpenAI => (
                crate::wire::openai_endpoint(&base, "chat/completions"),
                BackendKind::OpenAI,
            ),
        };
        if validate_url(&url, &base).is_err() {
            return false;
        }
        let Ok(headers) = json_headers(config, &base) else {
            return false;
        };
        let request = match kind {
            BackendKind::Ollama => self
                .client
                .post(&url)
                .headers(headers)
                .json(&ollama_warm_up_body(WARM_UP_PROMPT, config)),
            BackendKind::OpenAI => self
                .client
                .post(&url)
                .headers(headers)
                .json(&openai_warm_up_body(WARM_UP_PROMPT, config)),
        };
        match request.send().await {
            Ok(response) => response.status().as_u16() == 200,
            Err(error) => {
                log::debug!("warm-up request failed: {error}");
                false
            }
        }
    }

    // --------------------------------------------------------------- pipeline

    /// Translate every chunk and recompose the document.
    async fn run_job(
        &self,
        request: &TranslateRequest<'_>,
        config: &BackendConfig,
    ) -> Result<JobResult, JobFailure> {
        let chunks = TextChunker::split(&TextChunker::normalize(request.text));
        if chunks.is_empty() {
            return Ok(JobResult {
                text: request.text.to_string(),
                ..JobResult::default()
            });
        }

        let total = chunks.len();
        report(&request.on_progress, 0, total);
        let mut translated: Vec<String> = Vec::with_capacity(total);
        let mut warnings = 0usize;
        let mut translated_count = 0usize;
        let mut tokens = 0u64;
        let mut seconds = 0.0f64;

        for (index, chunk) in chunks.iter().enumerate() {
            if let Err(error) = check_cancelled(request.cancel.as_ref()) {
                return Err(abandon_job(
                    error,
                    &chunks,
                    translated,
                    index,
                    JobProgress {
                        warnings,
                        translated_count,
                        tokens,
                        seconds,
                    },
                ));
            }
            let body = &chunk.text;
            let line = format!("{}{}", chunk.prefix, body);
            if chunk.is_code || !body.chars().any(is_letter) {
                // Fenced code and punctuation-only lines pass through untouched.
                translated.push(body.clone());
                emit_partial(
                    &request.on_partial,
                    &compose_through(&chunks, &translated, index),
                );
                report(&request.on_progress, index + 1, total);
                continue;
            }

            let (keep, translatable) = match split_mixed_line(body) {
                Some((keep, translatable)) => (keep, translatable),
                None => (String::new(), body.clone()),
            };

            let block = match self
                .translate_chunk(
                    &translatable,
                    request,
                    config,
                    contains_markdown(&line),
                    chunk.is_heading,
                )
                .await
            {
                Ok(block) => block,
                Err(error) if error.kind == ErrorKind::Empty => {
                    // Swift keeps the source line for this block and warns.
                    log::debug!("block left untranslated: {}", error.detail);
                    translated.push(format!("{keep}{translatable}"));
                    warnings += 1;
                    emit_partial(
                        &request.on_partial,
                        &compose_through(&chunks, &translated, index),
                    );
                    report(&request.on_progress, index + 1, total);
                    continue;
                }
                Err(error) => {
                    return Err(abandon_job(
                        error,
                        &chunks,
                        translated,
                        index,
                        JobProgress {
                            warnings,
                            translated_count,
                            tokens,
                            seconds,
                        },
                    ));
                }
            };

            let (translated_text, warning) =
                match TokenRestorer::restore(&translatable, &block.text) {
                    None => {
                        log::debug!("protected tokens changed in the model output");
                        (translatable.clone(), true)
                    }
                    Some(restored) => (
                        TokenRestorer::preserve_trailing_punctuation(&translatable, &restored),
                        block.warning,
                    ),
                };
            translated.push(format!("{keep}{translated_text}"));
            tokens += block.tokens;
            seconds += block.seconds;
            if warning {
                warnings += 1;
            } else {
                translated_count += 1;
            }
            emit_partial(
                &request.on_partial,
                &compose_through(&chunks, &translated, index),
            );
            report(&request.on_progress, index + 1, total);
        }

        Ok(JobResult {
            text: TextChunker::compose(&chunks, &translated).unwrap_or_default(),
            warnings,
            tokens,
            seconds,
            degenerate: warnings > 0 && translated_count == 0,
        })
    }

    /// Choose the prompt ladder for one block and translate it.
    async fn translate_chunk(
        &self,
        text: &str,
        request: &TranslateRequest<'_>,
        config: &BackendConfig,
        preserve_markdown: bool,
        is_heading: bool,
    ) -> Result<BlockResult, TranslationError> {
        let body = text.trim();
        let plan = PromptPlan {
            text: body,
            target: request.target,
            source: request.source,
            source_explicit: request.source_explicit,
            style: request.style,
            tone: request.tone,
            family: PromptFamily::for_model(&config.model),
            is_heading,
            preserve_markdown,
        };

        self.buffered_translation(
            plan,
            request,
            config,
            BlockOptions {
                preserve_line_breaks: false,
                requires_markdown_structure: false,
            },
        )
        .await
    }

    /// Try every prompt (with lowered-temperature retries) until one validates.
    async fn buffered_translation(
        &self,
        plan: PromptPlan<'_>,
        request: &TranslateRequest<'_>,
        config: &BackendConfig,
        options: BlockOptions,
    ) -> Result<BlockResult, TranslationError> {
        let source = plan.text;
        let source_count = source.chars().count();
        let max_bytes = source_count.saturating_mul(4).saturating_add(100).max(200) * 4;

        for (index, prompt) in plan.ladder().into_iter().enumerate() {
            let prompt = with_source_language(prompt, plan.source_hint());
            let attempts = if index == 0 { 3 } else { 2 };
            for attempt in 0..attempts {
                if attempt > 0 {
                    sleep_or_cancel(RETRY_DELAY, request.cancel.as_ref()).await?;
                }
                let retry_config = retry_config(config, attempt);
                let raw = self
                    .collect_candidate(&prompt, &retry_config, max_bytes, request.cancel.as_ref())
                    .await?;
                let Some(clean) = validated(
                    &raw.text,
                    source,
                    request.target,
                    options.preserve_line_breaks,
                ) else {
                    log::debug!("rejected model output (prompt {index}, attempt {attempt})");
                    continue;
                };
                if options.requires_markdown_structure
                    && markdown_structure(&clean) != markdown_structure(source)
                {
                    log::debug!("markdown structure changed (prompt {index}, attempt {attempt})");
                    continue;
                }
                return Ok(BlockResult {
                    text: clean,
                    warning: false,
                    tokens: raw.tokens,
                    seconds: raw.seconds,
                });
            }
        }

        if !(options.requires_markdown_structure
            || options.preserve_line_breaks && source.contains('\n'))
        {
            if let Some(segmented) = self.sentence_fallback(plan, request, config).await? {
                return Ok(segmented);
            }
        }
        Err(TranslationError::new(ErrorKind::Empty).with_detail("model output rejected"))
    }

    /// Translate sentence by sentence when the whole block keeps failing.
    async fn sentence_fallback(
        &self,
        plan: PromptPlan<'_>,
        request: &TranslateRequest<'_>,
        config: &BackendConfig,
    ) -> Result<Option<BlockResult>, TranslationError> {
        let source = plan.text;
        if source.contains("http") || source.contains("](") || source.contains('`') {
            return Ok(None);
        }
        let pieces = TextChunker::split_sentences(source);
        if pieces.len() <= 1 {
            return Ok(None);
        }

        let mut translated: Vec<String> = Vec::with_capacity(pieces.len());
        let mut failures = 0usize;
        let mut tokens = 0u64;
        let mut seconds = 0.0f64;
        for piece in &pieces {
            check_cancelled(request.cancel.as_ref())?;
            let prompts = if let Some(prompt) = plan.gemma_prompt(piece) {
                vec![prompt]
            } else {
                unique_prompts(vec![
                    PromptBuilder::plain_prompt(piece, request.target.english_name),
                    PromptBuilder::prompt(
                        piece,
                        TranslationStyle::Natural,
                        TranslationTone::Standard,
                        request.target.english_name,
                        false,
                    ),
                    PromptBuilder::prompt(
                        piece,
                        TranslationStyle::Literal,
                        TranslationTone::Standard,
                        request.target.english_name,
                        false,
                    ),
                ])
            };
            let mut success: Option<String> = None;
            for prompt in &prompts {
                let retry = retry_config(config, 1);
                let max_bytes = piece
                    .chars()
                    .count()
                    .saturating_mul(4)
                    .saturating_add(100)
                    .max(200)
                    * 4;
                let prompt = with_source_language(prompt.clone(), plan.source_hint());
                let raw = self
                    .collect_candidate(&prompt, &retry, max_bytes, request.cancel.as_ref())
                    .await?;
                if let Some(clean) = validated(&raw.text, piece, request.target, false) {
                    success = Some(clean);
                    tokens += raw.tokens;
                    seconds += raw.seconds;
                    break;
                }
            }
            match success {
                Some(text) => translated.push(text),
                None => {
                    translated.push(piece.clone());
                    failures += 1;
                }
            }
        }

        if failures >= pieces.len() {
            return Ok(None);
        }
        Ok(Some(BlockResult {
            text: translated.join(" "),
            warning: failures > 0,
            tokens,
            seconds,
        }))
    }

    /// One streamed candidate; a length-cut response becomes empty text.
    async fn collect_candidate(
        &self,
        prompt: &str,
        config: &BackendConfig,
        max_bytes: usize,
        cancel: Option<&CancelFlag>,
    ) -> Result<ChatResult, TranslationError> {
        match stream_chat(&self.client, prompt, config, cancel, max_bytes).await {
            // Python's `_collect_with_retry` raises `empty` for a byte-cap
            // overrun and `_collect_candidate` turns *any* `empty` into an
            // empty candidate, so the prompt ladder keeps going. Doing
            // otherwise would keep the source line, count a warning and might
            // even switch the whole job to the fallback provider.
            Ok(result) if result.exceeded_limit => {
                log::debug!("candidate exceeded the byte budget: treated as empty");
                Ok(ChatResult::default())
            }
            Ok(result) => Ok(result),
            Err(error) if error.kind == ErrorKind::Empty => {
                log::debug!("candidate rejected by the provider: {}", error.detail);
                Ok(ChatResult::default())
            }
            Err(error) => Err(error),
        }
    }

    /// One rewrite attempt, cleaned and rejected when empty.
    async fn rewrite_once(
        &self,
        prompt: &str,
        config: &BackendConfig,
        cancel: Option<&CancelFlag>,
        on_progress: &Option<crate::request::ProgressFn>,
    ) -> Result<ChatResult, TranslationError> {
        report(on_progress, 0, 1);
        let result = stream_chat(&self.client, prompt, config, cancel, REWRITE_MAX_BYTES).await?;
        if result.exceeded_limit {
            return Err(
                TranslationError::new(ErrorKind::Empty).with_detail("rewrite output too long")
            );
        }
        let cleaned = OutputSanitizer::clean(&result.text);
        if cleaned.is_empty() {
            return Err(
                TranslationError::new(ErrorKind::Empty).with_detail("rewrite returned nothing")
            );
        }
        report(on_progress, 1, 1);
        Ok(ChatResult {
            text: cleaned,
            ..result
        })
    }
}

// -------------------------------------------------------------------- typing

/// Options shared by the buffered (block) translation ladder.
#[derive(Clone, Copy)]
struct BlockOptions {
    preserve_line_breaks: bool,
    requires_markdown_structure: bool,
}

/// One translated block.
struct BlockResult {
    text: String,
    warning: bool,
    tokens: u64,
    seconds: f64,
}

/// One finished job, before the public output is built.
#[derive(Default)]
struct JobResult {
    text: String,
    warnings: usize,
    tokens: u64,
    seconds: f64,
    degenerate: bool,
}

/// A job that could not finish, together with the part that was translated.
struct JobFailure {
    error: TranslationError,
    partial: JobResult,
}

/// Counters accumulated before a job was abandoned.
struct JobProgress {
    warnings: usize,
    translated_count: usize,
    tokens: u64,
    seconds: f64,
}

/// One streamed candidate.
#[derive(Default)]
struct ChatResult {
    text: String,
    tokens: u64,
    seconds: f64,
    exceeded_limit: bool,
}

// ----------------------------------------------------------------- streaming

/// Stream one chat completion and accumulate its text.
///
/// The read timeout is configured on the client (180 s); the cancel flag is
/// polled every [`CANCEL_POLL`] while waiting for bytes, so a cancel drops the
/// response instead of waiting for the provider.
async fn stream_chat(
    client: &Client,
    prompt: &str,
    config: &BackendConfig,
    cancel: Option<&CancelFlag>,
    max_bytes: usize,
) -> Result<ChatResult, TranslationError> {
    if config.model.trim().is_empty() {
        return Err(TranslationError::new(ErrorKind::Model));
    }
    if config.requires_api_key && config.api_key.is_empty() {
        return Err(TranslationError::new(ErrorKind::Unauthorized).with_detail("api_key"));
    }
    check_cancelled(cancel)?;

    let base = config.compatible_base();
    let (url, protocol) = chat_endpoint(&base, config.kind);
    validate_url(&url, &base)?;
    let headers = json_headers(config, &base)?;
    let request = match config.kind {
        BackendKind::Ollama => client
            .post(&url)
            .headers(headers)
            .json(&ollama_body(prompt, config)),
        BackendKind::OpenAI => client
            .post(&url)
            .headers(headers)
            .json(&openai_body(prompt, config)),
    };

    let started = Instant::now();
    // The request itself must be cancellable: a server that accepts the
    // connection and stalls would otherwise keep the Cancel button inert for
    // the whole connect + read timeout.
    let sent = tokio::select! {
        biased;
        () = cancel_signal(cancel) => return Err(TranslationError::new(ErrorKind::Cancelled)),
        result = request.send() => result,
    };
    let mut response = sent.map_err(|error| request_error(&error, &base))?;
    let status = response.status().as_u16();
    if !(200..300).contains(&status) {
        let detail = status_detail(status, &response, config);
        return Err(http_error(status, &detail));
    }

    let mut reader = LineReader::default();
    let mut emitter = Emitter::new(max_bytes);
    let mut server_stats: Option<(u64, f64)> = None;
    let mut finished = false;

    'stream: loop {
        check_cancelled(cancel)?;
        let next = tokio::select! {
            biased;
            () = cancel_signal(cancel) => return Err(TranslationError::new(ErrorKind::Cancelled)),
            chunk = response.chunk() => chunk,
        };
        let Some(bytes) = next.map_err(|error| stream_error(&error, cancel))? else {
            break;
        };
        reader.push(&bytes);
        while let Some(line) = reader.next_line()? {
            if line.trim().is_empty() {
                continue;
            }
            let (terminal, stats) = consume(&protocol, &line, &mut emitter)?;
            if let Some(stats) = stats {
                server_stats = Some(stats);
            }
            if terminal {
                finished = true;
                break 'stream;
            }
        }
    }

    // A terminal frame may arrive without its trailing newline.
    if !finished {
        if let Some(line) = reader.finish() {
            if !line.trim().is_empty() {
                let (terminal, stats) = consume(&protocol, &line, &mut emitter)?;
                if let Some(stats) = stats {
                    server_stats = Some(stats);
                }
                finished = terminal;
            }
        }
    }

    check_cancelled(cancel)?;
    if !finished {
        return Err(TranslationError::new(ErrorKind::Interrupted)
            .with_detail("stream ended without a terminal event"));
    }

    let elapsed = started.elapsed().as_secs_f64();
    let span = match (emitter.first_at, emitter.last_at) {
        (Some(first), Some(last)) => last.saturating_duration_since(first).as_secs_f64(),
        _ => 0.0,
    };
    let (server_tokens, server_seconds) = match server_stats {
        Some((tokens, seconds)) => (Some(tokens), Some(seconds)),
        None => (None, None),
    };
    let generation_seconds = match server_seconds {
        Some(seconds) if seconds > 0.0 => seconds,
        _ if span > 0.0 => span,
        // Instant fake or real streams still get a measurable rate.
        _ if emitter.tokens > 0 => elapsed.max(0.001),
        _ => 0.0,
    };
    let total_tokens = server_tokens.unwrap_or(emitter.tokens);

    Ok(ChatResult {
        text: emitter.budget.text(),
        tokens: total_tokens,
        seconds: generation_seconds,
        exceeded_limit: emitter.budget.exceeded_limit(),
    })
}

/// Feed one frame to the protocol decoder with the stream accumulator.
fn consume(
    protocol: &Protocol,
    line: &str,
    emitter: &mut Emitter,
) -> Result<crate::wire::FrameOutcome, TranslationError> {
    match protocol {
        Protocol::Ollama => consume_ollama(line, &mut |piece| emitter.emit(piece)),
        Protocol::OpenAi => consume_openai(line, &mut |piece| emitter.emit(piece)),
    }
}

/// Accumulates streamed text and timing for one response.
struct Emitter {
    budget: OutputBudget,
    tokens: u64,
    first_at: Option<Instant>,
    last_at: Option<Instant>,
}

impl Emitter {
    fn new(max_bytes: usize) -> Self {
        Self {
            budget: OutputBudget::new(max_bytes),
            tokens: 0,
            first_at: None,
            last_at: None,
        }
    }

    /// Append one piece; returns `false` when generation must stop.
    fn emit(&mut self, piece: &str) -> bool {
        let now = Instant::now();
        let keep_going = self.budget.append(piece);
        self.tokens += 1;
        if self.first_at.is_none() {
            self.first_at = Some(now);
        }
        self.last_at = Some(now);
        keep_going
    }
}

/// Byte buffer that yields complete lines, including a final unterminated one.
#[derive(Default)]
struct LineReader {
    buffer: Vec<u8>,
}

impl LineReader {
    fn push(&mut self, bytes: &[u8]) {
        self.buffer.extend_from_slice(bytes);
    }

    /// Next line, splitting on `\n`, `\r\n` and a bare `\r`.
    ///
    /// `requests.Response.iter_lines()` uses universal newlines, so a server
    /// that terminates NDJSON or SSE frames with a bare CR must still work. A
    /// trailing `\r` is held back until the next byte arrives (it may be the
    /// first half of `\r\n`); [`Self::finish`] treats it as a terminator at EOF.
    fn next_line(&mut self) -> Result<Option<String>, TranslationError> {
        let mut index = 0;
        while index < self.buffer.len() {
            match self.buffer[index] {
                b'\n' => {
                    if index > MAX_LINE_BYTES {
                        return Err(line_too_long());
                    }
                    return Ok(Some(self.take_line(index, 1)));
                }
                b'\r' => {
                    if index + 1 < self.buffer.len() {
                        if index > MAX_LINE_BYTES {
                            return Err(line_too_long());
                        }
                        let width = if self.buffer[index + 1] == b'\n' {
                            2
                        } else {
                            1
                        };
                        return Ok(Some(self.take_line(index, width)));
                    }
                    break;
                }
                _ => index += 1,
            }
        }
        if self.buffer.len() > MAX_LINE_BYTES {
            // A server that never terminates a line must not grow the buffer
            // without bound; the response is unusable either way.
            return Err(line_too_long());
        }
        Ok(None)
    }

    /// Remove and return the line ending at `end`, consuming `width` bytes of
    /// the terminator.
    fn take_line(&mut self, end: usize, width: usize) -> String {
        let line: Vec<u8> = self.buffer[..end].to_vec();
        self.buffer.drain(..end + width);
        String::from_utf8_lossy(&line).into_owned()
    }

    fn finish(&mut self) -> Option<String> {
        if self.buffer.is_empty() {
            return None;
        }
        let mut line = std::mem::take(&mut self.buffer);
        trim_carriage_return(&mut line);
        Some(String::from_utf8_lossy(&line).into_owned())
    }
}

/// The error returned when one streamed line grows past [`MAX_LINE_BYTES`].
fn line_too_long() -> TranslationError {
    TranslationError::new(ErrorKind::Unexpected).with_detail("stream line exceeds the 4 MiB limit")
}

fn trim_carriage_return(line: &mut Vec<u8>) {
    if line.last() == Some(&b'\r') {
        line.pop();
    }
}

// -------------------------------------------------------------------- support

/// Endpoint and base URL validation shared with the probe.
pub(crate) fn validate_url(url: &str, base: &str) -> Result<(), TranslationError> {
    match reqwest::Url::parse(url) {
        Ok(parsed)
            if matches!(parsed.scheme(), "http" | "https")
                && parsed.host_str().is_some_and(|host| !host.is_empty()) =>
        {
            Ok(())
        }
        _ => Err(TranslationError::new(ErrorKind::InvalidUrl).with_detail(base)),
    }
}

/// Map a `reqwest` send error to a typed failure.
pub(crate) fn request_error(error: &reqwest::Error, base: &str) -> TranslationError {
    if error.is_builder() {
        TranslationError::new(ErrorKind::InvalidUrl).with_detail(base)
    } else {
        TranslationError::new(ErrorKind::Connection).with_detail(base)
    }
}

/// Map an error raised while reading the response body.
fn stream_error(error: &reqwest::Error, cancel: Option<&CancelFlag>) -> TranslationError {
    if is_cancelled(cancel) {
        return TranslationError::new(ErrorKind::Cancelled);
    }
    TranslationError::new(ErrorKind::Interrupted).with_detail(error.to_string())
}

/// Protocol specific `detail` for a failed status (Retry-After or model id).
fn status_detail(status: u16, response: &reqwest::Response, config: &BackendConfig) -> String {
    if status == 429 {
        response
            .headers()
            .get(reqwest::header::RETRY_AFTER)
            .and_then(|value| value.to_str().ok())
            .unwrap_or("")
            .to_string()
    } else if status == 404 {
        config.model.clone()
    } else {
        String::new()
    }
}

fn is_cancelled(cancel: Option<&CancelFlag>) -> bool {
    cancel.is_some_and(|flag| flag.load(Ordering::Relaxed))
}

fn check_cancelled(cancel: Option<&CancelFlag>) -> Result<(), TranslationError> {
    if is_cancelled(cancel) {
        Err(TranslationError::new(ErrorKind::Cancelled))
    } else {
        Ok(())
    }
}

/// Resolve when the cancel flag is set; never resolves without a flag.
async fn cancel_signal(cancel: Option<&CancelFlag>) {
    match cancel {
        Some(flag) => loop {
            if flag.load(Ordering::Relaxed) {
                return;
            }
            tokio::time::sleep(CANCEL_POLL).await;
        },
        None => std::future::pending::<()>().await,
    }
}

/// Sleep, but wake up immediately when the job is cancelled.
async fn sleep_or_cancel(
    duration: Duration,
    cancel: Option<&CancelFlag>,
) -> Result<(), TranslationError> {
    if cancel.is_none() {
        tokio::time::sleep(duration).await;
        return Ok(());
    }
    tokio::select! {
        biased;
        () = cancel_signal(cancel) => Err(TranslationError::new(ErrorKind::Cancelled)),
        () = tokio::time::sleep(duration) => Ok(()),
    }
}

/// Second and later attempts lower the temperature to at most 0.3.
fn retry_config(config: &BackendConfig, attempt: usize) -> BackendConfig {
    let mut retry = config.clone();
    if attempt > 0 {
        retry.temperature = retry.temperature.min(0.3);
    }
    retry
}

/// True when two configurations address the same endpoint and model.
///
/// The pointer comparison the Python code uses only works because both sides
/// share one object; two separately built configurations for the same server
/// must not be retried as if one were a fallback.
fn same_endpoint(left: &BackendConfig, right: &BackendConfig) -> bool {
    left.compatible_base() == right.compatible_base() && left.model == right.model
}

/// Fallback configuration only when it addresses a different endpoint.
fn distinct_fallback<'a>(request: &TranslateRequest<'a>) -> Option<&'a BackendConfig> {
    let fallback = request.fallback?;
    if same_endpoint(fallback, request.config) {
        None
    } else {
        Some(fallback)
    }
}

/// Build the result a caller keeps when the fallback also fails.
///
/// Blocks that were already translated stay as they are, the remaining lines
/// are copied from the source and counted as warnings, so the caller receives
/// a complete document with an accurate "lines left in the source language"
/// count instead of the fallback's error.
fn abandon_job(
    error: TranslationError,
    chunks: &[TextChunk],
    mut translated: Vec<String>,
    index: usize,
    progress: JobProgress,
) -> JobFailure {
    let mut warnings = progress.warnings;
    for chunk in &chunks[index..] {
        translated.push(format!("{}{}", chunk.prefix, chunk.text));
        warnings += 1;
    }
    JobFailure {
        error,
        partial: JobResult {
            text: TextChunker::compose(chunks, &translated).unwrap_or_default(),
            warnings,
            tokens: progress.tokens,
            seconds: progress.seconds,
            degenerate: warnings > 0 && progress.translated_count == 0,
        },
    }
}

/// Recompose the translated prefix for a partial result.
fn compose_through(chunks: &[TextChunk], translated: &[String], index: usize) -> String {
    TextChunker::compose(&chunks[..=index], translated).unwrap_or_default()
}

fn rate(tokens: u64, seconds: f64) -> Option<f64> {
    if tokens > 0 && seconds > 0.0 {
        Some(tokens as f64 / seconds)
    } else {
        None
    }
}

fn elapsed_ms(started: Instant) -> u64 {
    u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX)
}

fn report(callback: &Option<crate::request::ProgressFn>, completed: usize, total: usize) {
    let Some(callback) = callback else {
        return;
    };
    let result =
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| callback(completed, total)));
    if result.is_err() {
        log::error!("progress callback panicked");
    }
}

fn emit_partial(callback: &Option<crate::request::PartialFn>, text: &str) {
    let Some(callback) = callback else {
        return;
    };
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| callback(text)));
    if result.is_err() {
        log::error!("partial callback panicked");
    }
}

/// The "improve text" instruction used by the Write tab.
fn rewrite_prompt(text: &str, language: &str) -> String {
    format!(
        "You are an editor. Rewrite the following text in {language}. Improve clarity, \
         grammar, tone and style. Preserve the meaning, Markdown syntax, lists and line \
         breaks. Return only the rewritten text, without explanations or quotes.\n\n{text}"
    )
}
