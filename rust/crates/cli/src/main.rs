//! `ofm` — headless command line for DeepL-oFM.
//!
//! The CLI exists for two reasons: automation (translate a file from a script or
//! a CI job) and integration testing — it exercises the whole engine
//! (`ofm-config` → `ofm-text` → `ofm-net` → `ofm-docs`) without a window.

use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Args, Parser, Subcommand};
use ofm_config::{AppSettings, Provider};
use ofm_docs::DocumentTranslator;
use ofm_i18n::{t_in, AppLanguage, LanguageTable};
use ofm_net::Translator;
use ofm_text::{TranslationStyle, TranslationTone};

#[derive(Parser, Debug)]
#[command(
    name = "ofm",
    version,
    about = "DeepL-oFM command line: translate text and documents",
    long_about = None
)]
struct Cli {
    /// Interface language for diagnostics (en, uk, ru, de, fr, es, pl, pt, it)
    #[arg(long, global = true, default_value = "en")]
    language: String,

    /// Verbose logging
    #[arg(long, global = true)]
    verbose: bool,

    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand, Debug)]
enum Command {
    /// Translate a string and print the result
    Translate(TextArgs),
    /// Translate a document and write it next to the source (or to --out)
    TranslateFile(FileArgs),
    /// List the models the configured server offers
    Models(ConnArgs),
    /// Check the connection and the configured model
    Check(ConnArgs),
    /// Print the prompt that would be sent for a given text
    Prompt(TextArgs),
    /// Show the resolved settings and paths
    Info,
}

#[derive(Args, Debug)]
struct ConnArgs {
    /// Provider: ollama, ollamaCloud, lmStudio, omlx, llamaCpp, openRouter, groq, cerebras, custom
    #[arg(long)]
    provider: Option<String>,
    /// Server base URL (overrides the provider default)
    #[arg(long)]
    base_url: Option<String>,
    /// API key (defaults to the stored key for the provider)
    #[arg(long)]
    api_key: Option<String>,
    /// Model id
    #[arg(long)]
    model: Option<String>,
}

#[derive(Args, Debug)]
struct TextArgs {
    /// Text to translate; omit to read standard input
    #[arg(long)]
    text: Option<String>,
    /// Source language code, or "auto"
    #[arg(long, default_value = "auto")]
    source: String,
    /// Target language code
    #[arg(long, default_value = "en")]
    target: String,
    /// Style: auto, literal, natural
    #[arg(long, default_value = "auto")]
    style: String,
    /// Tone: standard, formal, casual
    #[arg(long, default_value = "standard")]
    tone: String,
    #[command(flatten)]
    conn: ConnArgs,
}

#[derive(Args, Debug)]
struct FileArgs {
    /// Document to translate (.txt .md .pdf .docx)
    path: PathBuf,
    /// Target language code
    #[arg(long, default_value = "en")]
    target: String,
    /// Write the result here instead of `<name>_<lang>.<ext>`
    #[arg(long)]
    out: Option<PathBuf>,
    #[command(flatten)]
    conn: ConnArgs,
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    env_logger::Builder::from_env(
        env_logger::Env::default().default_filter_or(if cli.verbose { "debug" } else { "warn" }),
    )
    .init();

    if let Some(language) = AppLanguage::from_code(&cli.language) {
        ofm_i18n::set_language(language);
    }

    let runtime = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(runtime) => runtime,
        Err(error) => {
            eprintln!("could not start the async runtime: {error}");
            return ExitCode::FAILURE;
        }
    };

    match runtime.block_on(run(cli.command)) {
        Ok(()) => ExitCode::SUCCESS,
        Err(message) => {
            eprintln!("{message}");
            ExitCode::FAILURE
        }
    }
}

async fn run(command: Command) -> Result<(), String> {
    match command {
        Command::Translate(args) => translate(args).await,
        Command::TranslateFile(args) => translate_file(args).await,
        Command::Models(args) => models(args).await,
        Command::Check(args) => check(args).await,
        Command::Prompt(args) => prompt(args),
        Command::Info => info(),
    }
}

// ---------------------------------------------------------------- helpers

fn language_or_die(code: &str) -> Result<&'static ofm_i18n::Language, String> {
    LanguageTable::get(code).ok_or_else(|| format!("unknown language: {code}"))
}

fn read_text(text: Option<String>) -> Result<String, String> {
    match text {
        Some(value) => Ok(value),
        None => {
            use std::io::Read;
            let mut buffer = String::new();
            std::io::stdin()
                .read_to_string(&mut buffer)
                .map_err(|error| format!("could not read standard input: {error}"))?;
            Ok(buffer)
        }
    }
}

