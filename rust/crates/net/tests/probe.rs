//! Acceptance tests for model discovery, ported from `windows/tests/test_probe.py`.

mod support;

use ofm_config::{BackendConfig, BackendKind};
use ofm_net::{model_listed, ErrorKind, Translator};

use support::{FakeServer, Reply};

fn config(kind: BackendKind, base_url: &str, model: &str) -> BackendConfig {
    BackendConfig {
        kind,
        base_url: base_url.to_string(),
        model: model.to_string(),
        ..BackendConfig::default()
    }
}

fn strings(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| value.to_string()).collect()
}

#[tokio::test]
async fn probe_parses_ollama_tags() {
    let server = FakeServer::start(|_| {
        Reply::json(
            200,
            &serde_json::json!({
                "models": [
                    {"name": "hy-mt2:7b"},
                    {"name": "llama3:latest"},
                    {"model": "legacy-entry"},
                    {"size": 123}
                ]
            }),
        )
    })
    .await;

    let models = Translator::new()
        .list_models(&config(BackendKind::Ollama, &server.url(), "hy-mt2:7b"))
        .await
        .expect("models");

    assert_eq!(
        models,
        strings(&["hy-mt2:7b", "llama3:latest", "legacy-entry"])
    );
    assert_eq!(server.requests()[0].path, "/api/tags");
}

#[tokio::test]
async fn probe_parses_openai_models() {
    let server = FakeServer::start(|_| {
        Reply::json(
            200,
            &serde_json::json!({"data": [{"id": "gpt-4o-mini"}, {"id": "local-7b"}]}),
        )
    })
    .await;

    let models = Translator::new()
        .list_models(&config(BackendKind::OpenAI, &server.url(), "gpt-4o-mini"))
        .await
        .expect("models");

    assert_eq!(models, strings(&["gpt-4o-mini", "local-7b"]));
    assert_eq!(server.requests()[0].path, "/v1/models");
}

#[tokio::test]
async fn probe_does_not_double_v1() {
    let server = FakeServer::start(|_| Reply::json(200, &serde_json::json!({"data": []}))).await;
    let base = format!("{}/v1/", server.url());

    let models = Translator::new()
        .list_models(&config(BackendKind::OpenAI, &base, "x"))
        .await
        .expect("models");

    assert!(models.is_empty());
    assert_eq!(server.requests()[0].path, "/v1/models");
}

#[tokio::test]
async fn probe_sends_a_bearer_token() {
    let server =
        FakeServer::start(|_| Reply::json(200, &serde_json::json!({"data": [{"id": "x"}]}))).await;
    let mut backend = config(BackendKind::OpenAI, &server.url(), "x");
    backend.api_key = "secret".to_string();

    let models = Translator::new()
        .list_models(&backend)
        .await
        .expect("models");

    assert_eq!(models, strings(&["x"]));
    assert_eq!(
        server.requests()[0].header("authorization"),
        Some("Bearer secret")
    );
    assert!(
        server.requests()[0].header("content-type").is_none(),
        "the probe GET sends no content type"
    );
}

#[tokio::test]
async fn probe_maps_http_errors() {
    for (status, kind) in [
        (401u16, ErrorKind::Unauthorized),
        (429, ErrorKind::RateLimit),
        (502, ErrorKind::Server),
    ] {
        let server = FakeServer::start(move |_| Reply::status(status)).await;
        let error = Translator::new()
            .list_models(&config(BackendKind::Ollama, &server.url(), "hy-mt2:7b"))
            .await
            .expect_err("status error");
        assert_eq!(error.kind, kind, "status {status}");
        assert_eq!(error.status, Some(status), "status {status}");
    }
}

#[tokio::test]
async fn probe_maps_unexpected_payloads() {
    let invalid_json = FakeServer::start(|_| {
        Reply::body(b"not json".to_vec()).header("Content-Type", "application/json")
    })
    .await;
    let error = Translator::new()
        .list_models(&config(BackendKind::Ollama, &invalid_json.url(), "x"))
        .await
        .expect_err("invalid json");
    assert_eq!(error.kind, ErrorKind::Unexpected);
    assert_eq!(error.detail, "invalid JSON");

    let list_payload = FakeServer::start(|_| Reply::json(200, &serde_json::json!([1, 2, 3]))).await;
    let error = Translator::new()
        .list_models(&config(BackendKind::OpenAI, &list_payload.url(), "x"))
        .await
        .expect_err("unexpected payload");
    assert_eq!(error.kind, ErrorKind::Unexpected);
    assert_eq!(error.detail, "unexpected model list payload");
}

#[tokio::test]
async fn probe_maps_connection_errors() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0")
        .await
        .expect("bind");
    let address = listener.local_addr().expect("address");
    drop(listener);

    let error = Translator::new()
        .list_models(&config(
            BackendKind::Ollama,
            &format!("http://{address}"),
            "x",
        ))
        .await
        .expect_err("connection");
    assert_eq!(error.kind, ErrorKind::Connection);
}

#[tokio::test]
async fn probe_maps_invalid_urls() {
    let error = Translator::new()
        .list_models(&config(BackendKind::Ollama, "not a url", "x"))
        .await
        .expect_err("invalid url");
    assert_eq!(error.kind, ErrorKind::InvalidUrl);
}

#[test]
fn model_listed_matches_exact_tag_and_vendor_forms() {
    assert!(model_listed("hy-mt2:7b", &strings(&["hy-mt2:7b"])));
    assert!(model_listed("hy-mt2:7b", &strings(&["HY-MT2:7B"])));
    assert!(model_listed("hy-mt2", &strings(&["hy-mt2:7b"])));
    assert!(model_listed("gpt-oss", &strings(&["gpt-oss:120b-cloud"])));
}

#[test]
fn model_listed_accepts_vendor_slash_forms() {
    assert!(model_listed("hy-mt2-7b", &strings(&["tencent/hy-mt2-7b"])));
    assert!(!model_listed("hy-mt2:7b", &[]));
    assert!(!model_listed("hy-mt2:7b", &strings(&["llama-3.3-70b"])));
    assert!(!model_listed(
        "hy-mt2",
        &strings(&["tencent/hy-mt2-7b-extra"])
    ));
}
