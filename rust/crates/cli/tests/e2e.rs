//! End-to-end tests: the real `ofm` binary against a fake Ollama server.
//!
//! These tests exercise the whole stack — settings, prompts, chunking, streaming,
//! validation, document handling — without a window and without a real model.
//! They are the Rust counterpart of `windows/tests/test_e2e.py`.

use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;

/// A canned HTTP response.
struct Route {
    path: &'static str,
    content_type: &'static str,
    body: String,
}

/// Serve `routes` until the test drops the server; returns the base URL.
struct FakeServer {
    base_url: String,
    hits: Arc<AtomicUsize>,
    _thread: std::thread::JoinHandle<()>,
}

impl FakeServer {
    fn start(routes: Vec<Route>) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").expect("bind a local port");
        let port = listener.local_addr().expect("local address").port();
        let hits = Arc::new(AtomicUsize::new(0));
        let counter = Arc::clone(&hits);
        let routes = Arc::new(routes);

        let thread = std::thread::spawn(move || {
            for stream in listener.incoming() {
                let Ok(stream) = stream else { break };
                let routes = Arc::clone(&routes);
                let counter = Arc::clone(&counter);
                std::thread::spawn(move || handle(stream, &routes, &counter));
            }
        });

        Self {
            base_url: format!("http://127.0.0.1:{port}"),
            hits,
            _thread: thread,
        }
    }

    fn hits(&self) -> usize {
        self.hits.load(Ordering::SeqCst)
    }
}