fn config_from(
    conn: &ConnArgs,
    settings: &AppSettings,
) -> Result<ofm_config::BackendConfig, String> {
    let provider = match conn.provider.as_deref() {
        Some(value) => {
            Provider::from_value(value).ok_or_else(|| format!("unknown provider: {value}"))
        }
        None => Ok(settings.provider),
    }?;

    let mut config = settings.snapshot();
    config.kind = provider.kind();
    config.base_url = match conn.base_url.as_deref() {
        Some(url) => url.to_string(),
        // Without an override the stored endpoint wins; the provider default is
        // only the last resort. The app remembers one URL per provider.
        None => stored_base_url(settings, provider),
    };
    if let Some(model) = &conn.model {
        config.model = model.clone();
    } else if provider != settings.provider {
        config.model = String::new();
    }
    config.api_key = conn.api_key.clone().unwrap_or_else(|| {
        ofm_store_key(provider).unwrap_or_else(|| {
            if provider == settings.provider {
                settings.api_key.clone()
            } else {
                String::new()
            }
        })
    });
    config.requires_api_key = provider.requires_key();
    Ok(config)
}

/// Stored base URL for `provider`; the provider default only when none exists.
fn stored_base_url(settings: &AppSettings, provider: Provider) -> String {
    let remembered = settings
        .remembered
        .get(&format!("base_url.{}", provider.value()))
        .map(String::as_str);
    let current = (provider == settings.provider).then_some(settings.base_url.as_str());
    let candidate = current
        .map(str::trim)
        .filter(|url| !url.is_empty())
        .or_else(|| remembered.map(str::trim).filter(|url| !url.is_empty()));
    match candidate {
        Some(url) => {
            let mut value = url.to_string();
            while value.ends_with('/') {
                value.pop();
            }
            if value.is_empty() {
                provider.base_url().to_string()
            } else {
                value
            }
        }
        None => provider.base_url().to_string(),
    }
}

/// Fallback configuration with its API key loaded from the secret store.
///
/// [`AppSettings::load`] never reads keys from disk, so a fallback provider
/// that requires one would otherwise fail with `Unauthorized` before any
/// request is sent.
fn resolved_fallback(settings: &AppSettings) -> Option<ofm_config::BackendConfig> {
    let mut fallback = settings.fallback_config()?;
    if fallback.api_key.trim().is_empty() {
        if let Some(key) = ofm_store_key(settings.fallback_provider) {
            fallback.api_key = key;
        }
    }
    Some(fallback)
}

/// API keys live in the secret store; the CLI reads them the same way the app does.
fn ofm_store_key(provider: Provider) -> Option<String> {
    let store = ofm_store::SecretStore::new();
    let value = store.read(&provider.key_account());
    if value.trim().is_empty() {
        None
    } else {
        Some(value)
    }
}

fn style_from(value: &str) -> TranslationStyle {
    TranslationStyle::from_value(value).unwrap_or(TranslationStyle::Auto)
}

fn tone_from(value: &str) -> TranslationTone {
    TranslationTone::from_value(value).unwrap_or(TranslationTone::Standard)
}

// ----------------------------------------------------------------- commands

async fn translate(args: TextArgs) -> Result<(), String> {
    let text = read_text(args.text)?;
    if text.trim().is_empty() {
        return Err("nothing to translate".to_string());
    }

    let settings = AppSettings::load();
    let config = config_from(&args.conn, &settings)?;
    if config.model.trim().is_empty() {
        return Err("no model configured; pass --model or set one in the app".to_string());
    }

    let (source, source_explicit) = if args.source == "auto" {
        let detected = ofm_i18n::LanguageTable::detect(&text, settings.interface_language)
            .copied()
            .unwrap_or(LanguageTable::AUTO);
        (detected, false)
    } else {
        (*language_or_die(&args.source)?, true)
    };
    let target = language_or_die(&args.target)?;

    let translator = Translator::new();
    let fallback = resolved_fallback(&settings);
    let request = ofm_net::TranslateRequest {
        text: &text,
        source: &source,
        source_explicit,
        target,
        style: style_from(&args.style),
        tone: tone_from(&args.tone),
        config: &config,
        fallback: fallback.as_ref(),
        cancel: None,
        on_progress: None,
        on_partial: None,
    };

    let output = translator
        .translate(request)
        .await
        .map_err(|error| error.message())?;

    println!("{}", output.text);
    if output.warnings > 0 {
        eprintln!("{}", tf_warning(output.warnings));
    }
    Ok(())
}

fn tf_warning(count: usize) -> String {
    t_in(
        "Some lines could not be translated (%d); they are left in the source language.",
        ofm_i18n::current_language(),
    )
    .replace("%d", &count.to_string())
}

async fn translate_file(args: FileArgs) -> Result<(), String> {
    let settings = AppSettings::load();
    let config = config_from(&args.conn, &settings)?;
    if config.model.trim().is_empty() {
        return Err("no model configured; pass --model or set one in the app".to_string());
    }
    let target = language_or_die(&args.target)?;

    let document = DocumentTranslator::read(&args.path).map_err(|error| error.message())?;
    let destination = args
        .out
        .clone()
        .unwrap_or_else(|| DocumentTranslator::suggested_path(&args.path, target));

    let translator = Translator::new();
    let source = LanguageTable::AUTO;
    let fallback = resolved_fallback(&settings);
    let mut failures: usize = 0;

    let written = DocumentTranslator::write(
        &document,
        &destination,
        &mut |paragraph: &str| {
            let request = ofm_net::TranslateRequest {
                text: paragraph,
                source: &source,
                source_explicit: false,
                target,
                style: TranslationStyle::Auto,
                tone: TranslationTone::Standard,
                config: &config,
                fallback: fallback.as_ref(),
                cancel: None,
                on_progress: None,
                on_partial: None,
            };
            // The document writer is synchronous; `block_in_place` hands the
            // worker thread over so `block_on` is legal here.
            match tokio::task::block_in_place(|| {
                tokio::runtime::Handle::current().block_on(translator.translate(request))
            }) {
                Ok(output) => {
                    failures += output.warnings;
                    Ok(output.text)
                }
                Err(error) => Err(error.message()),
            }
        },
        None,
        None,
    )
    .map_err(|error| error.message())?;

    println!("{}", written.display());
    if failures > 0 {
        eprintln!("{}", tf_warning(failures));
    }
    Ok(())
}

async fn models(args: ConnArgs) -> Result<(), String> {
    let settings = AppSettings::load();
    let config = config_from(&args, &settings)?;
    let translator = Translator::new();
    let models = translator
        .list_models(&config)
        .await
        .map_err(|error| error.message())?;
    for model in models {
        println!("{model}");
    }
    Ok(())
}

async fn check(args: ConnArgs) -> Result<(), String> {
    let settings = AppSettings::load();
    let config = config_from(&args, &settings)?;
    let translator = Translator::new();
    let models = translator
        .list_models(&config)
        .await
        .map_err(|error| error.message())?;

    let configured = config.model.trim();
    if models.is_empty() {
        return Err("the server returned no models".to_string());
    }
    if !configured.is_empty() && !ofm_net::model_listed(configured, &models) {
        return Err(format!(
            "server responds, but model “{configured}” is missing; available: {}",
            models.join(", ")
        ));
    }
    println!(
        "ok · {} · {} · {} models",
        config.base_url,
        if configured.is_empty() {
            "(no model)"
        } else {
            configured
        },
        models.len()
    );
    if configured.is_empty() {
        println!("note: no model configured yet; pick one with --model or in the app");
    }
    Ok(())
}

fn prompt(args: TextArgs) -> Result<(), String> {
    let text = read_text(args.text)?;
    if text.trim().is_empty() {
        return Err("nothing to translate".to_string());
    }
    let settings = AppSettings::load();
    let config = config_from(&args.conn, &settings)?;
    let target = language_or_die(&args.target)?;
    let (source, source_explicit) = if args.source == "auto" {
        let detected = LanguageTable::detect(&text, settings.interface_language)
            .copied()
            .unwrap_or(LanguageTable::AUTO);
        (detected, false)
    } else {
        (*language_or_die(&args.source)?, true)
    };

    // Use the translator's own selection, so the preview is exactly the first
    // request body instead of a separately built instruction.
    let prompt = ofm_net::first_prompt_for_text(
        &text,
        &source,
        source_explicit,
        target,
        style_from(&args.style),
        tone_from(&args.tone),
        &config.model,
    )
    .ok_or_else(|| "nothing to translate".to_string())?;
    println!("{prompt}");
    Ok(())
}

fn info() -> Result<(), String> {
    let settings = AppSettings::load();
    println!("settings: {}", AppSettings::default_path().display());
    println!(
        "history:  {}",
        ofm_store::HistoryStore::default_path().display()
    );
    println!(
        "provider: {} ({})",
        settings.provider.title(),
        settings.provider.value()
    );
    println!("base URL: {}", settings.base_url);
    println!("model:    {}", settings.model);
    println!(
        "key:      {}",
        if settings.api_key.trim().is_empty() {
            "not set"
        } else {
            "stored"
        }
    );
    println!("language: {}", settings.interface_language.code());
    println!("style:    {} / {}", settings.last_style, settings.last_tone);
    Ok(())
}