fn handle(mut stream: TcpStream, routes: &[Route], counter: &AtomicUsize) {
    let mut reader = BufReader::new(stream.try_clone().expect("clone the socket"));
    let mut request_line = String::new();
    if reader.read_line(&mut request_line).is_err() {
        return;
    }
    // Drain the headers so the client can finish writing.
    loop {
        let mut line = String::new();
        match reader.read_line(&mut line) {
            Ok(0) => break,
            Ok(_) if line == "\r\n" || line == "\n" => break,
            Ok(_) => continue,
            Err(_) => return,
        }
    }

    let path = request_line
        .split_whitespace()
        .nth(1)
        .unwrap_or("/")
        .to_string();
    counter.fetch_add(1, Ordering::SeqCst);

    let route = routes.iter().find(|route| route.path == path);
    let (status, content_type, body) = match route {
        Some(route) => ("200 OK", route.content_type, route.body.clone()),
        None => ("404 Not Found", "text/plain", String::new()),
    };

    let response = format!(
        "HTTP/1.1 {status}\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = stream.write_all(response.as_bytes());
    let _ = stream.flush();
}

fn ndjson(lines: &[&str]) -> String {
    lines
        .iter()
        .map(|line| format!("{line}\n"))
        .collect::<String>()
}

fn chat_route(reply: &str) -> Route {
    let body = ndjson(&[
        &format!(
            r#"{{"model":"hy-mt2:7b","message":{{"role":"assistant","content":{}}},"done":false}}"#,
            serde_json::json!(reply)
        ),
        r#"{"model":"hy-mt2:7b","message":{"role":"assistant","content":""},"done":true,"eval_count":42,"eval_duration":1000000000}"#,
    ]);
    Route {
        path: "/api/chat",
        content_type: "application/x-ndjson",
        body,
    }
}

fn tags_route(models: &[&str]) -> Route {
    let names: Vec<String> = models
        .iter()
        .map(|name| format!(r#"{{"name":"{name}"}}"#))
        .collect();
    Route {
        path: "/api/tags",
        content_type: "application/json",
        body: format!(r#"{{"models":[{}]}}"#, names.join(",")),
    }
}

/// A private config directory so the tests never touch the user's settings.
struct Sandbox {
    dir: PathBuf,
}

impl Sandbox {
    fn new(tag: &str) -> Self {
        let dir = std::env::temp_dir().join(format!(
            "ofm-e2e-{}-{}-{}",
            tag,
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|value| value.as_nanos())
                .unwrap_or(0)
        ));
        std::fs::create_dir_all(&dir).expect("create the sandbox");
        Self { dir }
    }

    fn path(&self) -> &Path {
        &self.dir
    }
}

impl Drop for Sandbox {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.dir);
    }
}

fn run_cli(sandbox: &Sandbox, args: &[&str]) -> Output {
    let mut command = Command::new(env!("CARGO_BIN_EXE_ofm"));
    command
        .args(args)
        .env("XDG_CONFIG_HOME", sandbox.path())
        .env("APPDATA", sandbox.path())
        .env("LOCALAPPDATA", sandbox.path())
        .env("HOME", sandbox.path())
        .env("OFM_LOG", "warn");
    command.output().expect("run the ofm binary")
}

fn stdout(output: &Output) -> String {
    String::from_utf8_lossy(&output.stdout).into_owned()
}

fn stderr(output: &Output) -> String {
    String::from_utf8_lossy(&output.stderr).into_owned()
}

/// Seed the sandbox settings file the binary will load.
fn write_settings(sandbox: &Sandbox, document: serde_json::Value) {
    let path = sandbox.path().join("DeepL-oFM").join("settings.json");
    std::fs::create_dir_all(path.parent().expect("settings parent")).expect("create settings dir");
    std::fs::write(&path, document.to_string()).expect("write settings");
}

// ------------------------------------------------------------------- tests

#[test]
fn translates_text_through_a_streaming_server() {
    let server = FakeServer::start(vec![chat_route("Привіт, світе!")]);
    let sandbox = Sandbox::new("translate");

    let output = run_cli(
        &sandbox,
        &[
            "translate",
            "--text",
            "Hello, world!",
            "--source",
            "en",
            "--target",
            "uk",
            "--provider",
            "ollama",
            "--base-url",
            &server.base_url,
            "--model",
            "hy-mt2:7b",
        ],
    );

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    assert_eq!(stdout(&output).trim(), "Привіт, світе!");
    assert_eq!(server.hits(), 1, "exactly one chat request");
}

#[test]
fn reads_the_text_from_standard_input() {
    let server = FakeServer::start(vec![chat_route("Hallo, Welt!")]);
    let sandbox = Sandbox::new("stdin");

    let mut child = Command::new(env!("CARGO_BIN_EXE_ofm"))
        .args([
            "translate",
            "--source",
            "en",
            "--target",
            "de",
            "--provider",
            "ollama",
            "--base-url",
            &server.base_url,
            "--model",
            "hy-mt2:7b",
        ])
        .env("XDG_CONFIG_HOME", sandbox.path())
        .env("APPDATA", sandbox.path())
        .env("HOME", sandbox.path())
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .expect("spawn the binary");

    child
        .stdin
        .as_mut()
        .expect("stdin")
        .write_all(b"Hello, world!")
        .expect("write stdin");
    let output = child.wait_with_output().expect("wait");
    assert!(output.status.success(), "stderr: {}", stderr(&output));
    assert_eq!(stdout(&output).trim(), "Hallo, Welt!");
}

#[test]
fn lists_models_from_the_server() {
    let server = FakeServer::start(vec![tags_route(&["hy-mt2:7b", "qwen3:8b"])]);
    let sandbox = Sandbox::new("models");

    let output = run_cli(
        &sandbox,
        &[
            "models",
            "--provider",
            "ollama",
            "--base-url",
            &server.base_url,
        ],
    );

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    let listing = stdout(&output);
    assert!(listing.contains("hy-mt2:7b"), "listing: {listing}");
    assert!(listing.contains("qwen3:8b"), "listing: {listing}");
}

#[test]
fn check_fails_when_the_model_is_missing() {
    let server = FakeServer::start(vec![tags_route(&["qwen3:8b"])]);
    let sandbox = Sandbox::new("missing-model");

    let output = run_cli(
        &sandbox,
        &[
            "check",
            "--provider",
            "ollama",
            "--base-url",
            &server.base_url,
            "--model",
            "hy-mt2:7b",
        ],
    );

    assert!(!output.status.success(), "check must fail");
    let message = stderr(&output);
    assert!(message.contains("hy-mt2:7b"), "message: {message}");
    assert!(message.contains("qwen3:8b"), "message: {message}");
}

#[test]
fn check_succeeds_when_the_model_is_present() {
    let server = FakeServer::start(vec![tags_route(&["hy-mt2:7b"])]);
    let sandbox = Sandbox::new("present-model");

    let output = run_cli(
        &sandbox,
        &[
            "check",
            "--provider",
            "ollama",
            "--base-url",
            &server.base_url,
            "--model",
            "hy-mt2:7b",
        ],
    );

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    assert!(
        stdout(&output).contains("ok"),
        "stdout: {}",
        stdout(&output)
    );
}

#[test]
fn prompt_preview_shows_the_prompt_the_translator_sends() {
    let sandbox = Sandbox::new("prompt");
    let output = run_cli(
        &sandbox,
        &[
            "prompt",
            "--text",
            "Could you send me the report?",
            "--source",
            "en",
            "--target",
            "de",
            "--style",
            "literal",
            "--tone",
            "formal",
        ],
    );

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    assert_eq!(
        stdout(&output).trim_end(),
        "The source language is English. Please translate the following text into German. \
         Note that the translation style must strictly conform to [literal, word for word; \
         formal and professional]:\n\nCould you send me the report?"
    );
}

#[test]
fn prompt_preview_keeps_the_heading_template_for_markdown_headings() {
    let sandbox = Sandbox::new("prompt-heading");
    let output = run_cli(
        &sandbox,
        &["prompt", "--text", "## Title", "--target", "uk"],
    );

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    let text = stdout(&output);
    assert!(
        text.starts_with("Translate this heading into Ukrainian."),
        "prompt: {text}"
    );
    assert!(text.trim_end().ends_with("\n\nTitle"), "prompt: {text}");
}

#[test]
fn prompt_preview_uses_the_translate_gemma_instruction() {
    let sandbox = Sandbox::new("prompt-gemma");
    let output = run_cli(
        &sandbox,
        &[
            "prompt",
            "--text",
            "Hello, world!",
            "--source",
            "en",
            "--target",
            "de",
            "--model",
            "translategemma:4b",
        ],
    );

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    let text = stdout(&output);
    assert!(
        text.starts_with("You are a professional English (en) to German (de) translator."),
        "prompt: {text}"
    );
    assert!(
        text.trim_end().ends_with(":\n\n\nHello, world!"),
        "two blank lines before the text: {text}"
    );
}

#[test]
fn the_stored_base_url_wins_over_the_provider_default() {
    let server = FakeServer::start(vec![tags_route(&["hy-mt2:7b"])]);
    let sandbox = Sandbox::new("stored-url");
    write_settings(
        &sandbox,
        serde_json::json!({
            "provider": "ollama",
            "base_url": server.base_url,
            "model": "hy-mt2:7b",
        }),
    );

    let output = run_cli(&sandbox, &["models", "--provider", "ollama"]);

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    assert!(stdout(&output).contains("hy-mt2:7b"));
    assert_eq!(server.hits(), 1, "the stored URL must be used");
}

#[test]
fn translate_file_uses_the_enabled_fallback_provider() {
    let server = FakeServer::start(vec![chat_route("Übersetzt.")]);
    let sandbox = Sandbox::new("file-fallback");
    let source = sandbox.path().join("note.md");
    std::fs::write(&source, "Hello, world!\n").expect("write the document");
    write_settings(
        &sandbox,
        serde_json::json!({
            "provider": "ollama",
            "base_url": "http://127.0.0.1:1",
            "model": "hy-mt2:7b",
            "fallback_enabled": true,
            "fallback_provider": "ollama",
            "fallback_base_url": server.base_url,
            "fallback_model": "hy-mt2:7b",
        }),
    );

    let output = run_cli(
        &sandbox,
        &[
            "translate-file",
            source.to_str().expect("path"),
            "--target",
            "de",
        ],
    );

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    let written = PathBuf::from(stdout(&output).trim());
    let text = std::fs::read_to_string(&written).expect("read the output");
    assert!(text.contains("Übersetzt"), "translation written: {text}");
    assert!(server.hits() >= 1, "the fallback server must be used");
}

#[test]
fn connection_refused_is_reported_without_panicking() {
    let sandbox = Sandbox::new("refused");
    // Port 1 on loopback is closed in every sane environment.
    let output = run_cli(
        &sandbox,
        &[
            "models",
            "--provider",
            "ollama",
            "--base-url",
            "http://127.0.0.1:1",
        ],
    );

    assert!(!output.status.success(), "must fail");
    let message = stderr(&output);
    assert!(!message.is_empty(), "an error message is required");
    assert!(!message.contains("panicked"), "must not panic: {message}");
}

#[test]
fn translates_a_markdown_document_and_keeps_the_layout() {
    let server = FakeServer::start(vec![chat_route("Перекладено.")]);
    let sandbox = Sandbox::new("document");
    let source = sandbox.path().join("note.md");
    std::fs::write(
        &source,
        "# Heading\n\nFirst paragraph.\n\n- item one\n- item two\n\n```rust\nfn main() {}\n```\n",
    )
    .expect("write the document");

    let output = run_cli(
        &sandbox,
        &[
            "translate-file",
            source.to_str().expect("path"),
            "--target",
            "uk",
            "--provider",
            "ollama",
            "--base-url",
            &server.base_url,
            "--model",
            "hy-mt2:7b",
        ],
    );

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    let written = PathBuf::from(stdout(&output).trim());
    assert!(
        written.exists(),
        "output file must exist: {}",
        written.display()
    );
    let text = std::fs::read_to_string(&written).expect("read the output");
    assert!(text.starts_with("# "), "heading prefix kept: {text}");
    assert!(text.contains("- "), "list markers kept: {text}");
    assert!(text.contains("```rust"), "code fence kept: {text}");
    assert!(text.contains("Перекладено."), "translation written: {text}");
}

#[test]
fn info_reports_the_isolated_paths() {
    let sandbox = Sandbox::new("info");
    let output = run_cli(&sandbox, &["info"]);

    assert!(output.status.success(), "stderr: {}", stderr(&output));
    let text = stdout(&output);
    assert!(text.contains("settings:"), "stdout: {text}");
    assert!(text.contains("history:"), "stdout: {text}");
}
